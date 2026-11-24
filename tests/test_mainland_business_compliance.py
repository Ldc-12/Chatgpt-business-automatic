import csv
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "apps" / "经营证照与年报提醒助手.py"
spec = importlib.util.spec_from_file_location("business_compliance", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(item_id="BC-001", due="2026-12-31", **overrides):
    value = {
        "事项编号": item_id, "事项名称": "营业执照年报", "事项类型": "年度报告",
        "登记/开始日期": "2026-01-01", "截止日期": due,
        "提醒提前天数": "30", "状态": "待办理", "责任人": "店长",
        "来源/主管部门": "自行登记", "联系方式": "", "备注": "",
    }
    value.update(overrides)
    return value


def test_normalize_and_reminder_boundaries():
    item = module.normalize_item(row())
    assert module.reminder_state(item, date(2026, 12, 1)) == ("即将到期", 30)
    assert module.reminder_state(item, date(2026, 12, 31)) == ("即将到期", 0)
    assert module.reminder_state(item, date(2027, 1, 1)) == ("已逾期", -1)
    item["状态"] = "已完成"
    assert module.reminder_state(item, date(2027, 1, 1))[0] == "无需提醒"


@pytest.mark.parametrize("changes, message", [
    ({"事项编号": ""}, "事项编号不能为空"),
    ({"事项类型": "不存在"}, "事项类型无效"),
    ({"截止日期": "2026-02-30"}, "截止日期必须使用"),
    ({"登记/开始日期": "2027-01-01"}, "不能晚于截止日期"),
    ({"提醒提前天数": "-1"}, "0 到 3650"),
    ({"状态": "已提交"}, "事项状态无效"),
])
def test_invalid_fields_are_rejected(changes, message):
    value = row()
    value.update(changes)
    with pytest.raises(ValueError, match=message):
        module.normalize_item(value)


def test_store_persistence_update_delete_and_duplicate_guard(tmp_path):
    store = module.ComplianceStore(tmp_path / "items.json")
    store.add(row())
    loaded = module.ComplianceStore(store.path)
    assert loaded.rows == store.rows
    with pytest.raises(ValueError, match="已存在"):
        loaded.add(row())
    changed = row(due="2027-01-31", **{"事项名称": "变更后的年报事项"})
    loaded.update("BC-001", changed)
    assert loaded.rows[0]["事项名称"] == "变更后的年报事项"
    loaded.delete("BC-001")
    assert loaded.rows == []


def test_csv_roundtrip_and_formula_injection_protection(tmp_path):
    store = module.ComplianceStore(tmp_path / "items.json")
    store.add(row(**{"事项名称": "=HYPERLINK(\"https://example.invalid\",\"点击\")", "备注": "@SUM(A1:A2)"}))
    path = tmp_path / "export.csv"
    store.export_csv(path)
    content = path.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK(" in content
    assert "'@SUM(" in content
    imported = module.ComplianceStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["事项名称"] == "=HYPERLINK(\"https://example.invalid\",\"点击\")"
    assert imported.rows[0]["备注"] == "@SUM(A1:A2)"


def test_csv_import_is_atomic_on_invalid_or_duplicate_rows(tmp_path):
    store = module.ComplianceStore(tmp_path / "items.json")
    store.add(row())
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(row("BC-002"))
        writer.writerow(row("BC-003", due="not-a-date"))
    before = json.loads(store.path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="第 3 行"):
        store.import_csv(bad)
    assert store.rows == before
    assert json.loads(store.path.read_text(encoding="utf-8")) == before
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(row("BC-001"))
    with pytest.raises(ValueError, match="已有事项编号"):
        store.import_csv(duplicate)
    assert store.rows == before


def test_backup_restore_sha256_and_tamper_rejection(tmp_path):
    store = module.ComplianceStore(tmp_path / "items.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(row("BC-002", "2027-01-31"))
    store.restore(backup)
    assert [item["事项编号"] for item in store.rows] == ["BC-001"]
    document = json.loads(backup.read_text(encoding="utf-8"))
    document["payload"]["items"][0]["事项名称"] = "被篡改"
    backup.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    before = json.loads(store.path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(backup)
    assert store.rows == before
    assert json.loads(store.path.read_text(encoding="utf-8")) == before


def test_default_data_path_uses_windows_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert module.default_data_path() == tmp_path / "MainlandBusinessTools" / "business_compliance.json"


def test_filter_and_summary():
    rows = [module.normalize_item(row()), module.normalize_item(row("BC-002", "2026-11-20"))]
    filtered = module.filter_items(rows, keyword="营业执照")
    assert [item["事项编号"] for item in filtered] == ["BC-002", "BC-001"]
    due = module.filter_items(rows, due_only=True, today=date(2026, 12, 1))
    assert len(due) == 2
    summary = module.summarize_items(rows, today=date(2026, 12, 1))
    assert summary["count"] == 2
    assert summary["reminders"]["已逾期"] == 1


def test_self_test():
    module.self_test()



def test_csv_roundtrip_preserves_literal_apostrophe_before_formula_text(tmp_path):
    literal = "'=这是用户原本输入的文本"
    store = module.ComplianceStore(tmp_path / "items.json")
    store.add(row(**{"事项名称": literal}))
    exported = tmp_path / "export.csv"
    store.export_csv(exported)

    content = exported.read_text(encoding="utf-8-sig")
    assert "''=这是用户原本输入的文本" in content

    imported = module.ComplianceStore(tmp_path / "imported.json")
    assert imported.import_csv(exported) == 1
    assert imported.rows[0]["事项名称"] == literal
