"""Fase 5B.1: el workflow de builds nativos reutiliza los scripts del
proyecto y no publica nada ni usa secretos."""

from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release-build.yml"


@pytest.fixture
def text():
    if not WORKFLOW.exists():
        pytest.skip("workflow vive en la raíz del monorepo; no disponible aquí")
    return WORKFLOW.read_text(encoding="utf-8")


def test_manual_trigger_only(text):
    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text and "pull_request" not in text


def test_native_matrix_covers_three_platforms(text):
    for runner in ("ubuntu-22.04", "windows-2022", "macos-14"):
        assert runner in text
    assert "expected_machine: arm64" in text


def test_reuses_project_scripts(text):
    assert "scripts/build.py" in text
    assert "scripts/smoke_test.py" in text


def test_no_publication_and_no_secrets(text):
    lowered = text.lower()
    for forbidden in ("secrets.", "action-gh-release", "gh release", "pypi", "twine", "codesign", "notariz"):
        assert forbidden not in lowered
    assert "contents: read" in text
