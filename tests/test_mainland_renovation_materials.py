import csv
import json
from pathlib import Path

import pytest

from src import renovation_materials as module


def sample(**overrides):
    row = {
        "记录编号": "RM-001", "项目编号": "P001", "项目名称": "A户型装修",
        "房间/区域": "客厅", "材料编码": "TILE-600", "材料名称": "600×600地砖",
        "材料类别": "地面", "计量单位": "m²", "净用量": "10",
        "损耗率(%)": "8", "包装规格": "1", "单价(元/单位)": "38",
        "供应商": "甲建材", "实际采购量": "", "实际金额(元)": "", "备注": "",
    }
    row.update(overrides)
    return row


def test_material_takeoff_rounds_to_full_package_and_budget():
    result = module.calculate_material(sample())
    assert result["计划用量(含损耗)"] == "10.800"
    assert result["建议采购包装数"] == 11
    assert result["建议采购量"] == "11.000"
    assert result["预算金额(元)"] == "418.00"


def test_tile_calculator_rounds_tiles_and_boxes_up():
    result = module.calculate_tile_quantity("10", "600", "600", "8", "4")
    assert result["理论所需片数"] == 30
    assert result["建议整箱数"] == 8
    assert result["建议采购片数"] == 32


def test_paint_calculator_rounds_to_tenth_litre():
    assert module.calculate_paint_liters("50", 2, "10", "10") == "11.0"
    with pytest.raises(ValueError, match="1–10"):
        module.calculate_paint_liters("50", 0, "10", "10")


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"损耗率(%)": "101"}, "0–100"),
        ({"净用量": "-1"}, "大于 0"),
        ({"包装规格": "0"}, "大于 0"),
        ({"单价(元/单位)": "NaN"}, "NaN"),
        ({"材料类别": "不存在"}, "内置分类"),
        ({"计量单位": "平方英尺"}, "支持列表"),
    ],
)
def test_invalid_material_inputs_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_material_row(sample(**overrides))


def test_project_id_cannot_be_reused_with_different_project_name(tmp_path):
    store = module.MaterialStore(tmp_path / "materials.json")
    store.add(sample())
    with pytest.raises(ValueError, match="对应多个项目名称"):
        store.add(sample(**{"记录编号": "RM-002", "项目名称": "另一个项目"}))
    assert len(store.rows) == 1


def test_store_persists_updates_and_deletes(tmp_path):
    path = tmp_path / "materials.json"
    store = module.MaterialStore(path)
    store.add(sample())
    loaded = module.MaterialStore(path)
    assert loaded.rows == store.rows
    changed = dict(loaded.rows[0], **{"单价(元/单位)": "40"})
    loaded.update("RM-001", changed)
    assert module.calculate_material(loaded.rows[0])["预算金额(元)"] == "440.00"
    loaded.delete("RM-001")
    assert loaded.rows == []


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    store = module.MaterialStore(tmp_path / "source.json")
    store.add(sample(**{"材料名称": "=HYPERLINK(\"https://bad.example\",\"点击\")"}))
    csv_path = tmp_path / "materials.csv"
    store.export_csv(csv_path)
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "'=HYPERLINK" in text

    target = module.MaterialStore(tmp_path / "target.json")
    assert target.import_csv(csv_path) == 1
    assert target.rows[0]["材料名称"].startswith("'=")


def test_csv_import_rejects_bad_rows_and_duplicates_atomically(tmp_path):
    source = module.MaterialStore(tmp_path / "source.json")
    source.add(sample())
    csv_path = tmp_path / "bad.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"记录编号": "RM-002", "损耗率(%)": "150"}))
    before = list(source.rows)
    with pytest.raises(ValueError, match="损耗率"):
        source.import_csv(csv_path)
    assert source.rows == before

    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在"):
        source.import_csv(duplicate)
    assert source.rows == before


def test_backup_restore_checks_sha256_before_replacing_data(tmp_path):
    source = module.MaterialStore(tmp_path / "source.json")
    source.add(sample())
    backup = tmp_path / "materials-backup.json"
    source.backup(backup)

    target = module.MaterialStore(tmp_path / "target.json")
    target.add(sample(**{"记录编号": "RM-OLD", "材料编码": "OLD", "材料名称": "旧材料"}))
    target.restore(backup)
    assert target.rows == source.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["materials"][0]["单价(元/单位)"] = "999"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(target.rows)
    with pytest.raises(ValueError, match="SHA256"):
        target.restore(tampered)
    assert target.rows == before


def test_failed_atomic_replace_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "materials.json"
    store = module.MaterialStore(path)
    store.add(sample())
    original = path.read_bytes()
    monkeypatch.setattr(module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        store.add(sample(**{"记录编号": "RM-002", "材料编码": "WOOD", "材料名称": "木地板"}))
    assert path.read_bytes() == original
    assert len(store.rows) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_project_summary_separates_projects_and_actual_cost_variance():
    rows = [
        sample(**{"实际金额(元)": "450"}),
        sample(**{"记录编号": "RM-002", "项目编号": "P002", "项目名称": "B项目",
                  "实际金额(元)": "100"}),
    ]
    summary = module.project_summary(rows)
    assert summary["P001"]["预算金额(元)"] == "418.00"
    assert summary["P001"]["实际与预算差额(元)"] == "32.00"
    assert summary["P002"]["材料行数"] == 1


def test_self_test_runs_without_gui():
    module.self_test()
