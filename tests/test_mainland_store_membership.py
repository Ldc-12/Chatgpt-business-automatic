import csv
import hashlib
import json
from pathlib import Path

import pytest

from src import store_membership as MODULE


def add_member(store, **changes):
    row = {"会员姓名": "测试会员", "联系电话": "13800000000", "备注": "普通会员"}
    row.update(changes)
    return store.add_member(row)


def test_recharge_consume_refund_points_and_persistence_roundtrip(tmp_path):
    path = tmp_path / "members.json"
    store = MODULE.MemberStore(path)
    member_id = add_member(store)
    store.recharge(member_id, "100.00")
    consume_id = store.consume(member_id, "30.00")
    store.refund(member_id, "10.00", consume_id)
    store.redeem_points(member_id, 5)

    assert store.get_balance(member_id) == {"储值余额": "80.00", "积分余额": 15}
    loaded = MODULE.MemberStore(path)
    assert loaded.get_balance(member_id) == store.get_balance(member_id)
    assert len(loaded.transactions) == 4
    assert loaded.audit_summary()["事件数"] == 5


def test_consume_cannot_make_stored_value_negative_and_is_atomic(tmp_path):
    path = tmp_path / "members.json"
    store = MODULE.MemberStore(path)
    member_id = add_member(store)
    store.recharge(member_id, "20")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="储值余额不足"):
        store.consume(member_id, "20.01")
    assert path.read_bytes() == before
    assert store.get_balance(member_id)["储值余额"] == "20.00"


def test_partial_refunds_reverse_points_proportionally_and_cap_original_amount(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "100")
    consume_id = store.consume(member_id, "30")
    store.refund(member_id, "10", consume_id)
    assert store.get_balance(member_id)["积分余额"] == 20
    store.refund(member_id, "20", consume_id)
    assert store.get_balance(member_id) == {"储值余额": "100.00", "积分余额": 0}
    assert store.list_refundable_transactions(member_id) == []
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="累计退款金额"):
        store.refund(member_id, "0.01", consume_id)
    assert store.path.read_bytes() == before


def test_refund_must_reference_same_members_prior_consumption(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    first = add_member(store, **{"会员姓名": "甲"})
    second = add_member(store, **{"会员姓名": "乙"})
    store.recharge(first, "50")
    store.recharge(second, "50")
    consume_id = store.consume(first, "10")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="此前的一笔消费流水"):
        store.refund(second, "5", consume_id)
    assert store.path.read_bytes() == before


def test_points_redemption_requires_positive_integer_and_sufficient_points(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "10")
    with pytest.raises(ValueError, match="积分余额不足"):
        store.redeem_points(member_id, 1)
    store.consume(member_id, "5")
    with pytest.raises(ValueError, match="正整数"):
        store.redeem_points(member_id, 0)
    with pytest.raises(ValueError, match="整数"):
        store.redeem_points(member_id, "1.5")
    store.redeem_points(member_id, 3)
    assert store.get_balance(member_id)["积分余额"] == 2


def test_inactive_member_cannot_start_new_transactions(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "20")
    store.set_member_status(member_id, "停用", reason="会员申请停用")
    with pytest.raises(ValueError, match="停用会员"):
        store.recharge(member_id, "1")
    assert store.get_balance(member_id)["储值余额"] == "20.00"
    store.set_member_status(member_id, "正常", reason="恢复服务")
    store.recharge(member_id, "1")
    assert store.get_balance(member_id)["储值余额"] == "21.00"


def test_duplicate_member_ids_are_rejected_without_mutating_store(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    store.add_member({"会员编号": "M-001", "会员姓名": "甲"})
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="已存在"):
        store.add_member({"会员编号": "M-001", "会员姓名": "乙"})
    assert store.path.read_bytes() == before
    assert len(store.members) == 1


def test_member_csv_import_export_is_utf8_bom_formula_safe_and_roundtrips(tmp_path):
    source = tmp_path / "members.csv"
    rows = [
        {"会员编号": "M-CSV-1", "会员姓名": "甲", "联系电话": "13800000000", "入会日期": "2026-11-20", "状态": "正常", "备注": "=HYPERLINK(\"x\")"},
        {"会员编号": "M-CSV-2", "会员姓名": "乙", "联系电话": "", "入会日期": "2026-11-19", "状态": "正常", "备注": "普通"},
    ]
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.MEMBER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    store = MODULE.MemberStore(tmp_path / "members.json")
    assert store.import_members_csv(source) == 2
    exported = tmp_path / "export.csv"
    store.export_members_csv(exported)
    assert exported.read_bytes().startswith(b"\xef\xbb\xbf")
    text = exported.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in text
    imported = MODULE.MemberStore(tmp_path / "second.json")
    assert imported.import_members_csv(exported) == 2
    assert imported.members[0]["备注"].startswith("'=")


def test_member_csv_batch_import_is_all_or_nothing(tmp_path):
    source = tmp_path / "invalid.csv"
    rows = [
        {"会员编号": "M-OK", "会员姓名": "正常会员", "联系电话": "", "入会日期": "2026-11-20", "状态": "正常", "备注": ""},
        {"会员编号": "M-BAD", "会员姓名": "", "联系电话": "", "入会日期": "2026-11-20", "状态": "正常", "备注": ""},
    ]
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.MEMBER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    store = MODULE.MemberStore(tmp_path / "members.json")
    with pytest.raises(ValueError, match="会员姓名"):
        store.import_members_csv(source)
    assert store.members == []
    assert not store.path.exists()


def test_member_csv_import_rejects_duplicate_existing_ids(tmp_path):
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.MEMBER_FIELDS)
        writer.writeheader()
        writer.writerow({"会员编号": "M-001", "会员姓名": "重复", "入会日期": "2026-11-20", "状态": "正常"})
    store = MODULE.MemberStore(tmp_path / "members.json")
    store.add_member({"会员编号": "M-001", "会员姓名": "已有"})
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="重复会员编号"):
        store.import_members_csv(source)
    assert store.path.read_bytes() == before


def test_transaction_export_is_formula_safe_and_balance_export_is_derived(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "25", operator="=HYPERLINK(\"x\")", note="@formula")
    transactions = tmp_path / "transactions.csv"
    balances = tmp_path / "balances.csv"
    store.export_transactions_csv(transactions)
    store.export_balances_csv(balances)
    assert transactions.read_bytes().startswith(b"\xef\xbb\xbf")
    text = transactions.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in text
    assert "'@formula" in text
    rows = list(csv.DictReader(balances.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["储值余额"] == "25.00"
    assert rows[0]["积分余额"] == "0"


def test_refund_after_redeemed_points_creates_debt_and_exports_numeric_delta(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "100")
    consume_id = store.consume(member_id, "30")
    store.redeem_points(member_id, 30)
    store.refund(member_id, "30", consume_id)

    assert store.get_balance(member_id)["积分余额"] == -30
    with pytest.raises(ValueError, match="积分余额不足"):
        store.redeem_points(member_id, 1)

    # Later earned points first offset the refund clawback debt.
    store.consume(member_id, "35")
    assert store.get_balance(member_id)["积分余额"] == 5

    exported = tmp_path / "transactions.csv"
    store.export_transactions_csv(exported)
    rows = list(csv.DictReader(exported.open(encoding="utf-8-sig", newline="")))
    refund_row = next(row for row in rows if row["交易类型"] == "退款")
    assert refund_row["积分变动"] == "-30"


def test_signed_formula_text_is_still_escaped_in_csv(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "10", note='-1+HYPERLINK("x")')
    exported = tmp_path / "transactions.csv"
    store.export_transactions_csv(exported)
    rows = list(csv.DictReader(exported.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["备注"] == ''-1+HYPERLINK("x")'


def test_backup_restore_replaces_data_and_records_restore_event(tmp_path):
    path = tmp_path / "members.json"
    store = MODULE.MemberStore(path)
    member_id = add_member(store)
    store.recharge(member_id, "50")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    add_member(store, **{"会员姓名": "后加会员"})
    assert len(store.members) == 2
    store.restore(backup)
    assert len(store.members) == 1
    assert store.get_balance(member_id)["储值余额"] == "50.00"
    assert store.events[-1]["action"] == "恢复备份"


def test_backup_hash_tampering_is_rejected_without_overwriting_current_data(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    add_member(store)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add_member({"会员姓名": "当前会员"})
    before = store.path.read_bytes()
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["会员"][0]["会员姓名"] = "被篡改"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(corrupt)
    assert store.path.read_bytes() == before


def test_rehashed_backup_with_tampered_audit_event_is_still_rejected(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    add_member(store)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["操作日志"][0]["reason"] = "tampered"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = hashlib.sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "rehashed.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="操作日志 SHA256"):
        store.restore(corrupt)
    assert store.path.read_bytes() == before


def test_rehashed_transaction_snapshot_tampering_is_rejected_by_ledger_replay(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    store.recharge(member_id, "40")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["交易流水"][0]["储值余额"] = "999.00"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = hashlib.sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "rehashed-tx.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="储值余额快照"):
        store.restore(corrupt)


def test_failed_atomic_write_preserves_memory_and_disk(tmp_path, monkeypatch):
    store = MODULE.MemberStore(tmp_path / "members.json")
    member_id = add_member(store)
    before = store.path.read_bytes()
    original_members = list(store.members)

    def fail_write(path, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(MODULE, "atomic_write", fail_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.recharge(member_id, "10")
    assert store.path.read_bytes() == before
    assert store.members == original_members
    assert store.transactions == []


def test_oversized_local_file_is_rejected_without_modification(tmp_path, monkeypatch):
    path = tmp_path / "members.json"
    path.write_text("{}", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(MODULE, "MAX_BACKUP_BYTES", 1)
    with pytest.raises(ValueError, match="100 MiB"):
        MODULE.MemberStore(path)
    assert path.read_bytes() == before


def test_invalid_money_and_member_fields_are_rejected():
    for value in ("NaN", "Infinity", "-1", "1e999999", "1000000000000"):
        with pytest.raises(ValueError):
            MODULE.money_value(value, "金额")
    with pytest.raises(ValueError, match="会员姓名"):
        MODULE.normalize_member({"会员姓名": ""})
    with pytest.raises(ValueError, match="会员编号"):
        MODULE.normalize_member({"会员编号": "../bad", "会员姓名": "测试"})


def test_summary_reports_stored_value_and_points_totals(tmp_path):
    store = MODULE.MemberStore(tmp_path / "members.json")
    first = add_member(store, **{"会员姓名": "甲"})
    second = add_member(store, **{"会员姓名": "乙"})
    store.recharge(first, "10")
    store.recharge(second, "20")
    store.consume(second, "5")
    summary = store.summary()
    assert summary["会员总数"] == 2
    assert summary["正常会员"] == 2
    assert summary["储值余额合计"] == "25.00"
    assert summary["积分余额合计"] == 5
    assert summary["交易流水数"] == 3


def test_self_test_and_gui_entrypoint_are_noninteractive():
    MODULE.self_test()
    app = (Path(__file__).resolve().parents[1] / "apps" / "门店会员储值与积分台账助手.py").read_text(encoding="utf-8")
    assert "MAINLAND_EXE_SELF_TEST" in app
    assert "os._exit(0)" in app
    assert "require_license(PRODUCT)" in app
    assert "MemberStore(default_data_path())" in app
    assert "def refund(" in app
    assert "def backup(" in app
    assert "def restore(" in app


def test_no_network_or_external_ai_dependency_is_added():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src" / "store_membership.py").read_text(encoding="utf-8")
    app = (root / "apps" / "门店会员储值与积分台账助手.py").read_text(encoding="utf-8")
    for marker in ("requests", "urllib.request", "http://", "https://", "openai", "ChatGPT"):
        assert marker not in core
        assert marker not in app
