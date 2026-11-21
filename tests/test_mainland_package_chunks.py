import hashlib
from pathlib import Path
import importlib.util
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "split_mainland_package.py"
SPEC = importlib.util.spec_from_file_location("split_mainland_package", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_customer_package_fits_bounded_48_chunk_capacity():
    # The 35-business-tool candidate exceeds the previous 24-chunk ceiling.
    # Keep 20 MiB chunks but allow a bounded 48-part package for future growth.
    assert MODULE.chunk_count(558_312_237) == 27
    assert MODULE.chunk_count(25 * MODULE.CHUNK_SIZE_BYTES) == 25
    assert MODULE.chunk_count(48 * MODULE.CHUNK_SIZE_BYTES) == 48
    assert MODULE.chunk_count(48 * MODULE.CHUNK_SIZE_BYTES + 1) == 49
    assert MODULE.MAX_CHUNKS == 48


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
    assert "--max-chunks 48" in workflow
    assert "tools/group_mainland_package_chunks.py" in workflow
    assert "mainland-phase1-package-parts-01" in workflow
    assert "mainland-phase1-package-parts-02" in workflow
    assert "release/package-chunks/group-01/*" in workflow
    assert "release/package-chunks/group-02/*" in workflow
