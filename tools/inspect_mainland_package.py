"""Validate the customer ZIP before it is uploaded as a release artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED_ROOT_FILES = {
    "package/README-大陆版.md",
    "package/套餐说明.txt",
    "package/分类套餐目录.md",
    "package/说明书/README.md",
}
SERIES_LABELS = tuple(f"系列 {letter}" for letter in "ABCDEF")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_package(path: str | Path, *, expected_exes: int = 22, expected_manuals: int = 22) -> dict:
    archive_path = Path(path)
    if not archive_path.is_file():
        raise ValueError(f"客户 ZIP 不存在：{archive_path}")

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        normalized_names = set()
        reserved_names = {"CON", "PRN", "AUX", "NUL"} | {
            f"COM{number}" for number in range(1, 10)
        } | {f"LPT{number}" for number in range(1, 10)}
        for info in infos:
            name = info.filename
            is_directory = info.is_dir()
            raw_parts = name.split("/")
            if is_directory and raw_parts and raw_parts[-1] == "":
                raw_parts = raw_parts[:-1]
            if (
                not name
                or "\x00" in name
                or "\\" in name
                or not raw_parts
                or any(part in {"", ".", ".."} for part in raw_parts)
            ):
                raise ValueError(f"客户 ZIP 存在不安全路径：{name}")
            member = PurePosixPath(name)
            if member.is_absolute():
                raise ValueError(f"客户 ZIP 存在不安全路径：{name}")
            for part in raw_parts:
                device_stem = part.split(".", 1)[0].rstrip(" .").upper()
                if (
                    ":" in part
                    or part.endswith((" ", "."))
                    or device_stem in reserved_names
                ):
                    raise ValueError(f"客户 ZIP 存在不安全路径：{name}")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(unix_mode)
            if stat.S_ISLNK(unix_mode) or file_type not in {
                0, stat.S_IFREG, stat.S_IFDIR
            }:
                raise ValueError(f"客户 ZIP 存在不安全路径或特殊文件：{name}")
            normalized = "/".join(
                unicodedata.normalize("NFC", part).rstrip(" .").casefold()
                for part in raw_parts
            )
            if normalized in normalized_names:
                raise ValueError(f"客户 ZIP 存在重复或 Windows 路径冲突：{name}")
            normalized_names.add(normalized)
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"客户 ZIP CRC 校验失败：{bad_member}")

        files = [item for item in infos if not item.is_dir()]
        exes = sorted(
            item.filename for item in files
            if item.filename.startswith("package/") and item.filename.count("/") == 1
            and item.filename.lower().endswith(".exe")
        )
        manuals = sorted(
            item.filename for item in files
            if item.filename.startswith("package/说明书/") and item.filename.count("/") == 2
            and item.filename.lower().endswith(".md") and not item.filename.endswith("/README.md")
        )
        if len(exes) != expected_exes:
            raise ValueError(f"EXE 数量不符：期望 {expected_exes}，实际 {len(exes)}")
        if len(manuals) != expected_manuals:
            raise ValueError(f"产品说明书数量不符：期望 {expected_manuals}，实际 {len(manuals)}")

        missing = sorted(REQUIRED_ROOT_FILES - set(names))
        if missing:
            raise ValueError("客户 ZIP 缺少交付文档：" + "、".join(missing))
        for name in exes + manuals:
            info = archive.getinfo(name)
            if info.file_size <= 0:
                raise ValueError(f"客户 ZIP 中存在空 EXE 或说明书：{name}")

        description = archive.read("package/套餐说明.txt").decode("utf-8-sig")
        catalog = archive.read("package/分类套餐目录.md").decode("utf-8-sig")
        combined = description + "\n" + catalog
        missing_series = [label for label in SERIES_LABELS if label not in combined]
        if missing_series:
            raise ValueError("套餐目录缺少系列说明：" + "、".join(missing_series))
        if "待市场验证" not in combined:
            raise ValueError("套餐说明必须明确标注建议售价尚待市场验证")

        timestamps = sorted({item.date_time for item in files})
        timestamp_text = lambda value: (
            f"{value[0]:04d}-{value[1]:02d}-{value[2]:02d} "
            f"{value[3]:02d}:{value[4]:02d}:{value[5]:02d}"
        )
        return {
            "archive": archive_path.name,
            "size_bytes": archive_path.stat().st_size,
            "sha256": _sha256(archive_path),
            "crc": "passed",
            "entry_count": len(infos),
            "file_count": len(files),
            "exe_count": len(exes),
            "manual_count": len(manuals),
            "executables": exes,
            "manuals": manuals,
            "bundle_descriptions": [
                line.strip() for line in description.splitlines()
                if line.strip().startswith("系列 ")
            ],
            "bundle_catalog": [
                line.strip() for line in catalog.splitlines()
                if line.strip().startswith("|")
            ],
            "timestamp_min": timestamp_text(timestamps[0]) if timestamps else None,
            "timestamp_max": timestamp_text(timestamps[-1]) if timestamps else None,
            "timestamp_distinct_count": len(timestamps),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the Mainland Phase 1 customer ZIP.")
    parser.add_argument("--package", required=True, help="Path to Phase1-Mainland-Windows-Tools.zip")
    parser.add_argument("--expected-exes", type=int, default=22)
    parser.add_argument("--expected-manuals", type=int, default=22)
    parser.add_argument("--report", required=True, help="Write the JSON inspection report to this path")
    args = parser.parse_args()
    try:
        report = inspect_package(
            args.package,
            expected_exes=args.expected_exes,
            expected_manuals=args.expected_manuals,
        )
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("MAINLAND_PACKAGE_INSPECTION_OK")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, zipfile.BadZipFile, ValueError) as exc:
        print(f"MAINLAND_PACKAGE_INSPECTION_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
