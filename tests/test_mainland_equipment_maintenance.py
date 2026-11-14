import csv
import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "apps" / "设备维保巡检与保养计划助手.py"
SPEC = importlib.util.spec_from_file_location("equipment_maintenance", APP)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def asset(store, asset_id="EQ-001", **overrides):
    row = {
        "设备编号": asset_id,
        "设备名称": "冷藏柜",
        "设备类别": "冷藏冷冻",
        "安装位置": "后厨",
        "负责人": "张三",
        "启用日期": "2026-01-01",
        "保修到期日": "2027-01-01",
        "保养周期(天)": "30",
        "最近保养日期": "",
        "下次保养日期": "",
        "设备状态": "正常",
        "备注": "",
    }
    row.update(overrides)
    return row


def log(store, log_id="WB20260201-0001", **overrides):
    row = {
        "记录编号": log_id,
        "设备编号": "EQ-001",
        "维护日期": "2026-02-01",
        "维护类型": "例行保养",
        "维护内容": "清洁冷凝器",
        "服务商/人员": "内部",
        "停机时长(小时)": "0.5",
        "费用(元)": "80",
        "下次保养日期": "2026-03-03",
        "验收状态": "已验收",
        "备注": "",
    }
    row.update(overrides)
    return row


def test_add_asset_persists_and_derives_first_due_date(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    loaded = MODULE.EquipmentStore(tmp_path / "equipment.json")
    assert loaded.assets[0]["设备编号"] == "EQ-001"
    assert loaded.assets[0]["下次保养日期"] == "2026-01-31"


def test_category_default_interval_is_used_when_blank(tmp_path):
    row = asset(None, **{"设备类别": "冷藏冷冻", "保养周期(天)": ""})
    assert MODULE.normalize_asset(row)["保养周期(天)"] == "30"
    row["设备类别"] = "空调通风"
    assert MODULE.normalize_asset(row)["保养周期(天)"] == "90"


@pytest.mark.parametrize(
    "changes",
    [
        {"设备编号": ""},
        {"设备名称": ""},
        {"设备类别": "未知类别"},
        {"启用日期": "2026/01/01"},
        {"保修到期日": "2025-12-31"},
        {"最近保养日期": "2025-12-31"},
        {"保养周期(天)": "0"},
        {"保养周期(天)": "3651"},
        {"保养周期(天)": "30.5"},
        {"下次保养日期": "2026-01-01"},
        {"设备状态": "未知状态"},
    ],
)
def test_invalid_asset_fields_are_rejected(changes):
    row = asset(None)
    row.update(changes)
    with pytest.raises(ValueError):
        MODULE.normalize_asset(row)


def test_duplicate_asset_id_is_rejected_without_mutating_store(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    with pytest.raises(ValueError, match="已存在"):
        store.add_asset(asset(store, "EQ-001", **{"设备名称": "另一台设备"}))
    assert len(store.assets) == 1


def test_maintenance_log_updates_asset_schedule_and_summary(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store))
    assert store.assets[0]["最近保养日期"] == "2026-02-01"
    assert store.assets[0]["下次保养日期"] == "2026-03-03"
    assert store.assets[0]["设备状态"] == "正常"
    totals = MODULE.maintenance_totals(store.logs)
    assert totals == {"count": 1, "cost": Decimal("80.00"), "downtime": Decimal("0.50")}
    reloaded = MODULE.EquipmentStore(tmp_path / "equipment.json")
    assert len(reloaded.logs) == 1


def test_pending_or_failed_acceptance_raises_risk(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store, **{"验收状态": "待验收"}))
    result = MODULE.analyze_assets(store.assets, store.logs, today="2026-02-02")[0]
    assert result["风险等级"] == "高风险"
    assert "待验收" in result["风险说明"] or "未通过" in result["风险说明"]


def test_failed_acceptance_marks_asset_for_repair(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store, **{"验收状态": "不通过"}))
    assert store.assets[0]["设备状态"] == "待检修"
    assert MODULE.analyze_assets(store.assets, store.logs, today="2026-02-02")[0]["风险等级"] == "高风险"


def test_due_date_boundary_and_warranty_warning():
    row = MODULE.normalize_asset(asset(None, **{"启用日期": "2026-01-01", "下次保养日期": "2026-02-15"}))
    due = MODULE.analyze_assets([row], [], today="2026-02-01", lead_days=14)[0]
    assert due["风险等级"] == "中风险"
    assert "14 天内到期" in due["风险说明"]
    overdue = MODULE.analyze_assets([row], [], today="2026-02-16")[0]
    assert overdue["风险等级"] == "高风险"
    assert overdue["逾期天数"] == 1


def test_warranty_expiry_is_reported_separately_from_maintenance_due():
    row = MODULE.normalize_asset(asset(None, **{
        "启用日期": "2026-01-01",
        "保修到期日": "2026-02-20",
        "下次保养日期": "2026-08-01",
    }))
    result = MODULE.analyze_assets([row], [], today="2026-02-01")[0]
    assert result["风险等级"] == "中风险"
    assert "保修将在 30 天内到期" in result["风险说明"]


def test_maintenance_log_rejects_unknown_asset_and_invalid_amounts(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    with pytest.raises(ValueError, match="不存在的设备"):
        store.record_maintenance(log(store, **{"设备编号": "EQ-404"}))
    with pytest.raises(ValueError, match="非有限数"):
        store.record_maintenance(log(store, **{"费用(元)": "NaN"}))
    with pytest.raises(ValueError, match="不能为负数"):
        store.record_maintenance(log(store, **{"停机时长(小时)": "-1"}))
    assert store.logs == []


def test_maintenance_log_id_is_unique(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store))
    with pytest.raises(ValueError, match="已存在"):
        store.record_maintenance(log(store))
    assert len(store.logs) == 1


def test_asset_with_history_cannot_be_deleted_or_renumbered(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store))
    with pytest.raises(ValueError, match="不能删除"):
        store.delete_asset("EQ-001")
    with pytest.raises(ValueError, match="不允许修改编号"):
        store.update_asset("EQ-001", asset(store, "EQ-002"))
    assert store.assets[0]["设备编号"] == "EQ-001"


def test_csv_export_uses_bom_and_formula_injection_guard_and_roundtrips(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store, **{"设备名称": "=HYPERLINK(\"https://bad.example\")"}))
    output = tmp_path / "assets.csv"
    store.export_assets_csv(output)
    raw = output.read_text(encoding="utf-8-sig")
    assert raw.startswith("设备编号,")
    assert "'=HYPERLINK" in raw
    restored = MODULE.EquipmentStore(tmp_path / "copy.json")
    assert restored.import_assets_csv(output) == 1
    assert restored.assets[0]["设备名称"] == "=HYPERLINK(\"https://bad.example\")"


def test_csv_import_rejects_duplicate_ids_and_malformed_rows_atomically(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS)
        writer.writeheader()
        writer.writerow(asset(store, "EQ-002"))
        writer.writerow(asset(store, "EQ-002"))
    with pytest.raises(ValueError, match="重复"):
        store.import_assets_csv(bad)
    assert [row["设备编号"] for row in store.assets] == ["EQ-001"]


def test_csv_import_rejects_short_rows_and_extra_columns(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    short = tmp_path / "short.csv"
    short.write_text("设备编号,设备名称\nEQ-1,冷藏柜\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="表头"):
        store.import_assets_csv(short)
    extra = tmp_path / "extra.csv"
    extra.write_text(",".join(MODULE.FIELDS) + ",恶意列\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="表头"):
        store.import_assets_csv(extra)


def test_csv_import_duplicate_against_existing_is_atomic(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    path = tmp_path / "duplicate.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS)
        writer.writeheader()
        writer.writerow(asset(store, "EQ-002"))
        writer.writerow(asset(store, "EQ-001"))
    with pytest.raises(ValueError, match="已存在设备编号"):
        store.import_assets_csv(path)
    assert [row["设备编号"] for row in store.assets] == ["EQ-001"]


def test_backup_and_restore_preserve_asset_and_full_history(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store))
    backup = tmp_path / "backup.json"
    store.backup(backup)
    target = MODULE.EquipmentStore(tmp_path / "target.json")
    target.add_asset(asset(target, "EQ-OLD"))
    target.restore(backup)
    assert [row["设备编号"] for row in target.assets] == ["EQ-001"]
    assert len(target.logs) == 1
    assert target.assets[0]["最近保养日期"] == "2026-02-01"


def test_invalid_backup_does_not_replace_existing_data(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store, "EQ-KEEP"))
    bad = tmp_path / "bad-backup.json"
    bad.write_text(json.dumps({
        "format": MODULE.BACKUP_FORMAT,
        "version": MODULE.BACKUP_VERSION,
        "assets": [asset(store, "EQ-DUP"), asset(store, "EQ-DUP")],
        "logs": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        store.restore(bad)
    assert [row["设备编号"] for row in store.assets] == ["EQ-KEEP"]


def test_atomic_replace_failure_preserves_original_file(tmp_path, monkeypatch):
    target = tmp_path / "equipment.json"
    store = MODULE.EquipmentStore(target)
    store.add_asset(asset(store))
    original = target.read_text(encoding="utf-8")
    monkeypatch.setattr(MODULE.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("simulated replace failure")))
    with pytest.raises(OSError, match="simulated replace failure"):
        store.add_asset(asset(store, "EQ-002"))
    assert target.read_text(encoding="utf-8") == original
    assert [row["设备编号"] for row in store.assets] == ["EQ-001"]


def test_export_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    target = tmp_path / "assets.csv"
    target.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(MODULE.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("simulated export failure")))
    with pytest.raises(OSError, match="simulated export failure"):
        store.export_assets_csv(target)
    assert target.read_text(encoding="utf-8") == "previous"


def test_risk_analysis_prioritizes_high_before_medium():
    normal = MODULE.normalize_asset(asset(None, "EQ-2", **{"启用日期": "2026-01-01", "下次保养日期": "2026-12-01"}))
    overdue = MODULE.normalize_asset(asset(None, "EQ-1", **{"启用日期": "2026-01-01", "下次保养日期": "2026-01-01"}))
    rows = MODULE.analyze_assets([normal, overdue], [], today="2026-02-01")
    assert [row["设备编号"] for row in rows] == ["EQ-1", "EQ-2"]


def test_self_test_uses_temporary_data_and_covers_backup_restore():
    MODULE.self_test()


def test_backdated_maintenance_cannot_move_schedule_backwards(tmp_path):
    store = MODULE.EquipmentStore(tmp_path / "equipment.json")
    store.add_asset(asset(store))
    store.record_maintenance(log(store))
    with pytest.raises(ValueError, match="不能早于最近一次"):
        store.record_maintenance(log(store, "WB20260131-0001", **{"维护日期": "2026-01-31"}))
    assert len(store.logs) == 1
    assert store.assets[0]["最近保养日期"] == "2026-02-01"


def test_retired_asset_is_not_flagged_for_routine_due_or_warranty(tmp_path):
    row = MODULE.normalize_asset(asset(None, **{
        "启用日期": "2025-01-01",
        "保修到期日": "2025-06-01",
        "下次保养日期": "2025-02-01",
        "设备状态": "停用",
    }))
    result = MODULE.analyze_assets([row], [], today="2026-02-01")[0]
    assert result["风险等级"] == "正常"
    assert result["风险说明"] == "当前无到期或验收异常"
