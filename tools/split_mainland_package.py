"""Create bounded, checksummed download chunks for the mainland customer ZIP."""
from __future__ import annotations

import argparse
import hashlib
import math
import os
from pathlib import Path
import tempfile

CHUNK_SIZE_BYTES = 20 * 1024 * 1024
MAX_CHUNKS = 48


def chunk_count(size_bytes: int, chunk_size: int = CHUNK_SIZE_BYTES) -> int:
    if size_bytes < 0:
        raise ValueError("文件大小不能为负数")
    if chunk_size <= 0:
        raise ValueError("分片大小必须大于 0")
    return math.ceil(size_bytes / chunk_size)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def split_package(
    package: str | Path,
    output_dir: str | Path,
    *,
    chunk_size: int = CHUNK_SIZE_BYTES,
    max_chunks: int = MAX_CHUNKS,
) -> dict:
    source_path = Path(package)
    destination = Path(output_dir)
    if not source_path.is_file():
        raise ValueError(f"客户 ZIP 不存在：{source_path}")
    size_bytes = source_path.stat().st_size
    if size_bytes <= 0:
        raise ValueError("客户 ZIP 不能为空")
    if max_chunks <= 0:
        raise ValueError("分片数量上限必须大于 0")
    count = chunk_count(size_bytes, chunk_size)
    if count > max_chunks:
        raise ValueError(
            f"客户包需要 {count} 个分片，超过上限 {max_chunks} 个；"
            f"当前单片大小为 {chunk_size} bytes"
        )

    destination.mkdir(parents=True, exist_ok=True)
    prefix = source_path.name
    expected_parts = [destination / f"{prefix}.part-{index:02d}" for index in range(count)]
    temporary_parts: list[Path] = []
    digest = _sha256(source_path)
    try:
        with source_path.open("rb") as source:
            for part_path in expected_parts:
                fd, temp_name = tempfile.mkstemp(
                    prefix=f".{part_path.name}.", suffix=".tmp", dir=destination
                )
                temp_path = Path(temp_name)
                temporary_parts.append(temp_path)
                remaining = chunk_size
                with os.fdopen(fd, "wb") as target:
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            break
                        target.write(block)
                        remaining -= len(block)
                    target.flush()
                    os.fsync(target.fileno())
                if temp_path.stat().st_size == 0:
                    raise ValueError(f"生成了空分片：{part_path.name}")
        for temp_path, part_path in zip(temporary_parts, expected_parts):
            os.replace(temp_path, part_path)
        temporary_parts.clear()

        # Remove only stale chunks sharing this exact generated filename prefix.
        expected_set = set(expected_parts)
        for stale in destination.glob(f"{prefix}.part-*"):
            if stale not in expected_set and stale.is_file():
                stale.unlink()

        (destination / f"{prefix}.sha256").write_text(
            f"{digest}  {prefix}\n", encoding="utf-8", newline="\n"
        )
        (destination / f"{prefix}.bytes").write_text(
            f"{size_bytes}\n", encoding="ascii", newline="\n"
        )
        size_label = "20MiB" if chunk_size == CHUNK_SIZE_BYTES else f"{chunk_size}B"
        manifest = (
            f"file={prefix}\n"
            f"bytes={size_bytes}\n"
            f"sha256={digest}\n"
            f"parts={count}\n"
            f"part_size={size_label}\n"
            f"max_parts={max_chunks}\n"
        )
        _atomic_text(destination / f"{prefix}.manifest.txt", manifest)
    except Exception:
        for temp_path in temporary_parts:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
        raise

    return {
        "file": prefix,
        "bytes": size_bytes,
        "sha256": digest,
        "parts": count,
        "part_size_bytes": chunk_size,
        "part_paths": [str(path) for path in expected_parts],
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将客户 ZIP 拆分为带 SHA256 清单的有限大小分片")
    parser.add_argument("--package", required=True, help="待拆分的客户 ZIP")
    parser.add_argument("--output-dir", required=True, help="分片和清单输出目录")
    parser.add_argument("--chunk-size-bytes", type=int, default=CHUNK_SIZE_BYTES)
    parser.add_argument("--max-chunks", type=int, default=MAX_CHUNKS)
    args = parser.parse_args()
    result = split_package(
        args.package,
        args.output_dir,
        chunk_size=args.chunk_size_bytes,
        max_chunks=args.max_chunks,
    )
    print(
        "MAINLAND_PACKAGE_CHUNKING_OK "
        f"parts={result['parts']} bytes={result['bytes']} sha256={result['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
