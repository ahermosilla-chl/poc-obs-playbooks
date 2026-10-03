"""Smoke test del ejecutable standalone (Fase 5B).

    python scripts/smoke_test.py dist/splunk-spend-auditor-<version>-<os>-<arch>

Copia el binario a un directorio temporal FUERA del repo, lo ejecuta con un
entorno vacío (sin PATH ni venv) y verifica --version, --help y demo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED = [
    "Indexes analyzed:      9",
    "Sourcetypes analyzed:  12",
    "Daily ingest:          267.2 GB/day",
    "Findings detected:     4 (2 possible waste, 2 review)",
]


def main() -> None:
    src = Path(sys.argv[1]).resolve()
    checksum_file = src.with_name(src.name + ".sha256")
    if checksum_file.exists():
        expected = checksum_file.read_text(encoding="utf-8").split()[0]
        actual = hashlib.sha256(src.read_bytes()).hexdigest()
        assert actual == expected, f"SHA-256 mismatch: {actual} != {expected}"
        print("SHA-256 verified:", actual)
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / ("splunk-spend-auditor" + src.suffix)
        shutil.copy2(src, exe)
        env = {"HOME": tmp, "USERPROFILE": tmp}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")

        def run(*args: str) -> str:
            res = subprocess.run([str(exe), *args], cwd=tmp, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            assert res.returncode == 0, f"{args}: exit {res.returncode}\n{res.stdout}\n{res.stderr}"
            return res.stdout

        assert "splunk-spend-auditor" in run("--version")
        assert "quickscan" in run("--help")
        out = run("demo", "--output-dir", str(Path(tmp) / "out"))
        for line in EXPECTED:
            assert line in out, f"missing in demo output: {line}"
        files = sorted(p.name for p in (Path(tmp) / "out").iterdir())
        assert files == ["report.html", "report.md"], files
        assert "k8s:kube_container_logs" in (Path(tmp) / "out" / "report.html").read_text(encoding="utf-8")
    print("SMOKE TEST OK:", src.name, f"({src.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
