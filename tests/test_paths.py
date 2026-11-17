"""Unit tests for the folder guard. Run: python3 -m pytest tests/"""
import os, pathlib, tempfile
root = pathlib.Path(tempfile.mkdtemp()).resolve()
os.environ["DOC_TOOLS_ROOT"] = str(root)
import pytest
from doc_tools import server as s

def test_inside_ok():
    (root / "a.pdf").write_bytes(b"x")
    assert s.safe("a.pdf") == root / "a.pdf"

@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "sub/../../x", "a/../../.."])
def test_outside_refused(bad):
    with pytest.raises(s.PathError):
        s.safe(bad)

def test_symlink_escape_refused():
    outside = pathlib.Path(tempfile.mkdtemp()) / "secret.txt"; outside.write_text("s")
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(s.PathError):
        s.safe("link.txt")

def test_free_name_never_overwrites():
    p = root / "r.pdf"; p.write_bytes(b"1")
    assert s.free_name(p).name == "r-2.pdf"
    (root / "r-2.pdf").write_bytes(b"2")
    assert s.free_name(p).name == "r-3.pdf"

def test_page_ranges():
    assert s.pages_from("1-3,5", 5) == [0, 1, 2, 4]
    assert s.pages_from("", 3) == [0, 1, 2]
    with pytest.raises(s.PathError):
        s.pages_from("4", 3)
