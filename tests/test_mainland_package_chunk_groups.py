import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "group_mainland_package_chunks.py"
SPEC = importlib.util.spec_from_file_location("group_mainland_package_chunks", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_group_chunks_creates_two_ordered_independent_download_sets(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    contents = [bytes([index]) * (index + 1) for index in range(5)]
    for index, content in enumerate(contents):
        (source / f"{MODULE.PART_PREFIX}{index:02d}").write_bytes(content)

    output = tmp_path / "grouped"
    result = MODULE.group_chunks(source, output, groups=2)

    assert result["part_count"] == 5
    assert result["group_count"] == 2
    assert [len(group["parts"]) for group in result["groups"]] == [3, 2]
    for group in result["groups"]:
        for item in group["parts"]:
            copied = output / group["name"] / item["name"]
            assert copied.stat().st_size == item["bytes"]
            assert MODULE._sha256(copied) == item["sha256"]
    assert (output / "chunk-groups.json").is_file()


def test_group_chunks_rejects_missing_or_non_contiguous_parts(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    (source / f"{MODULE.PART_PREFIX}00").write_bytes(b"first")
    (source / f"{MODULE.PART_PREFIX}02").write_bytes(b"third")
    with pytest.raises(ValueError, match="连续递增"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=2)


def test_group_chunks_rejects_empty_parts_and_invalid_group_count(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    (source / f"{MODULE.PART_PREFIX}00").write_bytes(b"")
    (source / f"{MODULE.PART_PREFIX}01").write_bytes(b"second")
    with pytest.raises(ValueError, match="不能为空"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=2)
    with pytest.raises(ValueError, match="2 至 8"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=1)


def test_group_chunks_rejects_directory_entries(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    (source / f"{MODULE.PART_PREFIX}00").mkdir()
    (source / f"{MODULE.PART_PREFIX}01").write_bytes(b"second")
    with pytest.raises(ValueError, match="不是普通文件"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=2)


def test_workflow_uploads_bounded_chunk_groups_and_keeps_full_package_manifest():
    workflow = (ROOT / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "tools/group_mainland_package_chunks.py" in workflow
    assert "mainland-phase1-package-parts-01" in workflow
    assert "--groups 8" in workflow
    assert "--max-group-bytes 125829120" in workflow
    for index in range(1, 9):
        suffix = f"{index:02d}"
        assert f"mainland-phase1-package-parts-{suffix}" in workflow
        assert f"release/package-chunks/group-{suffix}/*" in workflow



def test_group_chunks_creates_eight_download_groups_under_size_limit(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    for index in range(33):
        (source / f"{MODULE.PART_PREFIX}{index:02d}").write_bytes(bytes([index]) * 1024)

    output = tmp_path / "grouped"
    result = MODULE.group_chunks(source, output, groups=8, max_group_bytes=5 * 1024)

    assert result["part_count"] == 33
    assert result["group_count"] == 8
    assert result["max_group_bytes"] == 5 * 1024
    assert [len(group["parts"]) for group in result["groups"]] == [5, 5, 5, 5, 5, 5, 5, 3]
    assert all(group["bytes"] <= result["max_group_bytes"] for group in result["groups"])


def test_group_chunks_rejects_group_that_exceeds_download_limit(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    sizes = [3, 3, 1, 1]
    for index, size in enumerate(sizes):
        (source / f"{MODULE.PART_PREFIX}{index:02d}").write_bytes(bytes([index]) * size)

    with pytest.raises(ValueError, match="超过最大字节限制"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=2, max_group_bytes=5)


def test_group_chunks_rejects_non_positive_group_size_limit(tmp_path):
    source = tmp_path / "parts"
    source.mkdir()
    for index in range(2):
        (source / f"{MODULE.PART_PREFIX}{index:02d}").write_bytes(b"x")
    with pytest.raises(ValueError, match="必须大于 0"):
        MODULE.group_chunks(source, tmp_path / "grouped", groups=2, max_group_bytes=0)
