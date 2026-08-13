#!/usr/bin/env python3
"""Generates/updates the 'intervals-icu' entry in claude_desktop_config.json."""
import json
import os
import platform
import sys
from pathlib import Path
from typing import Optional

# Same reason as in install.py: cp1252 in Windows consoles doesn't support ✓/→/✗.
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
    Claude Desktop installed from the Microsoft Store stores its config in
    Packages\\<PackageId>\\LocalCache\\Roaming\\Claude\\. The exact PackageId
    varies, so we look for any folder containing 'Claude'.
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
    Returns (config_path, installed). 'installed' is True if we found
    the config file or the folder where Claude Desktop would store it,
    which indicates the app has run at least once on this system.
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
        # Nothing found — return the standard path as our best guess,
        # but flagged as "not installed" so the caller doesn't try to write.
        fallback = Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
        return fallback, False

    if system == "Darwin":
        candidate = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        installed = candidate.exists() or candidate.parent.exists()
        return candidate, installed

    # Linux and other Unix systems
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
        print(f"✗ {config_path} exists but is not valid JSON ({e}).")
        print("  Review it manually before running this script again.")
        return None


def main() -> None:
    print("=" * 60)
    print("  Claude Desktop configurator — intervals-icu-mcp")
    print("=" * 60)
    print(f"Detected operating system: {platform.system()}")

    python_bin = venv_python(ROOT / ".venv")
    if not python_bin.exists():
        print("✗ Virtual environment (.venv) not found.")
        print("→ Run first: python install.py")
        sys.exit(1)

    entry = build_mcp_entry(python_bin)

    print()
    print(f"Configuration block generated for '{SERVER_NAME}':")
    print(json.dumps({SERVER_NAME: entry}, indent=2, ensure_ascii=False))

    config_path, installed = find_claude_config_path()

    if not installed or config_path is None:
        print()
        print("✗ Claude Desktop was not detected.")
        print("→ Install it from claude.ai/download and run this script again.")
        return

    existing = load_existing_config(config_path)
    if existing is None:
        sys.exit(1)

    if not isinstance(existing.get("mcpServers"), dict):
        existing["mcpServers"] = {}
    existing["mcpServers"][SERVER_NAME] = entry

    print()
    print(f"Full config that will be written to:\n  {config_path}")
    print(json.dumps(existing, indent=2, ensure_ascii=False))

    answer = input(f"\nWrite to {config_path}? (y/n): ").strip().lower()
    if answer != "y":
        print("→ Cancelled. No file was modified.")
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print("✓ Claude Desktop configured")
    print("→ Restart Claude Desktop to activate the MCP")


if __name__ == "__main__":
    main()
