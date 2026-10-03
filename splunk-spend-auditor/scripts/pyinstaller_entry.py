"""Punto de entrada para PyInstaller: equivalente al console script
`splunk-spend-auditor` (splunk_spend_auditor.cli:app)."""

from splunk_spend_auditor.cli import app

if __name__ == "__main__":
    app()
