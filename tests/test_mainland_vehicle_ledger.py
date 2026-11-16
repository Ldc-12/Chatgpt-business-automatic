import csv
import importlib.util
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "车辆维保与费用台账助手.py"
SPEC = importlib.util.spec_from_file_location("vehicle_ledger", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(**changes):
    row = {"车牌号码": "粤A12345", "车辆名称": "家用轿车", "日期": "2026-01-02",
           "里程公里": 12000, "费用类别": "保养", "项目/事项": "更换机油",
           "服务商": "测试维修店", "金额元": 380, "下次提醒日期": "2026-07-01", "备注": "正常"}
    row.update(changes)
    return row


def test_add_persists_and_reloads(tmp_path):
    path = tmp_path / "ledger.json"
    store = MODULE.VehicleStore(path)
    record_id = store.add(sample())
    loaded = MODULE.VehicleStore(path)
    assert loaded.rows[0]["记录编号"] == record_id
    assert loaded.rows[0]["里程公里"] == 12000


def test_rejects_non_finite_and_negative_numbers_without_partial_write(tmp_path):
    store = MODULE.VehicleStore(tmp_path / "ledger.json")
    for field, value in (("金额元", float("nan")), ("金额元", float("inf")), ("里程公里", -1)):
        before = store.path.read_bytes() if store.path.exists() else None
        try:
            store.add(sample(**{field: value}))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid numeric value accepted")
        assert (store.path.read_bytes() if store.path.exists() else None) == before
        assert store.rows == []


def test_csv_roundtrip_formula_safe_and_chinese_compatible(tmp_path):
    store = MODULE.VehicleStore(tmp_path / "ledger.json")
    store.add(sample(**{"项目/事项": "=HYPERLINK(\"x\")"}))
    output = tmp_path / "export.csv"
    store.export_csv(output)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in output.read_text(encoding="utf-8-sig")
    restored = MODULE.VehicleStore(tmp_path / "restored.json")
    assert restored.import_csv(output) == 1
    assert restored.rows[0]["项目/事项"].startswith("'=")


def test_duplicate_import_is_rejected_atomically(tmp_path):
    store = MODULE.VehicleStore(tmp_path / "ledger.json")
    store.add(sample())
    output = tmp_path / "export.csv"
    store.export_csv(output)
    before = store.path.read_bytes()
    try:
        store.import_csv(output)
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate import accepted")
    assert store.path.read_bytes() == before
    assert len(store.rows) == 1


def test_invalid_header_and_row_width_are_rejected(tmp_path):
    store = MODULE.VehicleStore(tmp_path / "ledger.json")
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,header\na,b\n", encoding="utf-8")
    try:
        store.import_csv(bad)
    except ValueError as exc:
        assert "表头" in str(exc)
    else:
        raise AssertionError("invalid header accepted")


def test_backup_restore_validates_hash_and_preserves_existing_data(tmp_path):
    path = tmp_path / "ledger.json"
    store = MODULE.VehicleStore(path)
    store.add(sample())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(sample(**{"车牌号码": "粤B23456", "车辆名称": "第二辆车"}))
    store.restore(backup)
    assert len(store.rows) == 1
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["记录"][0]["备注"] = "tampered"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()
    try:
        store.restore(bad)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("tampered backup accepted")
    assert path.read_bytes() == before


def test_due_reminders_filter_by_date(tmp_path):
    store = MODULE.VehicleStore(tmp_path / "ledger.json")
    store.add(sample())
    assert len(store.due_reminders(__import__("datetime").date.fromisoformat("2026-08-01"))) == 1
    assert store.due_reminders(__import__("datetime").date.fromisoformat("2026-06-01")) == []


def test_oversized_local_data_is_rejected_without_modification(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    path.write_text("{}", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(MODULE, "MAX_BACKUP_BYTES", 1)
    try:
        MODULE.VehicleStore(path)
    except ValueError as exc:
        assert "100 MiB" in str(exc)
    else:
        raise AssertionError("oversized local data accepted")
    assert path.read_bytes() == before


def test_self_test_runs_without_gui_or_license():
    MODULE.self_test()
