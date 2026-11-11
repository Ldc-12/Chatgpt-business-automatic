import csv
import io
import hashlib
import importlib.util
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "售后纠纷证据链管理助手.py"
SPEC = importlib.util.spec_from_file_location("after_sales_evidence_assistant", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def case(case_id="CASE-001", **changes):
    row = {
        "案件编号": case_id,
        "平台": "闲鱼",
        "订单编号": "ORDER-001",
        "买家备注名": "买家甲",
        "商品名称": "二手显示器",
        "纠纷类型": "退货争议",
        "购买日期": "2026-11-01",
        "响应截止日期": (date.today() + timedelta(days=3)).isoformat(),
        "退款金额": "100.00",
        "补偿金额": "0",
        "状态": "待处理",
        "负责人": "店主",
        "备注": "",
    }
    row.update(changes)
    return row


def add_evidence(store, tmp_path, case_id="CASE-001", content=b"chat screenshot"):
    source = tmp_path / "chat.txt"
    source.write_bytes(content)
    return store.add_evidence(case_id, source, "聊天记录截图导出")


def test_case_persists_and_creates_first_chained_event(tmp_path):
    path = tmp_path / "cases.json"
    store = MODULE.EvidenceStore(path)
    store.add_case(case())
    loaded = MODULE.EvidenceStore(path)
    assert loaded.cases[0]["案件编号"] == "CASE-001"
    assert len(loaded.events) == 1
    assert loaded.events[0]["事件类型"] == "创建案件"
    assert loaded.events[0]["前序哈希"] == MODULE.ZERO_HASH
    assert loaded.verify_integrity() == []


def test_update_case_records_field_and_status_changes(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    updated = case("CASE-001", 状态="处理中", 负责人="客服乙", 备注="已联系买家")
    store.update_case("CASE-001", updated)
    assert [row["事件类型"] for row in store.events] == ["创建案件", "更新案件", "状态变更"]
    assert store.events[-1]["说明"] == "待处理 → 处理中"
    assert store.verify_integrity() == []


def test_invalid_money_and_date_order_are_rejected(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    for row in (
        case(退款金额="-1"),
        case(退款金额="NaN"),
        case(购买日期="2026-11-10", 响应截止日期="2026-11-09"),
        case(响应截止日期="not-a-date"),
    ):
        try:
            store.add_case(row)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid case row should be rejected")
    assert store.cases == []
    assert store.events == []


def test_duplicate_case_id_is_rejected_without_mutation(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    before = (list(store.cases), list(store.events))
    try:
        store.add_case(case())
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate case ID should fail")
    assert (store.cases, store.events) == before


def test_case_id_cannot_change_after_evidence_is_linked(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    add_evidence(store, tmp_path)
    try:
        store.update_case("CASE-001", case("CASE-RENAMED"))
    except ValueError as exc:
        assert "不可修改" in str(exc)
    else:
        raise AssertionError("case ID change should fail")
    assert store.cases[0]["案件编号"] == "CASE-001"
    assert store.evidence[0]["案件编号"] == "CASE-001"


def test_evidence_is_copied_and_sha256_recorded(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    item = add_evidence(store, tmp_path, content=b"original evidence bytes")
    stored = store._evidence_path(item["存储路径"])
    assert stored.read_bytes() == b"original evidence bytes"
    assert item["大小字节"] == str(len(b"original evidence bytes"))
    assert item["SHA256"] == hashlib.sha256(b"original evidence bytes").hexdigest()
    assert store.verify_integrity() == []


def test_evidence_tampering_is_detected(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    item = add_evidence(store, tmp_path)
    store._evidence_path(item["存储路径"]).write_bytes(b"modified")
    errors = store.verify_integrity()
    assert any("哈希已变化" in error for error in errors)


def test_missing_evidence_is_detected_on_integrity_check(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    item = add_evidence(store, tmp_path)
    store._evidence_path(item["存储路径"]).unlink()
    assert any("文件缺失" in error for error in store.verify_integrity())


def test_event_chain_detects_modified_event_content(tmp_path):
    path = tmp_path / "cases.json"
    store = MODULE.EvidenceStore(path)
    store.add_case(case())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["events"][0]["说明"] = "被修改的事件内容"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        MODULE.EvidenceStore(path)
    except ValueError as exc:
        assert "哈希不匹配" in str(exc)
    else:
        raise AssertionError("modified event chain should not load")


def test_case_csv_roundtrip_and_formula_injection_prefix(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case(备注="=HYPERLINK(\"https://example.invalid\")"))
    exported = tmp_path / "cases.csv"
    store.export_csv(exported)
    with exported.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["备注"].startswith("'=")
    normal = MODULE.EvidenceStore(tmp_path / "imported.json")
    clean = tmp_path / "clean.csv"
    with clean.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CASE_FIELDS)
        writer.writeheader()
        writer.writerow(case("CASE-002", 备注="普通备注"))
    assert normal.import_csv(clean) == 1
    assert normal.cases[0]["备注"] == "普通备注"


def test_duplicate_csv_import_is_atomic(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CASE_FIELDS)
        writer.writeheader()
        writer.writerow(case("CASE-002"))
        writer.writerow(case("CASE-001"))
    before = (list(store.cases), list(store.events))
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate CSV import should fail")
    assert (store.cases, store.events) == before


def test_invalid_csv_import_does_not_change_existing_data(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    source = tmp_path / "invalid.csv"
    source.write_text("案件编号,平台\nCASE-2,闲鱼", encoding="utf-8-sig")
    before = (list(store.cases), list(store.events))
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("CSV missing required columns should fail")
    assert (store.cases, store.events) == before


def test_backup_restore_roundtrip_includes_evidence_and_event_chain(tmp_path):
    source = MODULE.EvidenceStore(tmp_path / "source" / "cases.json")
    source.add_case(case())
    add_evidence(source, tmp_path, content=b"evidence in backup")
    backup = tmp_path / "full-backup.zip"
    source.backup(backup)
    source.update_case("CASE-001", case("CASE-001", 状态="处理中"))
    restored = MODULE.EvidenceStore(tmp_path / "restored" / "cases.json")
    restored.restore(backup)
    assert restored.cases[0]["状态"] == "待处理"
    assert len(restored.evidence) == 1
    assert restored.verify_integrity() == []
    assert restored._evidence_path(restored.evidence[0]["存储路径"]).read_bytes() == b"evidence in backup"


def test_backup_manifest_tampering_is_rejected_without_overwriting(tmp_path):
    source = MODULE.EvidenceStore(tmp_path / "source" / "cases.json")
    source.add_case(case())
    backup = tmp_path / "good.zip"
    source.backup(backup)
    with zipfile.ZipFile(backup) as original:
        members = {name: original.read(name) for name in original.namelist()}
    members["data.json"] += b" "
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    target = MODULE.EvidenceStore(tmp_path / "target" / "cases.json")
    target.add_case(case("KEEP-001"))
    before = (list(target.cases), list(target.events))
    try:
        target.restore(bad)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("tampered backup should fail")
    assert (target.cases, target.events) == before


def test_restore_rejects_path_traversal_member(tmp_path):
    payload = {
        "format": MODULE.BACKUP_FORMAT,
        "version": MODULE.BACKUP_VERSION,
        "cases": [],
        "evidence": [],
        "events": [],
    }
    entries = {
        "data.json": json.dumps(payload).encode("utf-8"),
        "../escape.txt": b"not allowed",
    }
    manifest = MODULE.EvidenceStore._zip_manifest(entries, MODULE.BACKUP_FORMAT)
    bad = tmp_path / "traversal.zip"
    with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
    target = MODULE.EvidenceStore(tmp_path / "target" / "cases.json")
    try:
        target.restore(bad)
    except ValueError as exc:
        assert "不安全" in str(exc)
    else:
        raise AssertionError("path traversal backup should fail")


def test_case_export_bundle_contains_evidence_and_matching_manifest(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case())
    add_evidence(store, tmp_path, content=b"case evidence")
    output = tmp_path / "case-export.zip"
    store.export_case_bundle("CASE-001", output)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        for name, meta in manifest["files"].items():
            data = archive.read(name)
            assert len(data) == meta["size"]
            assert hashlib.sha256(data).hexdigest() == meta["sha256"]
        assert "case.json" in archive.namelist()
        assert "events.csv" in archive.namelist()
        assert any(name.startswith("evidence/") for name in archive.namelist())


def test_deadline_state_boundaries_and_closed_cases(tmp_path):
    today = date.today()
    assert MODULE.deadline_state(case(响应截止日期=(today - timedelta(days=1)).isoformat()), today=today) == "已逾期 1 天"
    assert MODULE.deadline_state(case(响应截止日期=today.isoformat()), today=today) == "今日截止"
    assert MODULE.deadline_state(case(响应截止日期=(today + timedelta(days=3)).isoformat()), today=today) == "3 日内截止"
    assert MODULE.deadline_state(case(响应截止日期="", 状态="处理中"), today=today) == "未设置期限"
    assert MODULE.deadline_state(case(状态="已解决"), today=today) == "已结束"


def test_noninteractive_self_test_exercises_backup_restore(tmp_path):
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(PATH), "--self-test"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "SELF_TEST_OK" in result.stdout

def test_case_bundle_is_scoped_to_selected_case_and_formula_safe(tmp_path):
    store = MODULE.EvidenceStore(tmp_path / "cases.json")
    store.add_case(case("CASE-001"))
    store.add_case(case("CASE-002", 订单编号="ORDER-002", 商品名称="另一件商品"))
    source = tmp_path / "proof.txt"
    source.write_bytes(b"case-specific evidence")
    store.add_evidence("CASE-001", source, '=HYPERLINK("https://example.invalid")')

    output = tmp_path / "case-001.zip"
    store.export_case_bundle("CASE-001", output)
    with zipfile.ZipFile(output) as archive:
        chain = json.loads(archive.read("event-chain.json").decode("utf-8"))
        assert chain["scope"] == "case-only"
        assert chain["case_id"] == "CASE-001"
        assert all(event["案件编号"] == "CASE-001" for event in chain["events"])
        assert "CASE-002" not in json.dumps(chain, ensure_ascii=False)

        events = list(csv.DictReader(io.StringIO(archive.read("events.csv").decode("utf-8-sig"))))
        assert events and all(row["案件编号"] == "CASE-001" for row in events)

        evidence_rows = list(csv.DictReader(io.StringIO(archive.read("evidence-index.csv").decode("utf-8-sig"))))
        assert evidence_rows[0]["说明"].startswith("'=")


def test_restore_rejects_malformed_manifest_size_without_overwriting(tmp_path):
    source = MODULE.EvidenceStore(tmp_path / "source" / "cases.json")
    source.add_case(case())
    good = tmp_path / "good.zip"
    source.backup(good)
    with zipfile.ZipFile(good) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["files"]["data.json"]["size"] = None
    members["manifest.json"] = json.dumps(manifest).encode("utf-8")

    bad = tmp_path / "malformed-manifest.zip"
    with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)

    target = MODULE.EvidenceStore(tmp_path / "target" / "cases.json")
    target.add_case(case("KEEP-001"))
    before = (list(target.cases), list(target.events))
    try:
        target.restore(bad)
    except ValueError as exc:
        assert "文件大小无效" in str(exc)
    else:
        raise AssertionError("malformed manifest size should be rejected")
    assert (target.cases, target.events) == before
