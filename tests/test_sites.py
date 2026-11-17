"""Tests for the website tools, the project audit, the network guard and the setup command. Run: python3 -m pytest tests/"""
import functools, http.server, json, os, socketserver, threading
from pathlib import Path
import pytest

os.environ.setdefault("DOC_TOOLS_ROOT", ".")


def server_with(handler_cls):
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ---------- network guard ----------
from doc_tools import netguard


@pytest.mark.parametrize("url", ["http://10.0.0.5/", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]:1/x" if False else "http://172.16.0.1/",
                                 "file:///etc/passwd", "ftp://example.com/", "http://user:pass@127.0.0.1/"])
def test_guard_refuses(url):
    with pytest.raises(netguard.Blocked):
        netguard.check_url(url)


def test_guard_allows_localhost():
    assert netguard.check_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/"


def test_redirect_into_private_network_is_refused():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302); self.send_header("Location", "http://169.254.169.254/"); self.end_headers()
        log_message = lambda *a: None
    srv, base = server_with(H)
    from doc_tools import sitecheck
    with pytest.raises(netguard.Blocked):
        sitecheck.fetch(base + "/")
    srv.shutdown()


# ---------- tools ----------
BAD = """<!doctype html><html><head><title>x</title></head><body><h1>Hi</h1>
<script src="https://cdn.example.net/a.js"></script><form action="http://example.com/send"><input name="a"></form>
<a href="https://other.org/" target="_blank">go</a></body></html>"""


def test_check_page_file(tmp_path, monkeypatch):
    import doc_tools.server as srv
    monkeypatch.setattr(srv, "ROOT", tmp_path.resolve())
    (tmp_path / "page.html").write_text(BAD)
    plain = srv.check_page_file("page.html")
    ids_plain = {i["id"] for i in plain["issues"]}
    sec = srv.check_page_file("page.html", address="https://example.com/", security=True)
    ids_sec = {i["id"] for i in sec["issues"]}
    assert not any(i.startswith("sec-") for i in ids_plain)
    assert {"sec-form-http", "sec-no-sri", "sec-blank-rel"} <= ids_sec
    with pytest.raises(Exception):
        srv.check_page_file("../outside.html")


def test_check_site_on_localhost_and_private_refused(tmp_path, monkeypatch):
    import doc_tools.server as srv
    (tmp_path / "index.html").write_text(BAD)
    H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)); H.log_message = lambda *a, **k: None
    s, base = server_with(H)
    r = srv.check_site(base + "/index.html", security=True)
    ids = {i["id"] for i in r["issues"]}
    assert "sec-form-http" in ids and "sec-csp" in ids and r["checked"].startswith(base)
    with pytest.raises(Exception) as e:
        srv.check_site("http://192.168.0.1/")
    assert "private network" in str(e.value)
    s.shutdown()


def test_project_audit(tmp_path, monkeypatch):
    import doc_tools.server as srv
    monkeypatch.setattr(srv, "ROOT", tmp_path.resolve())
    (tmp_path / "index.html").write_text('<link href="https://fonts.googleapis.com/css2?family=X" rel="stylesheet">\n<script src="https://www.googletagmanager.com/gtag/js"></script>\n<a href="https://github.com/me">me</a>\n')
    (tmp_path / "app.js").write_text('const apiKey = "abcd1234efgh5678ijkl";\nconst t = "ghp_' + "a" * 36 + '";\n')
    (tmp_path / "vendor").mkdir(); (tmp_path / "vendor" / "lib.js").write_text('src="https://cdn.example.net/x.js"')
    r = srv.project_audit(".")
    kinds = {(f["kind"], f["file"]) for f in r["findings"]}
    assert ("tracker", "index.html") in kinds and ("other site", "index.html") in kinds
    assert ("possible secret", "app.js") in kinds
    assert ("missing", ".") in kinds                                        # no README / LICENSE
    assert not any(f["file"].startswith("vendor") for f in r["findings"])   # vendor skipped
    assert not any("github.com" in f["detail"] for f in r["findings"])      # a plain link is not a load
    assert "abcd1234efgh5678ijkl" not in json.dumps(r) and "ghp_aaaa" not in json.dumps(r)   # secret values are never shown
    with pytest.raises(Exception):
        srv.project_audit("../")


# ---------- setup command ----------
from doc_tools import setup_cmd


def test_setup_keeps_other_servers_and_makes_backup(tmp_path, capsys):
    cfg = tmp_path / "c" / "claude_desktop_config.json"; cfg.parent.mkdir()
    cfg.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    work = tmp_path / "docs"; work.mkdir()
    assert setup_cmd.main(["--folder", str(work), "--config", str(cfg)]) == 0
    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark" and data["mcpServers"]["other"] == {"command": "x"}
    e = data["mcpServers"]["doc-tools"]
    assert e["args"] == ["-m", "doc_tools"] and e["env"]["DOC_TOOLS_ROOT"] == str(work.resolve())
    assert json.loads(cfg.with_name(cfg.name + ".bak").read_text())["mcpServers"] == {"other": {"command": "x"}}
    assert setup_cmd.main(["--folder", str(work), "--config", str(cfg)]) == 0      # running twice changes nothing else
    assert list(json.loads(cfg.read_text())["mcpServers"]) == ["other", "doc-tools"]


def test_setup_refuses_broken_config_and_missing_folder(tmp_path):
    cfg = tmp_path / "bad.json"; cfg.write_text("{ not json")
    assert setup_cmd.main(["--folder", str(tmp_path), "--config", str(cfg)]) == 2
    assert cfg.read_text() == "{ not json"                                           # untouched
    assert setup_cmd.main(["--folder", str(tmp_path / "nope"), "--config", str(tmp_path / "x.json")]) == 2


def test_setup_print_changes_nothing(tmp_path, capsys):
    cfg = tmp_path / "x.json"
    assert setup_cmd.main(["--folder", str(tmp_path), "--config", str(cfg), "--print"]) == 0
    assert not cfg.exists() and "doc-tools" in capsys.readouterr().out
