from pathlib import Path
import importlib.util
import tempfile

def load():
    path=Path("apps/文件整理助手Pro.py")
    spec=importlib.util.spec_from_file_location("file_organizer", path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_category_and_organize():
    m=load()
    assert m.category(Path("a.jpg"))=="图片"
    assert m.category(Path("a.pdf"))=="文档"
    assert m.category(Path("a.unknown"))=="其他"
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        (p/"a.jpg").write_bytes(b"x")
        (p/"b.pdf").write_bytes(b"x")
        moved=m.organize(p)
        assert len(moved)==2
        assert (p/"图片/a.jpg").exists()
        assert (p/"文档/b.pdf").exists()
