# MCP Doc Tools

![MCP Doc Tools](docs/banner.jpg)

> **Test version.** Every tool was tested here through a real MCP client, but the server has not yet been tried inside Claude Desktop or on Windows. The website tools and `doc-tools setup` are new and have only run on Linux. Expect rough edges and please report them.

An [MCP](https://modelcontextprotocol.io) server that gives an AI assistant hands for your documents and your own websites: read a scan, work with PDFs, shrink photos, check a page, audit a project folder. It runs on your computer. Nothing is uploaded, and the assistant can only touch **one folder you choose**.

## Tools

| Tool | What it does |
|---|---|
| `list_files` | PDFs and images in the folder, with sizes |
| `pdf_info` | Pages, size, whether it has selectable text (scan or not) |
| `pdf_text` | Text of a PDF, by page range |
| `pdf_merge` | Join PDFs in a given order |
| `pdf_extract_pages` | Keep only some pages, e.g. `2-4,7` |
| `pdf_compress` | Smaller (150 dpi) or smallest (100 dpi). Says so when a file cannot get smaller |
| `read_text` | OCR for scans, photos and scanned PDFs. Straightens and cleans the page first. English, Portuguese, Russian, Ukrainian and any other Tesseract language |
| `clean_scan` | Straighten a photo and make it black and white |
| `shrink_photo` | Smaller JPEG, HEIC from an iPhone works |
| `check_page_file` | Check a saved `.html` file: titles, headings, alt text, labels, mobile viewport, mixed content. With `security=true` also forms over http, files from other sites without integrity checks, inline code. No network |
| `check_site` | Check one live page of your own: the same, plus page weight, compression, speed, heavy images and (with `security=true`) response headers |
| `project_audit` | Scan a project folder for scripts, fonts and images loaded from other sites, known trackers, text that looks like a key or password (the value is never shown), files over 2 MB, missing README or LICENSE |

The scan clean-up is the same method as in [Local OCR](https://github.com/davydmedvedchuk/local-ocr) (adaptive threshold, then deskew by projection profile).

## Safety rules

- Every path is resolved inside the working folder. `../`, absolute paths and symlinks that point outside are refused, and the assistant sees why.
- Nothing is overwritten. A result gets a new name (`merged.pdf`, then `merged-2.pdf`) and the tool returns it.
- Original files are never changed. There is no delete tool.
- The only network call is `check_site`, and it fetches just the address you give it. Addresses inside private networks (router, other computers, cloud metadata) are refused, also after redirects. `localhost` is allowed so you can check a site you are building. Use it on sites you own or may test.
- `project_audit` only reads files, skips `.git`, `node_modules` and `vendor`, and never prints a secret it finds.

## Install

You need Python 3.10+ and the Tesseract program with the languages you want (`apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-rus`, or `brew install tesseract tesseract-lang`).

```
pip install git+https://github.com/davydmedvedchuk/mcp-doc-tools
doc-tools setup --folder ~/Documents/work
```

`doc-tools setup` adds the server to Claude Desktop's config file for you, with the one folder the assistant may work in. It keeps your other servers, writes a backup (`.bak`) first and refuses to touch a config it cannot read. Add `--print` to only see the result. Restart Claude Desktop afterwards.

## Connect it by hand

If you prefer not to use `doc-tools setup`, add this to `claude_desktop_config.json` (Settings → Developer → Edit config) and restart the app. Put your own folder in `DOC_TOOLS_ROOT`.

```json
{
  "mcpServers": {
    "doc-tools": {
      "command": "doc-tools",
      "env": { "DOC_TOOLS_ROOT": "/Users/you/Documents/scans" }
    }
  }
}
```

If `doc-tools` is not found, use the full path of the command (`which doc-tools`) or `"command": "python3", "args": ["-m", "doc_tools"]`.

Then ask in plain words: *"Check https://my-site.example with security on and list what to fix."*, *"Audit this project folder for trackers and keys."*, *"Read invoice.jpg in Portuguese and tell me the total."* or *"Merge contract.pdf and annex.pdf, then make it smaller."*

## Tests

```
pip install -e ".[test]"
python3 -m pytest tests/                                  # folder guard, never-overwrite, page ranges, network guard, project audit, setup command
DOC_TOOLS_ROOT=/folder/with/samples python3 tests/smoke.py   # starts the real server and calls every tool
```

## Limits

- Website checks find common slips. A clean result does not mean a site is safe. On GitHub Pages the header checks always flag the site, because you cannot set headers there.
- The network guard checks the address before connecting. It cannot stop a name that changes its answer in between (DNS rebinding).
- `sitecheck.py` here is a copy of the one in [Site checker](https://github.com/davydmedvedchuk/site-checker). Fixes have to be copied by hand.

- `pdf_compress` turns pages into images, so the text is no longer selectable. Use `read_text` on the result if you need the words.
- OCR reads printed text. Handwriting and blurry photos come out poorly.
- Password-protected PDFs are refused, not opened.
- Built on the MCP Python SDK 2.x (`mcp.server.mcpserver`).

Made by Davyd Medvedchuk. MIT licence.
