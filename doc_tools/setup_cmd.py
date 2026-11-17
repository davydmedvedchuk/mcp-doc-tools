"""`doc-tools setup`: adds this server to Claude Desktop's config file. Other servers in the file are kept, and a backup is written first."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Claude/claude_desktop_config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Claude/claude_desktop_config.json"


def entry(folder: str) -> dict:
    # the full path of this Python, so it works even when "doc-tools" is not on PATH (common on Windows)
    return {"command": sys.executable, "args": ["-m", "doc_tools"], "env": {"DOC_TOOLS_ROOT": str(Path(folder).expanduser().resolve())}}


def merge(existing: dict, folder: str) -> dict:
    out = dict(existing)
    servers = dict(out.get("mcpServers") or {})
    servers["doc-tools"] = entry(folder)
    out["mcpServers"] = servers
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="doc-tools setup", description="Connect doc-tools to Claude Desktop.")
    ap.add_argument("--folder", default=".", help="the one folder the assistant may work in (default: the current folder)")
    ap.add_argument("--print", dest="show", action="store_true", help="only print the config, change nothing")
    ap.add_argument("--config", help="path of the config file (default: Claude Desktop's own)")
    a = ap.parse_args(argv)
    folder = Path(a.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"That folder does not exist: {folder}", file=sys.stderr); return 2
    path = Path(a.config) if a.config else config_path()
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            print(f"{path} is not valid JSON. Fix or move it, then run this again. Nothing was changed.", file=sys.stderr); return 2
        if not isinstance(current, dict):
            print(f"{path} has an unexpected shape. Nothing was changed.", file=sys.stderr); return 2
    new = merge(current, str(folder))
    text = json.dumps(new, indent=2, ensure_ascii=False)
    if a.show:
        print(text); return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.write_text(text + "\n", encoding="utf-8")
    kept = [k for k in new["mcpServers"] if k != "doc-tools"]
    print(f"Done. doc-tools can now work in: {folder}")
    print(f"Config: {path}" + (f" (backup: {path.name}.bak)" if path.with_name(path.name + '.bak').exists() else ""))
    if kept: print("Other servers kept as they were: " + ", ".join(kept))
    print("Restart Claude Desktop to load it.")
    return 0
