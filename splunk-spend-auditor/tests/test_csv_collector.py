"""Tests del collector CSV -- en particular, el manejo de archivos
opcionales ausentes (docs/architecture.md, 'Manejo de errores')."""

import pandas as pd
import pytest

from splunk_spend_auditor.collector.csv_collector import load_from_directory


def _write_minimal_ingest(directory):
    df = pd.DataFrame(
        [
            {"date": "2026-09-01", "index": "main", "sourcetype": "nginx", "gb": 1.0},
            {"date": "2026-09-02", "index": "main", "sourcetype": "nginx", "gb": 1.2},
        ]
    )
    df.to_csv(directory / "ingest_by_index_sourcetype.csv", index=False)


def test_missing_ingest_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_from_directory(tmp_path)


def test_missing_optional_files_are_recorded_not_silently_assumed(tmp_path):
    _write_minimal_ingest(tmp_path)
    collection = load_from_directory(tmp_path)

    assert collection.ingest is not None
    assert collection.audit_searches is None
    assert collection.saved_searches is None
    assert collection.sources_available["audit_searches"] is False
    assert collection.sources_available["saved_searches"] is False
    assert collection.sources_available["ingest"] is True


def test_protected_overrides_parses_index_colon_sourcetype_lines(tmp_path):
    _write_minimal_ingest(tmp_path)
    (tmp_path / "protected_overrides.txt").write_text(
        "# comentario\n\ndr:heartbeat_check\nlegacy:app_2019\n"
    )
    collection = load_from_directory(tmp_path)
    assert collection.protected_overrides == {
        ("dr", "heartbeat_check"),
        ("legacy", "app_2019"),
    }


def test_nonexistent_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_from_directory(tmp_path / "no_existe")
