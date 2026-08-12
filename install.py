#!/usr/bin/env python3
"""Instalador cross-platform: crea el venv, instala dependencias y prepara los archivos de config."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# En Windows la consola suele usar cp1252, que no soporta ✓/→/✗ — forzamos UTF-8.
# line_buffering evita que la salida de los subprocesos (pip, venv) se intercale
# fuera de orden con los print() del script cuando la salida está redirigida.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"

MIN_PYTHON = (3, 10)


def check_python_version(summary: list[str]) -> bool:
    if sys.version_info < MIN_PYTHON:
        v = sys.version_info
        print(f"✗ Se requiere Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} o superior (detectado: {v.major}.{v.minor}.{v.micro})")
        print("  Instalá una versión compatible desde https://www.python.org/downloads/ y volvé a ejecutar este script.")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detectado")
    return True


def venv_python(venv_dir: Path) -> Path:
    # No usamos "activate" (difiere entre cmd/PowerShell/bash) — llamamos
    # directamente al intérprete del venv, que tiene el mismo efecto.
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def create_venv(summary: list[str]) -> bool:
    if VENV_DIR.exists():
        msg = "✓ Entorno virtual ya existe en .venv/ (sin modificar)"
        print(msg)
        summary.append(msg)
        return True

    print("→ Creando entorno virtual en .venv/ ...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        msg = "✗ No se pudo crear el entorno virtual"
        print(msg)
        summary.append(msg)
        return False

    msg = "✓ Entorno virtual creado"
    print(msg)
    summary.append(msg)
    return True


def install_dependencies(summary: list[str]) -> bool:
    if not REQUIREMENTS.exists():
        msg = "✗ No se encontró requirements.txt — no se instalaron dependencias"
        print(msg)
        summary.append(msg)
        return False

    python_bin = venv_python(VENV_DIR)
    if not python_bin.exists():
        msg = "✗ No se encontró el intérprete del entorno virtual — no se instalaron dependencias"
        print(msg)
        summary.append(msg)
        return False

    print("→ Instalando dependencias desde requirements.txt (puede tardar unos minutos) ...")
    result = subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    if result.returncode != 0:
        msg = "✗ Falló la instalación de dependencias — revisá el error de pip arriba"
        print(msg)
        summary.append(msg)
        return False

    msg = "✓ Dependencias instaladas"
    print(msg)
    summary.append(msg)
    return True


def copy_if_missing(src: Path, dst: Path, summary: list[str]) -> None:
    if dst.exists():
        msg = f"✓ {dst.name} ya existe (sin modificar)"
        print(msg)
        summary.append(msg)
        return

    if not src.exists():
        msg = f"✗ No se encontró {src.name} — no se pudo crear {dst.name}"
        print(msg)
        summary.append(msg)
        return

    try:
        shutil.copy(src, dst)
    except OSError as e:
        msg = f"✗ No se pudo crear {dst.name}: {e}"
        print(msg)
        summary.append(msg)
        return

    msg = f"✓ {dst.name} creado desde {src.name}"
    print(msg)
    summary.append(msg)


def ensure_dir(path: Path, summary: list[str]) -> None:
    if path.exists():
        msg = f"✓ Carpeta {path.name}/ ya existe"
        print(msg)
        summary.append(msg)
        return

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = f"✗ No se pudo crear la carpeta {path.name}/: {e}"
        print(msg)
        summary.append(msg)
        return

    msg = f"✓ Carpeta {path.name}/ creada"
    print(msg)
    summary.append(msg)


def main() -> None:
    summary: list[str] = []

    print("=" * 60)
    print("  Instalación — intervals-icu-mcp")
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
        "→ Editá .env con tu ATHLETE_ID y API_KEY de intervals.icu",
        "→ Personalizá SYSTEM_PROMPT.md con tu perfil de atleta",
        "→ Completá athlete_profile.json con tus datos (opcional)",
        "→ Ejecutá: python setup_claude.py para conectar con Claude Desktop",
    ]

    print()
    print("=" * 60)
    print("  Resumen")
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
