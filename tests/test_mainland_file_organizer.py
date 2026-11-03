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

def test_recursive_keeps_user_named_category_folder_and_skips_tool_output():
    m=load()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        user_folder=p/"项目资料"/"图片"
        user_folder.mkdir(parents=True)
        (user_folder/"nested.jpg").write_bytes(b"image")
        (p/"图片").mkdir()
        (p/"图片"/"already_sorted.jpg").write_bytes(b"sorted")
        (p/m.LOG_NAME).write_text('{"moves":[]}',encoding="utf-8")
        found=list(m.iter_files(p,recursive=True))
        assert user_folder/"nested.jpg" in found
        assert p/"图片"/"already_sorted.jpg" not in found
        assert p/m.LOG_NAME not in found

def test_repeated_organize_does_not_move_its_own_log():
    m=load()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        (p/"first.jpg").write_bytes(b"1")
        first=m.organize(p)
        assert len(first)==1
        assert (p/m.LOG_NAME).exists()
        second=m.organize(p)
        assert second==[]
        assert (p/m.LOG_NAME).exists()
        assert not (p/"其他"/m.LOG_NAME).exists()

def test_recursive_organize_and_undo_restore_nested_source():
    m=load()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        nested=p/"客户A"/"资料"
        nested.mkdir(parents=True)
        source=nested/"contract.pdf"
        source.write_bytes(b"pdf")
        moved=m.organize(p,recursive=True)
        assert len(moved)==1
        assert (p/"文档"/"contract.pdf").exists()
        assert m.undo(p)==1
        assert source.exists()
        assert not (p/"文档"/"contract.pdf").exists()
