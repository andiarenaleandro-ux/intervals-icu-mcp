#!/usr/bin/env python3
"""Genera/actualiza la entrada 'intervals-icu' en claude_desktop_config.json."""
import json
import os
import platform
import sys
from pathlib import Path
from typing import Optional

# Mismo motivo que en install.py: cp1252 en consolas de Windows no soporta ✓/→/✗.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent
SERVER_NAME = "intervals-icu"


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def build_mcp_entry(python_bin: Path) -> dict:
    return {
        "command": str(python_bin),
        "args": ["-m", "server.main"],
        "cwd": str(ROOT),
    }


def _windows_store_fallback() -> Optional[Path]:
    """
    Claude Desktop instalado desde Microsoft Store guarda su config en
    Packages\\<PackageId>\\LocalCache\\Roaming\\Claude\\. El PackageId exacto
    varía, así que buscamos cualquier carpeta que contenga 'Claude'.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    packages_dir = Path(local_appdata) / "Packages"
    if not packages_dir.exists():
        return None
    for pkg in sorted(packages_dir.glob("*Claude*")):
        candidate = pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
        if candidate.exists() or candidate.parent.exists():
            return candidate
    return None


def find_claude_config_path() -> tuple[Optional[Path], bool]:
    """
    Retorna (ruta_del_config, instalado). 'instalado' es True si encontramos
    el archivo de config o la carpeta donde Claude Desktop lo guardaría,
    lo que indica que la app corrió al menos una vez en este sistema.
    """
    system = platform.system()

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            standard = Path(appdata) / "Claude" / "claude_desktop_config.json"
            if standard.exists() or standard.parent.exists():
                return standard, True
        store_path = _windows_store_fallback()
        if store_path is not None:
            return store_path, True
        # No se encontró nada — devolvemos la ruta estándar como mejor palpito,
        # pero marcada como "no instalado" para que el caller no intente escribir.
        fallback = Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
        return fallback, False

    if system == "Darwin":
        candidate = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        installed = candidate.exists() or candidate.parent.exists()
        return candidate, installed

    # Linux y otros Unix
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    candidate = base / "Claude" / "claude_desktop_config.json"
    installed = candidate.exists() or candidate.parent.exists()
    return candidate, installed


def load_existing_config(config_path: Path) -> Optional[dict]:
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ {config_path} existe pero no es JSON válido ({e}).")
        print("  Revisalo manualmente antes de volver a correr este script.")
        return None


def main() -> None:
    print("=" * 60)
    print("  Configurador de Claude Desktop — intervals-icu-mcp")
    print("=" * 60)
    print(f"Sistema operativo detectado: {platform.system()}")

    python_bin = venv_python(ROOT / ".venv")
    if not python_bin.exists():
        print("✗ No se encontró el entorno virtual (.venv).")
        print("→ Ejecutá primero: python install.py")
        sys.exit(1)

    entry = build_mcp_entry(python_bin)

    print()
    print(f"Bloque de configuración generado para '{SERVER_NAME}':")
    print(json.dumps({SERVER_NAME: entry}, indent=2, ensure_ascii=False))

    config_path, installed = find_claude_config_path()

    if not installed or config_path is None:
        print()
        print("✗ No se detectó Claude Desktop instalado.")
        print("→ Instalalo desde claude.ai/download y después volvé a correr este script.")
        return

    existing = load_existing_config(config_path)
    if existing is None:
        sys.exit(1)

    if not isinstance(existing.get("mcpServers"), dict):
        existing["mcpServers"] = {}
    existing["mcpServers"][SERVER_NAME] = entry

    print()
    print(f"Config completo que se escribirá en:\n  {config_path}")
    print(json.dumps(existing, indent=2, ensure_ascii=False))

    answer = input(f"\n¿Escribir en {config_path}? (s/n): ").strip().lower()
    if answer != "s":
        print("→ Cancelado. No se modificó ningún archivo.")
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print("✓ Claude Desktop configurado")
    print("→ Reiniciá Claude Desktop para activar el MCP")


if __name__ == "__main__":
    main()
