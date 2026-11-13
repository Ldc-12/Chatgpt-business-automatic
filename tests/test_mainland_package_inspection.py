import importlib.util
import stat
import struct
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "inspect_mainland_package.py"
SPEC = importlib.util.spec_from_file_location("inspect_mainland_package", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_package(path, *, exe_count=22, manual_count=22, include_series=True):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for index in range(exe_count):
            archive.writestr(f"package/Tool{index:02d}.exe", b"MZ" + bytes([index]))
        for index in range(manual_count):
            archive.writestr(
                f"package/说明书/{index:02d}-产品-用户说明书.md",
                f"# 产品 {index}\n说明书内容\n".encode("utf-8"),
            )
        archive.writestr("package/说明书/README.md", b"# Manual index\n")
        archive.writestr("package/README-大陆版.md", b"# Mainland package\n")
        archive.writestr("package/分类套餐目录.md", b"\n".join(
            f"系列 {letter}".encode("utf-8") for letter in ("ABCDEF" if include_series else "A")
        ) if include_series else "系列 A".encode("utf-8"))
        archive.writestr(
            "package/套餐说明.txt",
            ("\n".join(f"系列 {letter}｜建议售价 29.9 元" for letter in ("ABCDEF" if include_series else "A"))
             + "\n以上均为待市场验证的建议售价。").encode("utf-8"),
        )


def test_inspector_reports_counts_crc_hash_bundle_labels_and_timestamps(tmp_path):
    package = tmp_path / "customer.zip"
    make_package(package)
    report = MODULE.inspect_package(package)
    assert report["crc"] == "passed"
    assert report["exe_count"] == 22
    assert report["manual_count"] == 22
    assert report["entry_count"] == 48
    assert len(report["executables"]) == 22
    assert len(report["manuals"]) == 22
    assert len(report["sha256"]) == 64
    assert report["bundle_descriptions"] == [
        f"系列 {letter}｜建议售价 29.9 元" for letter in "ABCDEF"
    ]
    assert report["timestamp_min"] is not None
    assert report["timestamp_max"] is not None


@pytest.mark.parametrize(
    ("exe_count", "manual_count", "message"),
    [
        (21, 22, "EXE 数量不符"),
        (22, 21, "产品说明书数量不符"),
    ],
)
def test_inspector_rejects_missing_exes_or_manuals(tmp_path, exe_count, manual_count, message):
    package = tmp_path / "wrong-count.zip"
    make_package(package, exe_count=exe_count, manual_count=manual_count)
    with pytest.raises(ValueError, match=message):
        MODULE.inspect_package(package)


def test_inspector_rejects_missing_series_description(tmp_path):
    package = tmp_path / "missing-series.zip"
    make_package(package, include_series=False)
    with pytest.raises(ValueError, match="套餐目录缺少系列说明"):
        MODULE.inspect_package(package)


def test_inspector_rejects_unsafe_archive_path(tmp_path):
    package = tmp_path / "unsafe.zip"
    make_package(package)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("package/../outside.txt", b"unsafe")
    with pytest.raises(ValueError, match="不安全路径"):
        MODULE.inspect_package(package)


def test_inspector_rejects_crc_corruption(tmp_path):
    package = tmp_path / "corrupt.zip"
    make_package(package)
    data = bytearray(package.read_bytes())
    with zipfile.ZipFile(package) as archive:
        info = archive.getinfo("package/Tool00.exe")
    header = struct.unpack_from("<IHHHHHIIIHH", data, info.header_offset)
    data_offset = info.header_offset + 30 + header[9] + header[10]
    data[data_offset] ^= 0x01
    package.write_bytes(data)
    with pytest.raises(ValueError, match="CRC 校验失败"):
        MODULE.inspect_package(package)



@pytest.mark.parametrize(
    "unsafe_name",
    [
        "C:/outside.txt",
        "package\\outside.txt",
        "package/readme.txt:payload",
        "package/trailing-dot./file.txt",
        "package/CON.txt",
    ],
)
def test_inspector_rejects_windows_unsafe_paths(tmp_path, unsafe_name):
    package = tmp_path / "windows-unsafe.zip"
    make_package(package)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr(unsafe_name, b"unsafe")
    with pytest.raises(ValueError, match="不安全路径"):
        MODULE.inspect_package(package)


def test_inspector_rejects_case_insensitive_path_collisions(tmp_path):
    package = tmp_path / "case-collision.zip"
    make_package(package)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("package/tool00.EXE", b"MZduplicate")
    with pytest.raises(ValueError, match="Windows 路径冲突"):
        MODULE.inspect_package(package)


def test_inspector_rejects_unicode_normalization_collisions(tmp_path):
    package = tmp_path / "unicode-collision.zip"
    make_package(package)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("package/cafe\u0301.txt", b"one")
        archive.writestr("package/caf\u00e9.txt", b"two")
    with pytest.raises(ValueError, match="Windows 路径冲突"):
        MODULE.inspect_package(package)


def test_inspector_rejects_symbolic_link_entries(tmp_path):
    package = tmp_path / "symlink.zip"
    make_package(package)
    link = zipfile.ZipInfo("package/link.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr(link, "target.txt")
    with pytest.raises(ValueError, match="特殊文件"):
        MODULE.inspect_package(package)
