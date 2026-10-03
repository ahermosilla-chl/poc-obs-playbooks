"""Build del ejecutable standalone (Fase 5B).

    python scripts/build.py        # o: make build

Genera dist/splunk-spend-auditor-<version>-<os>-<arch>[.exe] y su .sha256.
PyInstaller NO cross-compila: cada plataforma debe construirse en su propio
sistema operativo. Requiere `pip install -e ".[build]"`.
"""

from __future__ import annotations

import hashlib
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "splunk_spend_auditor"
DIST = ROOT / "dist"


def read_version() -> str:
    # Única fuente de verdad: splunk_spend_auditor/__init__.py
    match = re.search(r'__version__\s*=\s*"([^"]+)"', (PKG / "__init__.py").read_text())
    if not match:
        sys.exit("No se pudo leer __version__")
    return match.group(1)


def platform_tag() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine, machine
    )
    os_name = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(system)
    if os_name is None:
        sys.exit(f"Plataforma no soportada: {system}")
    return os_name, arch


def artifact_name() -> str:
    os_name, arch = platform_tag()
    suffix = ".exe" if os_name == "windows" else ""
    return f"splunk-spend-auditor-{read_version()}-{os_name}-{arch}{suffix}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if "--print-artifact-name" in sys.argv:
        print(artifact_name())
        return
    name = artifact_name()
    sep = ";" if platform.system() == "Windows" else ":"
    work = ROOT / "build"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", name,
        "--distpath", str(DIST),
        "--workpath", str(work),
        "--specpath", str(work),
        "--paths", str(ROOT / "src"),
        # Solo los recursos de runtime requeridos: nada de .env, docs ni repo.
        "--add-data", f"{PKG / 'templates'}{sep}splunk_spend_auditor/templates",
        "--add-data", f"{PKG / 'queries'}{sep}splunk_spend_auditor/queries",
        "--exclude-module", "pytest",
        str(ROOT / "scripts" / "pyinstaller_entry.py"),
    ]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    artifact = DIST / name
    digest = sha256_of(artifact)
    (DIST / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    print(f"\nArtifact: {artifact}")
    print(f"Size:     {artifact.stat().st_size:,} bytes")
    print(f"SHA-256:  {digest}")


if __name__ == "__main__":
    main()
