#!/usr/bin/env python3
"""Cross-platform installer: creates the venv, installs dependencies, and prepares config files."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows consoles usually default to cp1252, which doesn't support ✓/→/✗ — force UTF-8.
# line_buffering prevents subprocess output (pip, venv) from interleaving out of
# order with the script's print() calls when output is redirected.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"

MIN_PYTHON = (3, 10)


def check_python_version(summary: list[str]) -> bool:
    if sys.version_info < MIN_PYTHON:
        v = sys.version_info
        print(f"✗ Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or higher is required (detected: {v.major}.{v.minor}.{v.micro})")
        print("  Install a compatible version from https://www.python.org/downloads/ and re-run this script.")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detected")
    return True


def venv_python(venv_dir: Path) -> Path:
    # We don't use "activate" (it differs across cmd/PowerShell/bash) — we call
    # the venv's interpreter directly, which has the same effect.
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def create_venv(summary: list[str]) -> bool:
    if VENV_DIR.exists():
        msg = "✓ Virtual environment already exists at .venv/ (unchanged)"
        print(msg)
        summary.append(msg)
        return True

    print("→ Creating virtual environment at .venv/ ...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        msg = "✗ Could not create the virtual environment"
        print(msg)
        summary.append(msg)
        return False

    msg = "✓ Virtual environment created"
    print(msg)
    summary.append(msg)
    return True


def install_dependencies(summary: list[str]) -> bool:
    if not REQUIREMENTS.exists():
        msg = "✗ requirements.txt not found — dependencies were not installed"
        print(msg)
        summary.append(msg)
        return False

    python_bin = venv_python(VENV_DIR)
    if not python_bin.exists():
        msg = "✗ Virtual environment interpreter not found — dependencies were not installed"
        print(msg)
        summary.append(msg)
        return False

    print("→ Installing dependencies from requirements.txt (this may take a few minutes) ...")
    result = subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    if result.returncode != 0:
        msg = "✗ Dependency installation failed — check the pip error above"
        print(msg)
        summary.append(msg)
        return False

    msg = "✓ Dependencies installed"
    print(msg)
    summary.append(msg)
    return True


def copy_if_missing(src: Path, dst: Path, summary: list[str]) -> None:
    if dst.exists():
        msg = f"✓ {dst.name} already exists (unchanged)"
        print(msg)
        summary.append(msg)
        return

    if not src.exists():
        msg = f"✗ {src.name} not found — could not create {dst.name}"
        print(msg)
        summary.append(msg)
        return

    try:
        shutil.copy(src, dst)
    except OSError as e:
        msg = f"✗ Could not create {dst.name}: {e}"
        print(msg)
        summary.append(msg)
        return

    msg = f"✓ {dst.name} created from {src.name}"
    print(msg)
    summary.append(msg)


def ensure_dir(path: Path, summary: list[str]) -> None:
    if path.exists():
        msg = f"✓ {path.name}/ folder already exists"
        print(msg)
        summary.append(msg)
        return

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = f"✗ Could not create the {path.name}/ folder: {e}"
        print(msg)
        summary.append(msg)
        return

    msg = f"✓ {path.name}/ folder created"
    print(msg)
    summary.append(msg)


def main() -> None:
    summary: list[str] = []

    print("=" * 60)
    print("  Installation — intervals-icu-mcp")
    print("=" * 60)

    if not check_python_version(summary):
        sys.exit(1)

    venv_ok = create_venv(summary)
    deps_ok = install_dependencies(summary) if venv_ok else False

    copy_if_missing(ROOT / ".env.example", ROOT / ".env", summary)
    copy_if_missing(ROOT / "SYSTEM_PROMPT.example.md", ROOT / "SYSTEM_PROMPT.md", summary)
    copy_if_missing(ROOT / "athlete_profile.example.json", ROOT / "athlete_profile.json", summary)

    ensure_dir(ROOT / "db", summary)
    ensure_dir(ROOT / "fit_files", summary)

    pending = [
        "→ Edit .env with your intervals.icu ATHLETE_ID and API_KEY",
        "→ Customize SYSTEM_PROMPT.md with your athlete profile",
        "→ Fill in athlete_profile.json with your data (optional)",
        "→ Run: python setup_claude.py to connect to Claude Desktop",
    ]

    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    for line in summary:
        print(line)
    print()
    for line in pending:
        print(line)
    print("=" * 60)

    if not (venv_ok and deps_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
