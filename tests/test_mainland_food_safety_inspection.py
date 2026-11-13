import pytest
import csv
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "门店食品安全巡检与整改闭环助手.py"
SPEC = importlib.util.spec_from_file_location("food_safety_inspection", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def create(store, name="测试门店", inspector="检查员"):
    return store.create_inspection(name, inspector)


def fail(store, inspection_id, rule_id="FS-001", *, due=None):
    store.update_check(inspection_id, rule_id, "不合格", "现场记录缺失", "张三",
                       due or date.today().isoformat())


def test_checklist_is_versioned_and_rule_ids_are_unique():
    assert MODULE.CHECKLIST_VERSION == "CN-FOOD-SAFETY-OPS-2026.11.1"
    ids = [row["id"] for row in MODULE.CHECKLIST]
    assert len(ids) == 17
    assert len(ids) == len(set(ids))
    assert set(row["risk"] for row in MODULE.CHECKLIST) <= {"高", "中", "低"}


def test_create_inspection_persists_complete_checklist_and_audit_chain(tmp_path):
    path = tmp_path / "data.json"
    store = MODULE.InspectionStore(path)
    inspection_id = create(store)
    loaded = MODULE.InspectionStore(path)
    inspection = loaded.get_inspection(inspection_id)
    assert len(inspection["检查项"]) == 17
    assert all(row["检查结果"] == "待检查" for row in inspection["检查项"])
    assert len(loaded.events) == 1
    assert MODULE.verify_event_chain(loaded.events)


def test_failed_check_requires_owner_and_due_date_without_partial_write(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    before = store.path.read_bytes()
    try:
        store.update_check(inspection_id, "FS-001", "不合格", "不符合", "", "")
    except ValueError as exc:
        assert "责任人和整改期限" in str(exc)
    else:
        raise AssertionError("unassigned failed check should be rejected")
    assert store.path.read_bytes() == before
    assert len(store.events) == 1


def test_risk_weighted_score_excludes_unchecked_and_not_applicable(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    store.update_check(inspection_id, "FS-001", "不合格", "异常", "张三", date.today().isoformat())
    store.update_check(inspection_id, "FS-002", "合格", "记录齐全")
    inspection = store.get_inspection(inspection_id)
    assert store.score(inspection) == 50.0
    store.update_check(inspection_id, "FS-001", "合格", "已纠正")
    assert store.score(store.get_inspection(inspection_id)) == 100.0


def test_overdue_findings_and_repeat_issue_detection(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    today = date.today()
    first = store.create_inspection("门店 A", "检查员", inspected_on=(today - timedelta(days=2)).isoformat())
    second = store.create_inspection("门店 A", "检查员", inspected_on=today.isoformat())
    fail(store, first, due=(today - timedelta(days=1)).isoformat())
    fail(store, second, due=(today + timedelta(days=1)).isoformat())
    assert len(store.overdue_findings(today=today)) == 1
    assert store.repeated_findings(today=today) == ["FS-001"]
    dashboard = store.dashboard(today=today)
    assert dashboard["待整改"] == 2
    assert dashboard["逾期整改"] == 1
    assert dashboard["重复问题"] == 1


def test_close_finding_requires_note_and_records_reviewer(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    fail(store, inspection_id)
    try:
        store.close_finding(inspection_id, "FS-001", " ")
    except ValueError as exc:
        assert "整改说明不能为空" in str(exc)
    else:
        raise AssertionError("empty resolution should be rejected")
    store.close_finding(inspection_id, "FS-001", "补齐资料并复核")
    entry = next(row for row in store.get_inspection(inspection_id)["检查项"] if row["规则编号"] == "FS-001")
    assert entry["整改状态"] == "已完成"
    assert entry["复查日期"] == date.today().isoformat()
    assert len(store.open_findings()) == 0
    assert store.events[-1]["动作"] == "整改复查完成"


def test_csv_roundtrip_and_formula_safe_export(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store, name='=HYPERLINK("x")')
    store.update_check(inspection_id, "FS-001", "合格", "+供应商票据已核验")
    output = tmp_path / "export.csv"
    store.export_csv(output)
    raw = output.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in raw
    assert "'+供应商票据" in raw
    restored = MODULE.InspectionStore(tmp_path / "restored.json")
    assert restored.import_csv(output) == 1
    assert restored.get_inspection(inspection_id)["门店名称"] == "'=HYPERLINK(\"x\")"
    assert store.get_inspection(inspection_id)["门店名称"] == '=HYPERLINK("x")'


def test_duplicate_csv_import_is_rejected_atomically(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    export = tmp_path / "one.csv"
    store.export_csv(export)
    before = (list(store.inspections), list(store.events), store.path.read_bytes())
    try:
        store.import_csv(export)
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate inspection import should fail")
    assert (store.inspections, store.events, store.path.read_bytes()) == before


def test_incomplete_or_inconsistent_csv_is_rejected_atomically(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    export = tmp_path / "incomplete.csv"
    with export.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CSV_FIELDS)
        writer.writeheader()
        inspection = store.get_inspection(inspection_id)
        entry = inspection["检查项"][0]
        writer.writerow({
            "巡检编号": inspection_id, "门店名称": inspection["门店名称"],
            "巡检日期": inspection["巡检日期"], "检查人": inspection["检查人"],
            "清单版本": inspection["清单版本"], **entry,
        })
    before = (list(store.inspections), list(store.events), store.path.read_bytes())
    try:
        store.import_csv(export)
    except ValueError as exc:
        assert "全部检查项" in str(exc)
    else:
        raise AssertionError("partial inspection CSV should fail")
    assert (store.inspections, store.events, store.path.read_bytes()) == before


def test_modified_rule_title_is_rejected(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    export = tmp_path / "bad.csv"
    store.export_csv(export)
    rows = list(csv.DictReader(export.open(encoding="utf-8-sig", newline="")))
    rows[0]["检查项目"] = "伪造检查项目"
    with export.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    other = MODULE.InspectionStore(tmp_path / "other.json")
    try:
        other.import_csv(export)
    except ValueError as exc:
        assert "规则名称或风险等级" in str(exc)
    else:
        raise AssertionError("modified rule title should be rejected")


def test_backup_restore_validates_checksum_and_audit_chain(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    fail(store, inspection_id)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.close_finding(inspection_id, "FS-001", "已复核")
    store.restore(backup)
    restored = MODULE.InspectionStore(tmp_path / "data.json")
    assert restored.dashboard()["待整改"] == 1
    assert MODULE.verify_event_chain(restored.events)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["巡检记录"][0]["门店名称"] = "被篡改"
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = restored.path.read_bytes()
    try:
        restored.restore(bad)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("tampered backup should be rejected")
    assert restored.path.read_bytes() == before


def test_tampered_audit_event_is_detected_on_load(tmp_path):
    path = tmp_path / "data.json"
    store = MODULE.InspectionStore(path)
    create(store)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["审计链"][0]["摘要"] = "被篡改"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = __import__("hashlib").sha256(MODULE.canonical_bytes(body)).hexdigest()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        MODULE.InspectionStore(path)
    except ValueError as exc:
        assert "审计链校验失败" in str(exc)
    else:
        raise AssertionError("tampered audit event should be rejected")


def test_bad_local_data_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{broken", encoding="utf-8")
    before = path.read_bytes()
    try:
        MODULE.InspectionStore(path)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed local data should fail closed")
    assert path.read_bytes() == before


def test_self_test_runs_without_license_or_gui():
    MODULE.self_test()


def test_tampered_inspection_snapshot_is_detected_even_if_outer_checksum_is_recomputed(tmp_path):
    path = tmp_path / "data.json"
    store = MODULE.InspectionStore(path)
    create(store)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["巡检记录"][0]["门店名称"] = "被篡改门店"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = __import__("hashlib").sha256(MODULE.canonical_bytes(body)).hexdigest()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        MODULE.InspectionStore(path)
    except ValueError as exc:
        assert "记录快照 SHA256" in str(exc)
    else:
        raise AssertionError("tampered inspection snapshot should be rejected")


def test_event_chain_latest_snapshot_is_bound_to_inspection_record(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    row = store.get_inspection(inspection_id)
    assert store.events[-1]["记录SHA256"] == row["记录SHA256"]
    fail(store, inspection_id)
    row = store.get_inspection(inspection_id)
    assert store.events[-1]["记录SHA256"] == row["记录SHA256"]
    assert MODULE.verify_event_chain(store.events)


def test_csv_export_preserves_existing_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    destination = tmp_path / "export.csv"
    destination.write_bytes(b"previous-export")

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(MODULE.os, "replace", fail_replace)
    try:
        store.export_csv(destination)
    except OSError as exc:
        assert "simulated replace failure" in str(exc)
    else:
        raise AssertionError("failed atomic replace should be reported")

    assert destination.read_bytes() == b"previous-export"
    assert not list(tmp_path.glob("export.csv.*.tmp"))


def test_backup_preserves_existing_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    destination = tmp_path / "backup.json"
    destination.write_bytes(b"previous-backup")

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(MODULE.os, "replace", fail_replace)
    try:
        store.backup(destination)
    except OSError as exc:
        assert "simulated replace failure" in str(exc)
    else:
        raise AssertionError("failed atomic replace should be reported")

    assert destination.read_bytes() == b"previous-backup"
    assert not list(tmp_path.glob("backup.json.*.tmp"))


def test_oversized_csv_is_rejected_before_import(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    inspection_id = create(store)
    before_rows = list(store.inspections)
    before_events = list(store.events)
    source = tmp_path / "oversized.csv"
    source.write_bytes(b"x" * 11)
    monkeypatch.setattr(MODULE, "MAX_CSV_BYTES", 10)

    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "25 MiB" in str(exc)
    else:
        raise AssertionError("oversized CSV should be rejected")

    assert store.inspections == before_rows
    assert store.events == before_events
    assert store.get_inspection(inspection_id) is not None


def test_create_respects_inspection_count_limit_without_partial_write(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    monkeypatch.setattr(MODULE, "MAX_INSPECTIONS", 0)
    try:
        store.create_inspection("超限门店", "检查人")
    except ValueError as exc:
        assert "10000 条安全上限" in str(exc)
    else:
        raise AssertionError("inspection count limit should be enforced")
    assert store.inspections == []
    assert store.events == []
    assert not store.path.exists()


def test_oversized_backup_is_rejected_without_replacing_existing_file(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    destination = tmp_path / "backup.json"
    destination.write_bytes(b"previous-backup")
    monkeypatch.setattr(MODULE, "MAX_BACKUP_BYTES", 10)
    try:
        store.backup(destination)
    except ValueError as exc:
        assert "100 MiB" in str(exc)
    else:
        raise AssertionError("oversized backup should be rejected")
    assert destination.read_bytes() == b"previous-backup"


def test_repeat_issue_detection_is_scoped_to_the_same_store(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    today = date.today()
    a1 = store.create_inspection("门店 A", "检查员", inspected_on=today.isoformat())
    b1 = store.create_inspection("门店 B", "检查员", inspected_on=today.isoformat())
    fail(store, a1, "FS-001")
    fail(store, b1, "FS-001")

    assert store.repeated_findings(today=today) == []
    assert store.repeated_findings_by_store(today=today) == {}

    a2 = store.create_inspection("门店 A", "复查员", inspected_on=today.isoformat())
    fail(store, a2, "FS-001")
    assert store.repeated_findings(today=today) == ["FS-001"]
    assert store.repeated_findings_by_store(today=today) == {"门店 A": ["FS-001"]}


def test_store_risk_report_prioritizes_overdue_and_high_risk_work(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    today = date.today()
    urgent = store.create_inspection("重点门店", "检查员", inspected_on=today.isoformat())
    normal = store.create_inspection("普通门店", "检查员", inspected_on=today.isoformat())
    fail(store, urgent, "FS-001", due=(today - timedelta(days=1)).isoformat())
    fail(store, normal, "FS-009", due=(today + timedelta(days=2)).isoformat())

    rows = store.store_risk_report(today=today)
    assert [row["门店名称"] for row in rows] == ["重点门店", "普通门店"]
    assert rows[0]["关注等级"] == "重点关注"
    assert rows[0]["逾期整改"] == 1
    assert rows[0]["高风险待整改"] == 1
    assert rows[1]["关注等级"] == "跟进整改"
    assert rows[1]["逾期整改"] == 0


def test_store_risk_csv_is_formula_safe_and_keeps_original_store_name(tmp_path):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store, name='=HYPERLINK("x")')
    output = tmp_path / "store-risk.csv"
    store.export_store_risk_csv(output)
    raw = output.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in raw
    rows = list(csv.DictReader(output.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["关注等级"] == "暂无待整改"
    assert rows[0]["90天重复规则"] == ""


def test_store_risk_csv_preserves_existing_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    store = MODULE.InspectionStore(tmp_path / "data.json")
    create(store)
    destination = tmp_path / "store-risk.csv"
    destination.write_bytes(b"previous-report")

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(MODULE.os, "replace", fail_replace)
    try:
        store.export_store_risk_csv(destination)
    except OSError as exc:
        assert "simulated replace failure" in str(exc)
    else:
        raise AssertionError("failed atomic replace should be reported")

    assert destination.read_bytes() == b"previous-report"
    assert not list(tmp_path.glob("store-risk.csv.*.tmp"))
