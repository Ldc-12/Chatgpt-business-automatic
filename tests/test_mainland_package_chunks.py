import hashlib
from pathlib import Path
import importlib.util
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "split_mainland_package.py"
SPEC = importlib.util.spec_from_file_location("split_mainland_package", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_customer_package_fits_bounded_24_chunk_capacity():
    # The 2026-11-16 PR package is 425,249,695 bytes. A 20 MiB limit
    # therefore needs 21 chunks, not the old 20-chunk ceiling.
    assert MODULE.chunk_count(425_249_695) == 21
    assert MODULE.chunk_count(24 * MODULE.CHUNK_SIZE_BYTES) == 24
    assert MODULE.chunk_count(24 * MODULE.CHUNK_SIZE_BYTES + 1) == 25


def test_split_package_writes_ordered_chunks_and_sha256_manifest(tmp_path):
    source = tmp_path / "Phase1-Mainland-Windows-Tools.zip"
    source.write_bytes(bytes(range(256)) * 3)
    output = tmp_path / "release"

    result = MODULE.split_package(source, output, chunk_size=300, max_chunks=3)

    assert result["parts"] == 3
    assert [Path(path).read_bytes() for path in result["part_paths"]] == [
        source.read_bytes()[0:300],
        source.read_bytes()[300:600],
        source.read_bytes()[600:],
    ]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["sha256"] == digest
    assert (output / f"{source.name}.sha256").read_text(encoding="utf-8").startswith(digest)
    assert (output / f"{source.name}.bytes").read_text(encoding="ascii").strip() == str(source.stat().st_size)
    manifest = (output / f"{source.name}.manifest.txt").read_text(encoding="utf-8")
    assert "parts=3" in manifest
    assert "max_parts=3" in manifest
    assert f"sha256={digest}" in manifest


def test_split_package_rejects_over_limit_before_creating_chunks(tmp_path):
    source = tmp_path / "too-large.zip"
    source.write_bytes(b"x" * 11)
    output = tmp_path / "release"

    try:
        MODULE.split_package(source, output, chunk_size=5, max_chunks=2)
    except ValueError as exc:
        assert "超过上限" in str(exc)
    else:
        raise AssertionError("oversized package should be rejected")
    assert not list(output.glob("*.part-*"))


def test_split_package_removes_stale_chunks_from_previous_larger_package(tmp_path):
    source = tmp_path / "customer.zip"
    source.write_bytes(b"abcdefghij")
    output = tmp_path / "release"
    output.mkdir()
    (output / "customer.zip.part-99").write_bytes(b"stale")

    MODULE.split_package(source, output, chunk_size=4, max_chunks=3)

    assert not (output / "customer.zip.part-99").exists()
    assert sorted(path.name for path in output.glob("customer.zip.part-*")) == [
        "customer.zip.part-00",
        "customer.zip.part-01",
        "customer.zip.part-02",
    ]


def test_workflow_uses_the_tested_chunker_and_keeps_downloads_bounded():
    workflow = (ROOT / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "tests/test_mainland_package_chunks.py" in workflow
    assert "tools/split_mainland_package.py" in workflow
    assert "--max-chunks 24" in workflow
    assert "release/Phase1-Mainland-Windows-Tools.zip.part-*" in workflow
