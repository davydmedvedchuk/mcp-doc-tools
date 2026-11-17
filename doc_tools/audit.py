"""Project audit: looks through one folder of a website or app project for things that break the "data stays on the device" rules.
Reads files only. Nothing is sent anywhere."""
from __future__ import annotations

import re
from pathlib import Path

TEXT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".ts", ".json", ".md", ".py", ".svg", ".txt", ".yml", ".yaml", ".toml", ".xml"}
SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist", "build"}
URL = re.compile(r"""(?:src|href|action|url\(|import\s|from\s|fetch\()\s*=?\s*["']?\(?\s*((?:https?:)?//[^\s"')>]+)""", re.I)
# hosts that are only a link a person clicks, not a file the page loads
LINK_ONLY = re.compile(r'<a\s[^>]*href=["\']?((?:https?:)?//[^\s"\'>]+)', re.I)
SECRETS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("API key in code", re.compile(r"""(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*["'][A-Za-z0-9_\-+/=]{16,}["']""")),
]
TRACKERS = ("google-analytics.com", "googletagmanager.com", "facebook.net", "connect.facebook", "hotjar.com", "mixpanel.com", "segment.com", "clarity.ms", "doubleclick.net", "plausible.io", "fullstory.com")
BIG = 2 * 1024 * 1024


def host(u: str) -> str:
    u = u[2:] if u.startswith("//") else u.split("://", 1)[-1]
    return u.split("/", 1)[0].split(":", 1)[0].lower()


def audit(root: Path, max_files: int = 2000) -> dict:
    findings: list[dict] = []
    add = lambda level, kind, file, line, detail: findings.append({"level": level, "kind": kind, "file": file, "line": line, "detail": detail})
    n = 0
    names = {p.name.lower() for p in root.iterdir() if p.is_file()}
    for need, why in (("readme.md", "no README"), ("license", "no LICENSE file")):
        if need not in names and not any(x.startswith(need) for x in names):
            add("info", "missing", ".", 0, why)
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]) or p.is_symlink() or not p.is_file():
            continue
        n += 1
        if n > max_files:
            add("info", "limit", ".", 0, f"stopped after {max_files} files"); break
        rel = p.relative_to(root).as_posix()
        size = p.stat().st_size
        if size > BIG: add("info", "big file", rel, 0, f"{size / 1048576:.1f} MB")
        if p.suffix.lower() not in TEXT_EXT or size > 3 * BIG:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000: line = line[:4000]
            for m in URL.finditer(line):
                u = m.group(1); h = host(u)
                if not h or h in ("localhost", "127.0.0.1", "www.w3.org", "w3.org"): continue
                tracker = next((t for t in TRACKERS if t in h), None)
                if p.suffix.lower() == ".md": continue
                if LINK_ONLY.search(line) and u in [x.group(1) for x in LINK_ONLY.finditer(line)] and not re.search(r"(?:src|url\(|import|fetch|rel=[\"']?stylesheet)", line, re.I):
                    continue
                if tracker: add("error", "tracker", rel, i, f"{h} loads on the page")
                else: add("warn", "other site", rel, i, f"loads from {h}")
            for label, rx in SECRETS:
                if rx.search(line):
                    add("error", "possible secret", rel, i, f"looks like a {label} (value not shown)")
    seen, out = set(), []
    for f in findings:
        k = (f["kind"], f["file"], f["detail"])
        if k not in seen: seen.add(k); out.append(f)
    order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda f: (order[f["level"]], f["file"], f["line"]))
    return {"files_scanned": n, "counts": {lv: sum(1 for f in out if f["level"] == lv) for lv in order}, "findings": out[:200]}
