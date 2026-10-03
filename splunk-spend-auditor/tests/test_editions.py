"""Fase 5C: fronteras Community / Pro. El entitlement se inyecta en el borde
de la app (cli.resolve_entitlement); no existe bypass para el usuario."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from splunk_spend_auditor import entitlements
from splunk_spend_auditor.cli import EXIT_PRO_REQUIRED, app
from splunk_spend_auditor.demo import build_demo_collection
from splunk_spend_auditor.entitlements import COMMUNITY, PRO, Capability, Edition

runner = CliRunner()
SRC = Path(__file__).resolve().parent.parent / "src" / "splunk_spend_auditor"


@pytest.fixture
def demo_as_real_data(monkeypatch, tmp_path):
    """Un 'entorno real' (CSV) servido por el fixture sintético, sin disco/red."""
    monkeypatch.setattr("splunk_spend_auditor.cli.load_from_directory", lambda _d: build_demo_collection())
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _as(monkeypatch, entitlement):
    monkeypatch.setattr("splunk_spend_auditor.cli.resolve_entitlement", lambda: entitlement)


# --- entitlement model -------------------------------------------------------

def test_default_entitlement_is_community():
    assert entitlements.resolve_entitlement() == COMMUNITY


def test_capability_matrix():
    assert COMMUNITY.allows(Capability.QUICKSCAN)
    for cap in (Capability.FULL_QUICKSCAN, Capability.FULL_AUDIT, Capability.FULL_REPORT):
        assert not COMMUNITY.allows(cap)
        assert PRO.allows(cap)
    assert PRO.allows(Capability.QUICKSCAN)
    assert COMMUNITY.edition.value == "Log Spend Auditor Community"
    assert PRO.edition is Edition.PRO


# --- demo --------------------------------------------------------------------

def test_community_can_run_the_full_detail_demo(tmp_path):
    result = runner.invoke(app, ["demo", "--output-dir", str(tmp_path / "o")])
    assert result.exit_code == 0, result.output
    html = (tmp_path / "o" / "report.html").read_text(encoding="utf-8")
    for section in ("Usage Analysis", "Top Optimization Candidates", "Data Value Score", "Methodology"):
        assert section in html


# --- community quickscan -----------------------------------------------------

def test_community_quickscan_gives_real_aggregate_opportunity(demo_as_real_data):
    result = runner.invoke(app, ["quickscan", "--from-csv", "ignored"])
    out = result.output
    assert result.exit_code == 0, out
    assert "Log Spend Auditor Community" in out
    assert "Total ingest:         267.2 GB/day" in out
    assert "Datasets analyzed:    12 across 9 indexes" in out
    assert "Direct candidates:       2" in out
    assert "Review candidates:       2" in out
    assert "Weighted opportunity:    111.6 GB/day" in out
    assert "Potential reduction:     41.8% of observed ingest" in out


def test_community_quickscan_preview_is_limited_to_top_three_by_impact(demo_as_real_data):
    out = runner.invoke(app, ["quickscan", "--from-csv", "x"]).output
    preview = out.split("Top candidates")[1]
    assert preview.index("k8s:kube_container_logs") < preview.index("app:debug_verbose") < preview.index("infra:windows_perfmon")
    assert "POSSIBLE_WASTE" in preview and "REVIEW" in preview
    assert "legacy:app_2019" not in out  # 4º candidato: fuera de la vista previa


def test_community_quickscan_withholds_evidence_and_inventory(demo_as_real_data):
    result = runner.invoke(app, ["quickscan", "--from-csv", "x"])
    out = result.output
    for forbidden in (
        "web:nginx_access", "payments:txn_events", "security:ids_alerts",  # inventario
        "Top 5 consumers", "Searches", "Scheduled", "Data Value", "Last data observed",
        "Recommendation", "HIGH_VALUE", "PROTECTED",
    ):
        assert forbidden not in out
    assert list(demo_as_real_data.iterdir()) == []  # ningún archivo escrito


def test_community_quickscan_without_opportunities_is_not_pushy(monkeypatch, tmp_path):
    from splunk_spend_auditor.collector.csv_collector import RawCollection

    col = build_demo_collection()
    col = RawCollection(ingest=col.ingest[col.ingest["index"].isin(["web", "payments"])],
                        audit_searches=col.audit_searches, saved_searches=col.saved_searches,
                        last_seen=col.last_seen, sources_available=col.sources_available)
    monkeypatch.setattr("splunk_spend_auditor.cli.load_from_directory", lambda _d: col)
    out = runner.invoke(app, ["quickscan", "--from-csv", "x"]).output
    assert "No optimization opportunities were detected" in out
    assert "Optimization opportunities detected" not in out
    assert "Pro provides" not in out


# --- audit is Pro ------------------------------------------------------------

def test_community_cannot_run_audit_and_fails_before_collection(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("collection started for a locked command")

    monkeypatch.setattr("splunk_spend_auditor.cli.load_from_directory", boom)
    monkeypatch.setattr("splunk_spend_auditor.cli.collect_rest", boom)
    monkeypatch.setattr("splunk_spend_auditor.cli.getpass.getpass", boom)  # ni pide token
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)
    for args in (["--from-csv", "x"], ["--host", "splunk.example.com"]):
        out_dir = tmp_path / "o"
        result = runner.invoke(app, ["audit", *args, "--output-dir", str(out_dir)])
        assert result.exit_code == EXIT_PRO_REQUIRED == 3
        assert "Log Spend Auditor Pro required" in result.output
        assert "splunk-spend-auditor quickscan" in result.output
        assert not out_dir.exists()


def test_pro_entitlement_runs_full_audit_with_html_and_markdown(monkeypatch, demo_as_real_data):
    _as(monkeypatch, PRO)
    result = runner.invoke(app, ["audit", "--from-csv", "x", "--output-dir", "out"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in (demo_as_real_data / "out").iterdir()) == ["report.html", "report.md"]
    html = (demo_as_real_data / "out" / "report.html").read_text(encoding="utf-8")
    for section in ("Usage Analysis", "Top Optimization Candidates", "Methodology", "Risk Considerations"):
        assert section in html


def test_pro_quickscan_keeps_full_terminal_detail(monkeypatch, demo_as_real_data):
    _as(monkeypatch, PRO)
    out = runner.invoke(app, ["quickscan", "--from-csv", "x"]).output
    assert "Top 5 consumers by GB/day" in out
    assert "Possible waste: 2 datasets" in out
    assert "877" not in out and "111.6 GB/day" in out


def test_classification_results_do_not_depend_on_edition(monkeypatch, demo_as_real_data):
    import re

    community = runner.invoke(app, ["quickscan", "--from-csv", "x"]).output
    _as(monkeypatch, PRO)
    pro = runner.invoke(app, ["quickscan", "--from-csv", "x"]).output
    nums = lambda s: re.search(r"111\.6 GB/day.*?41\.8%", s, re.S)
    assert nums(community) and nums(pro)


# --- no user-facing bypass ---------------------------------------------------

def test_no_environment_variable_or_flag_unlocks_pro(monkeypatch, demo_as_real_data):
    for name in ("SPLUNK_SPEND_AUDITOR_PRO", "SPLUNK_SPEND_AUDITOR_EDITION", "PRO", "EDITION",
                 "LSA_PRO", "LOG_SPEND_AUDITOR_EDITION"):
        monkeypatch.setenv(name, "pro")
    assert entitlements.resolve_entitlement() == COMMUNITY
    assert runner.invoke(app, ["audit", "--from-csv", "x"]).exit_code == EXIT_PRO_REQUIRED
    for flag in ("--edition", "--pro", "--unlock-pro", "--license"):
        assert runner.invoke(app, ["audit", "--from-csv", "x", flag, "pro"]).exit_code == 2  # opción inexistente


def test_cli_exposes_no_edition_options():
    group = typer.main.get_command(app)
    for command in group.commands.values():
        for param in command.params:
            names = " ".join(param.opts).lower()
            assert not any(w in names for w in ("edition", "pro", "license", "unlock")), names


def test_entitlement_source_reads_no_environment_or_files():
    tree = ast.parse((SRC / "entitlements.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"os", "sys", "pathlib", "subprocess", "httpx", "socket"}


# --- centralization ----------------------------------------------------------

def test_edition_logic_is_centralized_in_entitlements_module():
    for path in SRC.rglob("*.py"):
        if path.name == "entitlements.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "Edition" not in text, f"{path.name} conoce Edition"
        assert not re.search(r"\b(COMMUNITY|PRO)\b", text), f"{path.name} compara ediciones"
        if path.name != "cli.py":
            assert "entitlements" not in text, f"{path.name} no debería conocer entitlements"
