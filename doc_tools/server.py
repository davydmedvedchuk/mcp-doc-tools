"""Doc tools as an MCP server. Everything runs on this computer, and only inside one folder you choose.

Set DOC_TOOLS_ROOT to that folder (default: the folder the server was started in).
"""
from __future__ import annotations

import os
from pathlib import Path

import pillow_heif
import pypdfium2 as pdfium
import pytesseract
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from . import audit as audit_mod
from . import netguard, sitecheck
from .prep import clean, fit

pillow_heif.register_heif_opener()

ROOT = Path(os.environ.get("DOC_TOOLS_ROOT", ".")).resolve()
MAX_FILES = 200
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp"}

mcp = MCPServer(
    "doc-tools",
    instructions=(
        "Local document tools. Paths are relative to one working folder; nothing outside it can be read or written. "
        "Start with list_files. Tools never overwrite: results get a new file name, which they return."
    ),
)


class PathError(ToolError):
    pass


def safe(p: str) -> Path:
    """Resolve a path inside ROOT. Refuses anything that lands outside it (.., absolute paths, symlinks)."""
    q = (ROOT / p).resolve()
    if q != ROOT and ROOT not in q.parents:
        raise PathError(f"'{p}' is outside the working folder")
    return q


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def free_name(p: Path) -> Path:
    """Never overwrite: report.pdf -> report-2.pdf -> report-3.pdf"""
    if not p.exists():
        return p
    i = 2
    while (p.with_name(f"{p.stem}-{i}{p.suffix}")).exists():
        i += 1
    return p.with_name(f"{p.stem}-{i}{p.suffix}")


def existing(p: str) -> Path:
    q = safe(p)
    if not q.is_file():
        raise PathError(f"'{p}' is not a file here")
    return q


def pages_from(spec: str | None, n: int) -> list[int]:
    """'1-3,5' -> [0,1,2,4] (zero based). Empty means all pages."""
    if not spec or not spec.strip():
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo < 1 or hi > n or lo > hi:
            raise PathError(f"page range '{part}' does not fit a document of {n} pages")
        out.extend(range(lo - 1, hi))
    return out


@mcp.tool()
def list_files(folder: str = ".") -> list[dict]:
    """List PDFs and images in the working folder (or a subfolder), with sizes. Start here."""
    d = safe(folder)
    if not d.is_dir():
        raise PathError(f"'{folder}' is not a folder here")
    items = []
    for f in sorted(d.iterdir()):
        if f.is_file() and (f.suffix.lower() == ".pdf" or f.suffix.lower() in IMAGE_EXT):
            items.append({"path": rel(f), "kb": round(f.stat().st_size / 1024)})
        if len(items) >= MAX_FILES:
            break
    return items


@mcp.tool()
def pdf_info(path: str) -> dict:
    """Page count, page size, whether it has selectable text, whether it is encrypted."""
    f = existing(path)
    r = PdfReader(str(f))
    if r.is_encrypted:
        return {"path": rel(f), "encrypted": True, "note": "Password protected. Not opened."}
    has_text = any((pg.extract_text() or "").strip() for pg in r.pages[:3])
    box = r.pages[0].mediabox
    return {"path": rel(f), "pages": len(r.pages), "page_size_pt": [round(float(box.width)), round(float(box.height))],
            "has_text": has_text, "kb": round(f.stat().st_size / 1024), "encrypted": False,
            "hint": None if has_text else "No selectable text: this looks like a scan. Use read_text."}


@mcp.tool()
def pdf_text(path: str, pages: str = "") -> str:
    """Extract the selectable text of a PDF. pages like '1-3,5'; empty means all. Scans have none: use read_text."""
    f = existing(path)
    r = PdfReader(str(f))
    if r.is_encrypted:
        raise PathError("This PDF is password protected.")
    idx = pages_from(pages, len(r.pages))
    return "\n\n".join(f"--- page {i + 1} ---\n{(r.pages[i].extract_text() or '').strip()}" for i in idx)


@mcp.tool()
def pdf_merge(paths: list[str], output: str = "merged.pdf") -> dict:
    """Join PDFs in the given order into a new PDF."""
    if len(paths) < 2:
        raise PathError("Give at least two files.")
    w = PdfWriter()
    for p in paths:
        r = PdfReader(str(existing(p)))
        if r.is_encrypted:
            raise PathError(f"'{p}' is password protected.")
        for pg in r.pages:
            w.add_page(pg)
    out = free_name(safe(output))
    with open(out, "wb") as fh:
        w.write(fh)
    return {"saved": rel(out), "pages": len(w.pages)}


@mcp.tool()
def pdf_extract_pages(path: str, pages: str, output: str = "") -> dict:
    """Keep only some pages (like '2-4,7') in a new PDF. The original stays as it is."""
    f = existing(path)
    r = PdfReader(str(f))
    if r.is_encrypted:
        raise PathError("This PDF is password protected.")
    w = PdfWriter()
    for i in pages_from(pages, len(r.pages)):
        w.add_page(r.pages[i])
    out = free_name(safe(output) if output else f.with_name(f"{f.stem}-pages.pdf"))
    with open(out, "wb") as fh:
        w.write(fh)
    return {"saved": rel(out), "pages": len(w.pages)}


@mcp.tool()
def pdf_compress(path: str, quality: str = "smaller", output: str = "") -> dict:
    """Make a PDF smaller. quality: 'smaller' (150 dpi) or 'smallest' (100 dpi). Pages become images, so text is no
    longer selectable; run read_text on the result if you need the words."""
    dpi, q = {"smaller": (150, 75), "smallest": (100, 55)}.get(quality, (None, None))
    if dpi is None:
        raise PathError("quality must be 'smaller' or 'smallest'")
    f = existing(path)
    doc = pdfium.PdfDocument(str(f))
    imgs = [doc[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(len(doc))]
    out = free_name(safe(output) if output else f.with_name(f"{f.stem}-{quality}.pdf"))
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:], resolution=dpi, quality=q)
    before, after = f.stat().st_size, out.stat().st_size
    if after >= before:                      # text-only PDFs are already tiny; as images they would grow
        out.unlink()
        return {"saved": None, "kb_before": round(before / 1024), "kb_after": round(after / 1024),
                "note": "The result would not be smaller, so nothing was saved. This file is already compact."}
    return {"saved": rel(out), "kb_before": round(before / 1024), "kb_after": round(after / 1024)}


def load_pages(f: Path, pages: str) -> list[tuple[int, Image.Image]]:
    if f.suffix.lower() == ".pdf":
        doc = pdfium.PdfDocument(str(f))
        out = []
        for i in pages_from(pages, len(doc)):
            pg = doc[i]
            s = min(3.0, 3000 / max(pg.get_size()))
            out.append((i + 1, pg.render(scale=s).to_pil().convert("RGB")))
        return out
    if f.suffix.lower() not in IMAGE_EXT:
        raise PathError("Only PDF and images (jpg, png, webp, heic, tiff, bmp).")
    return [(1, fit(ImageOps.exif_transpose(Image.open(f)).convert("RGB")))]


@mcp.tool()
def read_text(path: str, language: str = "eng", pages: str = "", clean_up: bool = True) -> str:
    """OCR: read the text of a scan, photo or scanned PDF. language is a Tesseract code or a mix like 'eng+por' or
    'rus+ukr+eng'. clean_up straightens the page and removes shadows first (recommended for phone photos).
    Needs the tesseract program and the language packs installed."""
    f = existing(path)
    parts = []
    for n, im in load_pages(f, pages):
        angle = 0.0
        if clean_up:
            im, angle = clean(fit(im))
        txt = pytesseract.image_to_string(im, lang=language).strip()
        note = f" (straightened {angle:.1f}°)" if clean_up and abs(angle) >= 0.2 else ""
        parts.append(f"--- page {n}{note} ---\n{txt}")
    return "\n\n".join(parts)


@mcp.tool()
def clean_scan(path: str, output: str = "") -> dict:
    """Straighten a scan or photo and make it black and white. Saves a new PNG and returns the angle that was removed."""
    f = existing(path)
    n, im = load_pages(f, "1")[0]
    bw, ang = clean(fit(im))
    out = free_name(safe(output) if output else f.with_name(f"{f.stem}-clean.png"))
    bw.save(out)
    return {"saved": rel(out), "straightened_degrees": round(ang, 1)}


@mcp.tool()
def shrink_photo(path: str, max_side: int = 1600, quality: int = 80, output: str = "") -> dict:
    """Make a photo smaller (JPEG). Works with HEIC from an iPhone. max_side is the longest side in pixels."""
    if not (200 <= max_side <= 8000) or not (30 <= quality <= 95):
        raise PathError("max_side must be 200 to 8000 and quality 30 to 95")
    f = existing(path)
    if f.suffix.lower() not in IMAGE_EXT:
        raise PathError("That is not an image file.")
    im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    out = free_name(safe(output) if output else f.with_name(f"{f.stem}-small.jpg"))
    im.save(out, "JPEG", quality=quality, optimize=True)
    return {"saved": rel(out), "kb_before": round(f.stat().st_size / 1024), "kb_after": round(out.stat().st_size / 1024),
            "size": list(im.size)}


# ---- websites and projects (your own) ----
def _report(issues: list[dict]) -> dict:
    order = {"error": 0, "warn": 1, "info": 2}
    issues = sorted(issues, key=lambda i: order[i["level"]])
    return {"score": sitecheck.score(issues), "issues": [{k: i[k] for k in ("level", "id", "title", "fix", "count") if k in i} for i in issues]}


@mcp.tool()
def check_page_file(path: str, address: str = "", security: bool = False) -> dict:
    """Check a saved .html file in the working folder: titles, descriptions, headings, alt text, labels, mixed content, and with security=true forms over http, files from other sites without integrity checks, inline code. Local only, no network. 'address' is the real web address of the page (only needed for the https checks)."""
    f = existing(path)
    html = f.read_text(encoding="utf-8", errors="replace")
    return _report(sitecheck.run_static(html, address or None, security))


@mcp.tool()
def check_site(url: str, security: bool = False) -> dict:
    """Check one live web page of your own: the same checks as check_page_file, plus page weight, compression, speed, heavy images and, with security=true, response headers (HSTS, Content-Security-Policy, framing, nosniff, referrer policy). Fetches only this address. Addresses inside private networks are refused. Use it only on sites you own or may test."""
    try:
        r, body, secs = sitecheck.fetch(url)
    except netguard.Blocked as e:
        raise ToolError(str(e))
    except Exception as e:
        raise ToolError(f"could not load that page: {e}")
    html = body.decode(r.headers.get_content_charset() or "utf-8", "replace")
    final = r.geturl()
    issues = sitecheck.run_static(html, final, security) + sitecheck.run_live(final, len(body), r.headers, secs, html)
    if security:
        issues += sitecheck.run_security_live(final, r.headers)
    out = _report(issues)
    out["checked"] = final
    return out


@mcp.tool()
def project_audit(folder: str = ".") -> dict:
    """Look through a folder (a website or app project) for things that break a privacy-first setup: scripts, styles, fonts or images loaded from other sites, known trackers, text that looks like a key or password (the value is never shown), files over 2 MB, a missing README or LICENSE. Reads files only; skips .git, node_modules and vendor."""
    d = safe(folder)
    if not d.is_dir():
        raise PathError(f"'{folder}' is not a folder here")
    return audit_mod.audit(d)


def main() -> None:
    import sys
    if sys.argv[1:2] == ["setup"]:
        from .setup_cmd import main as setup
        raise SystemExit(setup(sys.argv[2:]))
    mcp.run()


if __name__ == "__main__":
    main()
