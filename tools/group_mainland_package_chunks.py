"""Group package parts into independently downloadable, bounded artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PART_PREFIX = "Phase1-Mainland-Windows-Tools.zip.part-"
MAX_PARTS = 48
MAX_GROUP_BYTES = 80 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def group_chunks(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    groups: int = 8,
    max_group_bytes: int = MAX_GROUP_BYTES,
) -> dict:
    source = Path(input_dir)
    destination = Path(output_dir)
    if groups < 2 or groups > 8:
        raise ValueError("分组数量必须在 2 至 8 之间")
    if max_group_bytes <= 0:
        raise ValueError("单组最大字节数必须大于 0")
    parts = []
    for path in source.glob(PART_PREFIX + "*"):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"分片不是普通文件：{path.name}")
        suffix = path.name[len(PART_PREFIX):]
        if not suffix.isdigit():
            raise ValueError(f"分片编号无效：{path.name}")
        parts.append((int(suffix), path))
    parts.sort(key=lambda item: item[0])
    if len(parts) < groups or len(parts) > MAX_PARTS:
        raise ValueError(f"分片数量必须在 {groups} 至 {MAX_PARTS} 之间，当前为 {len(parts)}")
    if [index for index, _ in parts] != list(range(len(parts))):
        raise ValueError("分片编号必须从 00 连续递增，不能缺失或重复")
    if any(path.stat().st_size <= 0 for _, path in parts):
        raise ValueError("分片不能为空")

    destination.mkdir(parents=True, exist_ok=True)
    per_group = (len(parts) + groups - 1) // groups
    result_groups = []
    for group_index in range(groups):
        start = group_index * per_group
        selected = parts[start:start + per_group]
        if not selected:
            raise ValueError("分组后出现空分片组")
        selected_bytes = sum(path.stat().st_size for _, path in selected)
        if selected_bytes > max_group_bytes:
            raise ValueError(
                f"分片组超过最大字节限制：group-{group_index + 1:02d} "
                f"{selected_bytes} > {max_group_bytes}"
            )
        group_dir = destination / f"group-{group_index + 1:02d}"
        group_dir.mkdir(parents=True, exist_ok=True)
        for stale in group_dir.glob(PART_PREFIX + "*"):
            if stale.is_file() and not stale.is_symlink():
                stale.unlink()
        entries = []
        for _, original in selected:
            target = group_dir / original.name
            shutil.copyfile(original, target)
            if target.stat().st_size != original.stat().st_size or _sha256(target) != _sha256(original):
                raise ValueError(f"分片复制校验失败：{original.name}")
            entries.append({
                "name": target.name,
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            })
        result_groups.append({
            "name": group_dir.name,
            "bytes": sum(entry["bytes"] for entry in entries),
            "parts": entries,
        })

    manifest = {
        "source": str(source.resolve()),
        "part_count": len(parts),
        "group_count": groups,
        "max_group_bytes": max_group_bytes,
        "groups": result_groups,
    }
    (destination / "chunk-groups.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="将客户 ZIP 分片分组为可独立下载的 Actions artifacts")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--groups", type=int, default=8)
    parser.add_argument("--max-group-bytes", type=int, default=MAX_GROUP_BYTES)
    args = parser.parse_args()
    result = group_chunks(
        args.input_dir, args.output_dir, groups=args.groups,
        max_group_bytes=args.max_group_bytes,
    )
    print(
        "MAINLAND_PACKAGE_CHUNK_GROUPING_OK "
        f"groups={result['group_count']} parts={result['part_count']} "
        f"bytes={[group['bytes'] for group in result['groups']]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
