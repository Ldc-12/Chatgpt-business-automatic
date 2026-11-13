import csv
import importlib.util
import os
from pathlib import Path

import pytest
p=Path(__file__).resolve().parents[1]/"apps"/"轻量销售客户跟进工具.py"
s=importlib.util.spec_from_file_location("sales",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
def test_sales_helpers():
    assert m.num("￥1,200")==1200
    assert m.today()
    assert "客户" in m.FIELDS

def sample_customer(**overrides):
    row = {field: "" for field in m.FIELDS}
    row.update({"客户": "测试客户", "阶段": "新线索", "预计金额": "1200"})
    row.update(overrides)
    return row


def test_sales_json_backup_roundtrip(tmp_path):
    source = tmp_path / "sales.json"
    backup = tmp_path / "sales-backup.json"
    rows = [sample_customer(联系人="张先生", 备注="年度续约")]
    m.save_rows(source, rows)
    loaded = m.load_rows(source)
    assert loaded == rows

    m.save_rows(backup, loaded)
    assert m.load_rows(backup) == rows


def test_sales_json_rejects_corrupt_or_incomplete_data(tmp_path):
    source = tmp_path / "sales.json"
    source.write_text('{"not": "a list"}', encoding="utf-8")
    try:
        m.load_rows(source)
    except ValueError as exc:
        assert "顶层必须是记录列表" in str(exc)
    else:
        raise AssertionError("corrupt backup was accepted")

    source.write_text('[{"客户": "不完整"}]', encoding="utf-8")
    try:
        m.load_rows(source)
    except ValueError as exc:
        assert "缺少字段" in str(exc)
    else:
        raise AssertionError("incomplete record was accepted")


def test_sales_json_failed_save_preserves_previous_file(tmp_path):
    source = tmp_path / "sales.json"
    m.save_rows(source, [sample_customer()])
    original = source.read_bytes()
    try:
        m.save_rows(source, [{"客户": "缺少字段"}])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid rows were saved")
    assert source.read_bytes() == original


def test_sales_json_rejects_invalid_amount(tmp_path):
    try:
        m.validate_rows([sample_customer(预计金额="not-a-number")])
    except ValueError as exc:
        assert "预计金额无效" in str(exc)
    else:
        raise AssertionError("invalid amount was accepted")



def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def test_sales_csv_export_is_formula_safe_atomic_and_roundtrips(tmp_path):
    row = sample_customer(
        客户=' =HYPERLINK("https://example.invalid")',
        备注=chr(9) + "+CMD|' /C calc'!A0",
    )
    target = tmp_path / "exports" / "sales.csv"

    m.export_csv(target, [row])

    raw = target.read_bytes()
    assert raw.startswith(bytes((0xEF, 0xBB, 0xBF)))
    with target.open(encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["客户"].startswith("'")
    assert exported["备注"].startswith("'")
    assert m.read_csv_rows(target) == [row]


def test_sales_csv_export_preserves_existing_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "sales.csv"
    target.write_bytes(b"previous-valid-csv")

    def fail_replace(source, destination):
        raise OSError("simulated CSV replace failure")

    monkeypatch.setattr(m.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated CSV replace failure"):
        m.export_csv(target, [sample_customer()])

    assert target.read_bytes() == b"previous-valid-csv"
    assert list(tmp_path.glob("sales.csv*.tmp")) == []


@pytest.mark.parametrize(
    ("headers", "rows", "message"),
    [
        (m.FIELDS + ["额外字段"], [[*[""] * len(m.FIELDS), "ignored"]], "未支持字段"),
        (m.FIELDS + ["客户"], [[*[""] * (len(m.FIELDS) + 1)]], "重复字段名"),
        (m.FIELDS, [[*[""] * (len(m.FIELDS) + 1)]], "多余列"),
        (m.FIELDS, [["客户", *[""] * (len(m.FIELDS) - 2)]], "字段数量不足"),
    ],
)
def test_sales_csv_import_rejects_ambiguous_or_malformed_rows(tmp_path, headers, rows, message):
    path = tmp_path / "bad.csv"
    write_csv(path, headers, rows)
    with pytest.raises(ValueError, match=message):
        m.read_csv_rows(path)


def test_sales_csv_import_rejects_non_finite_amounts(tmp_path):
    for amount in ("NaN", "Infinity", "-Infinity"):
        path = tmp_path / f"{amount}.csv"
        write_csv(path, m.FIELDS, [["客户", "", "", "", "新线索", amount, "", "", ""]])
        with pytest.raises(ValueError, match="金额无效"):
            m.read_csv_rows(path)


def test_sales_csv_replacement_creates_recoverable_pre_import_backup(tmp_path):
    data_path = tmp_path / "sales.json"
    previous = [sample_customer(客户="旧客户")]
    imported = [sample_customer(客户="新客户")]
    m.save_rows(data_path, previous)

    backup_path = m.replace_rows_with_backup(data_path, imported, previous)

    assert backup_path is not None
    assert Path(backup_path).is_file()
    assert m.load_rows(backup_path) == previous
    assert m.load_rows(data_path) == imported


def test_sales_csv_replacement_failure_keeps_original_data(tmp_path, monkeypatch):
    data_path = tmp_path / "sales.json"
    previous = [sample_customer(客户="旧客户")]
    imported = [sample_customer(客户="新客户")]
    m.save_rows(data_path, previous)
    original = data_path.read_bytes()
    real_replace = m.os.replace

    def fail_data_replace(source, destination):
        if os.path.abspath(destination) == os.path.abspath(data_path):
            raise OSError("simulated data replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(m.os, "replace", fail_data_replace)
    with pytest.raises(OSError, match="simulated data replace failure"):
        m.replace_rows_with_backup(data_path, imported, previous)

    assert data_path.read_bytes() == original
    backups = list(tmp_path.glob("sales.json.before-csv-import-*.json"))
    assert len(backups) == 1
    assert m.load_rows(backups[0]) == previous
