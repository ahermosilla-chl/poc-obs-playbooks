"""Fase 5B: los recursos de runtime viven dentro del paquete y se localizan
sin depender del repositorio ni del directorio de trabajo."""

from __future__ import annotations

import importlib.util
import re
from importlib import resources
from pathlib import Path

from typer.testing import CliRunner

from splunk_spend_auditor import __version__
from splunk_spend_auditor.cli import app

ROOT = Path(__file__).resolve().parent.parent


def test_templates_and_queries_are_package_resources():
    pkg = resources.files("splunk_spend_auditor")
    for name in ("report.html.j2", "report.md.j2"):
        assert (pkg / "templates" / name).is_file()
    for name in ("ingest_by_index_sourcetype.spl", "audit_interactive_searches.spl", "metadata_last_seen.spl"):
        assert (pkg / "queries" / name).is_file()


def test_no_runtime_resources_left_outside_the_package():
    assert not (ROOT / "templates").exists()
    assert not (ROOT / "queries").exists()


def test_demo_works_from_an_arbitrary_working_directory(tmp_path, monkeypatch):
    work = tmp_path / "elsewhere"
    work.mkdir()
    monkeypatch.chdir(work)
    result = CliRunner().invoke(app, ["demo", "--output-dir", str(work / "o")])
    assert result.exit_code == 0, result.output
    assert (work / "o" / "report.html").exists()


def test_default_rest_queries_resolve_without_cwd_dependency(tmp_path, monkeypatch):
    import httpx

    from splunk_spend_auditor.collector.rest_collector import RestConfig, collect

    monkeypatch.chdir(tmp_path)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(401, json={})

    config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
    try:
        collect(config)
    except Exception as exc:  # RestCollectionError por el 401 -- lo relevante es no FileNotFoundError
        assert not isinstance(exc, FileNotFoundError)
    assert seen, "la query empaquetada debió cargarse y enviarse"


def test_cli_version_matches_single_source_of_truth():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"splunk-spend-auditor {__version__}"
    assert 'dynamic = ["version"]' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_build_script_artifact_naming():
    spec = importlib.util.spec_from_file_location("lsa_build", ROOT / "scripts" / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    assert build.read_version() == __version__
    assert re.fullmatch(
        rf"splunk-spend-auditor-{re.escape(__version__)}-(linux|macos|windows)-(x86_64|arm64)(\.exe)?",
        build.artifact_name(),
    )
