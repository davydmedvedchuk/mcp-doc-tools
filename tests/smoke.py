"""Starts the real server over stdio and calls every tool the way an assistant would.
    DOC_TOOLS_ROOT=/some/folder python3 tests/smoke.py   (folder needs a few sample files, see below)
"""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.environ.get("DOC_TOOLS_ROOT", ".")

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "doc_tools"], env={**os.environ, "DOC_TOOLS_ROOT": ROOT})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])
            async def call(name, **a):
                res = await s.call_tool(name, a)
                txt = " ".join(c.text for c in res.content if hasattr(c, "text"))
                print(("ERR " if res.is_error else "OK  ") + name, txt[:300].replace("\n", " | "))
                return res
            await call("list_files")
            await call("pdf_info", path="demo-invoice.pdf")
            await call("pdf_info", path="scan_ru.pdf")
            await call("pdf_text", path="demo-invoice.pdf", pages="1")
            await call("pdf_merge", paths=["demo-invoice.pdf", "scan_ru.pdf"])
            await call("pdf_merge", paths=["demo-invoice.pdf", "scan_ru.pdf"])      # must not overwrite
            await call("pdf_extract_pages", path="merged.pdf", pages="1-2")
            await call("pdf_compress", path="demo-invoice.pdf", quality="smallest")
            await call("read_text", path="skew_en.jpg", language="eng")
            await call("read_text", path="scan_ru.pdf", language="rus")
            await call("clean_scan", path="skew_en.jpg")
            await call("shrink_photo", path="photo.heic", max_side=800)
            print("--- should be refused ---")
            await call("pdf_info", path="../secret.txt")
            await call("pdf_info", path="/etc/passwd")
            await call("pdf_extract_pages", path="merged.pdf", pages="9-12")
asyncio.run(main())
