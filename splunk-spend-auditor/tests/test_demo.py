"""Fase 5A: demo offline sobre datos sintéticos deterministas. El demo debe
ejecutar el pipeline REAL, sin red, sin credenciales y escribiendo solo en
el directorio de salida."""

from __future__ import annotations

import socket

import pytest
from typer.testing import CliRunner

from splunk_spend_auditor.cli import app
from splunk_spend_auditor.demo import build_demo_collection

runner = CliRunner()


@pytest.fixture
def no_network(monkeypatch):
    """Cualquier intento de conexión/resolución DNS falla el test."""

    def _blocked(*args, **kwargs):
        raise AssertionError("the demo attempted a network operation")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr("splunk_spend_auditor.cli.collect_rest", _blocked)
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)


def _run(tmp_path):
    return runner.invoke(app, ["demo", "--output-dir", str(tmp_path / "out")])


def test_demo_runs_without_network_or_credentials(no_network, tmp_path):
    result = _run(tmp_path)
    assert result.exit_code == 0, result.output
    assert "Analysis complete." in result.output
    assert "synthetic" in result.output.lower()


def test_demo_writes_only_the_expected_files(no_network, tmp_path):
    result = _run(tmp_path)
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["report.html", "report.md"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out"]


def test_demo_cli_summary_numbers(no_network, tmp_path):
    out = _run(tmp_path).output
    assert "Indexes analyzed:      9" in out
    assert "Sourcetypes analyzed:  12" in out
    assert "Daily ingest:          267.2 GB/day" in out
    assert "Findings detected:     4 (2 possible waste, 2 review)" in out
    assert str(tmp_path / "out" / "report.html") in out


def test_demo_report_contains_core_sections_and_findings(no_network, tmp_path):
    _run(tmp_path)
    html = (tmp_path / "out" / "report.html").read_text()
    for section in (
        "Executive Summary",
        "Current Environment",
        "Ingestion Breakdown",
        "Top Optimization Candidates",
        "Protected / High Value",
        "Potential Savings",
        "Risk Considerations",
        "Methodology",
    ):
        assert section in html
    assert "Synthetic demo dataset" in html
    assert "k8s:kube_container_logs" in html
    assert "app:debug_verbose" in html
    assert "POSSIBLE_WASTE" in html


def test_demo_never_invents_dollar_figures(no_network, tmp_path):
    _run(tmp_path)
    text = (tmp_path / "out" / "report.md").read_text()
    assert "Not provided" in text
    assert "$" not in text


def test_demo_output_is_deterministic(no_network, tmp_path):
    runner.invoke(app, ["demo", "--output-dir", str(tmp_path / "a")])
    runner.invoke(app, ["demo", "--output-dir", str(tmp_path / "b")])
    a = (tmp_path / "a" / "report.md").read_text().splitlines()
    b = (tmp_path / "b" / "report.md").read_text().splitlines()
    strip = [i for i, line in enumerate(a) if "UTC" in line]
    assert [l for i, l in enumerate(a) if i not in strip] == [
        l for i, l in enumerate(b) if i not in strip
    ]


def test_synthetic_input_is_deterministic_and_wellformed():
    first, second = build_demo_collection(), build_demo_collection()
    assert first.ingest.equals(second.ingest)
    assert first.audit_searches.equals(second.audit_searches)
    assert len(first.ingest) == 12 * 28
    assert first.ingest["gb"].ge(0).all()
    # El scheduler existe en el fixture para probar que se excluye.
    assert first.audit_searches["search_id"].str.startswith("scheduler_").any()
