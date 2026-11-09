import csv
import json
from pathlib import Path

from src import rental_ledger as module


def lease(lease_id="R001", **overrides):
    row = {
        "租约编号": lease_id, "房产/房间": "A-101", "租客": "测试租客",
        "联系电话": "13800000000", "起租日期": "2026-01-15",
        "退租日期": "2026-03-31", "月租金(元)": "3100",
        "每月缴租日": "5", "应收押金(元)": "3100",
        "状态": "有效", "备注": "",
    }
    row.update(overrides)
    return row


def payment(payment_id="P001", charge_id="R001:2026-01", **overrides):
    row = {
        "收款编号": payment_id, "账单编号": charge_id,
        "收款日期": "2026-01-20", "金额(元)": "500",
        "方式": "银行转账", "流水号": "TX-001", "备注": "",
    }
    row.update(overrides)
    return row


def deposit(deposit_id="D001", **overrides):
    row = {
        "押金流水号": deposit_id, "租约编号": "R001",
        "日期": "2026-01-15", "类型": "收取",
        "金额(元)": "3100", "说明": "首期押金",
    }
    row.update(overrides)
    return row


def prepared_store(path):
    store = module.RentalStore(path)
    store.add_lease(lease())
    store.generate_charges("R001", "2026-03")
    return store


def test_month_proration_and_due_date_clamps_to_lease_start_and_end():
    first = module.charge_for_month(module.normalize_lease(lease()), "2026-01")
    assert first["应收金额(元)"] == "1700.00"
    assert first["应收日期"] == "2026-01-15"

    last = module.charge_for_month(
        module.normalize_lease(lease(退租日期="2026-01-10", 起租日期="2026-01-01")),
        "2026-01",
    )
    assert last["应收金额(元)"] == "1000.00"
    assert last["应收日期"] == "2026-01-10"


def test_full_month_proration_and_february_day_count():
    row = module.charge_for_month(
        module.normalize_lease(lease(起租日期="2026-02-01", 退租日期="2026-02-28")),
        "2026-02",
    )
    assert row["应收金额(元)"] == "3100.00"
    assert row["应收日期"] == "2026-02-05"


def test_generate_charges_is_idempotent_and_respects_lease_end(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    assert len(store.charges) == 3
    assert [x["账期(月)"] for x in store.charges] == ["2026-01", "2026-02", "2026-03"]
    assert store.charges[0]["应收金额(元)"] == "1700.00"
    assert store.generate_charges("R001", "2026-03") == 0
    assert len(store.charges) == 3


def test_payment_partial_full_and_overpayment_rejection(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    store.add_payment(payment())
    row = store.rent_rows("2026-01-21")[0]
    assert row["已收金额(元)"] == "500.00"
    assert row["未收金额(元)"] == "1200.00"
    assert row["状态"] == "部分收款"

    store.add_payment(payment("P002", 流水号="TX-002", **{"金额(元)": "1200"}))
    row = store.rent_rows("2026-01-21")[0]
    assert row["状态"] == "已结清"
    try:
        store.add_payment(payment("P003", 流水号="TX-003", **{"金额(元)": "0.01"}))
    except ValueError as exc:
        assert "超过应收金额" in str(exc)
    else:
        raise AssertionError("payment above charge amount accepted")
    assert len(store.payments) == 2


def test_payment_rejects_unknown_charge_and_duplicate_id(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    try:
        store.add_payment(payment(账单编号="MISSING"))
    except ValueError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("payment with missing charge accepted")
    store.add_payment(payment())
    try:
        store.add_payment(payment())
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate payment ID accepted")


def test_payment_update_overpayment_rolls_back_record_and_disk(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    store.add_payment(payment())
    before = store.path.read_bytes()
    try:
        store.update_payment("P001", payment(**{"金额(元)": "1800"}))
    except ValueError as exc:
        assert "超过应收金额" in str(exc)
    else:
        raise AssertionError("overpaid payment update accepted")
    assert store.payments[0]["金额(元)"] == "500.00"
    assert store.path.read_bytes() == before


def test_deposit_balance_and_no_negative_refund(tmp_path):
    store = module.RentalStore(tmp_path / "rental.json")
    store.add_lease(lease())
    store.add_deposit(deposit())
    store.add_deposit(deposit("D002", 类型="扣除", 说明="维修扣款", **{"金额(元)": "500"}))
    assert store.deposit_balance("R001") == "2600.00"
    store.add_deposit(deposit("D003", 类型="退还", 说明="退租退还", **{"金额(元)": "2600"}))
    assert store.deposit_balance("R001") == "0.00"
    try:
        store.add_deposit(deposit("D004", 类型="退还", 说明="超额退还", **{"金额(元)": "0.01"}))
    except ValueError as exc:
        assert "超过当时可用余额" in str(exc)
    else:
        raise AssertionError("negative deposit balance accepted")


def test_deposit_events_are_validated_in_date_order(tmp_path):
    store = module.RentalStore(tmp_path / "rental.json")
    store.add_lease(lease())
    store.add_deposit(deposit("Z-RECEIVE", 日期="2026-01-15"))
    store.add_deposit(deposit("A-REFUND", 日期="2026-01-15", 类型="退还", 说明="部分退还", **{"金额(元)": "100"}))
    assert store.deposit_balance("R001") == "3000.00"


def test_risk_rules_flag_overdue_rent_expiring_lease_and_short_deposit(tmp_path):
    store = module.RentalStore(tmp_path / "rental.json")
    store.add_lease(lease(退租日期="2026-02-15"))
    store.generate_charges("R001", "2026-02")
    store.add_deposit(deposit(**{"金额(元)": "1000"}))
    codes = {x["规则编号"] for x in store.risk_findings("2026-02-10")}
    assert "RENT_OVERDUE" in codes
    assert "LEASE_END_WITHIN_30_DAYS" in codes
    assert "DEPOSIT_BELOW_EXPECTED" in codes


def test_expired_active_lease_is_flagged(tmp_path):
    store = module.RentalStore(tmp_path / "rental.json")
    store.add_lease(lease(退租日期="2026-01-31"))
    codes = {x["规则编号"] for x in store.risk_findings("2026-02-10")}
    assert "ACTIVE_LEASE_PAST_END" in codes


def test_csv_roundtrip_for_all_four_ledgers(tmp_path):
    source = prepared_store(tmp_path / "source.json")
    source.add_payment(payment())
    source.add_deposit(deposit())
    target = module.RentalStore(tmp_path / "target.json")
    for kind in ("leases", "charges", "payments", "deposits"):
        csv_path = tmp_path / f"{kind}.csv"
        source.export_csv(kind, csv_path)
        assert target.import_csv(kind, csv_path) == len(getattr(source, kind))
    assert target.leases == source.leases
    assert target.charges == source.charges
    assert target.payments == source.payments
    assert target.deposits == source.deposits


def test_csv_tampered_charge_amount_is_rejected_atomically(tmp_path):
    source = prepared_store(tmp_path / "source.json")
    csv_path = tmp_path / "charges.csv"
    source.export_csv("charges", csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    rows[0]["应收金额(元)"] = "1.00"
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.CHARGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    target = module.RentalStore(tmp_path / "target.json")
    target.add_lease(lease())
    before = target.charges[:]
    try:
        target.import_csv("charges", bad)
    except ValueError as exc:
        assert "折算规则计算结果不一致" in str(exc)
    else:
        raise AssertionError("tampered charge amount accepted")
    assert target.charges == before


def test_csv_overpayment_is_rejected_without_partial_import(tmp_path):
    target = prepared_store(tmp_path / "target.json")
    bad = tmp_path / "overpay.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.PAYMENT_FIELDS)
        writer.writeheader()
        writer.writerow(payment("P001", **{"金额(元)": "1000"}))
        writer.writerow(payment("P002", **{"金额(元)": "1000"}))
    before = target.payments[:]
    try:
        target.import_csv("payments", bad)
    except ValueError as exc:
        assert "超过应收金额" in str(exc)
    else:
        raise AssertionError("overpayment CSV accepted")
    assert target.payments == before


def test_backup_restore_and_relationship_validation_are_atomic(tmp_path):
    source = prepared_store(tmp_path / "source.json")
    source.add_payment(payment())
    source.add_deposit(deposit())
    backup = tmp_path / "backup.json"
    source.backup(backup)
    target = module.RentalStore(tmp_path / "target.json")
    target.restore(backup)
    assert target.leases == source.leases
    assert target.charges == source.charges
    assert target.payments == source.payments
    assert target.deposits == source.deposits

    before = target.path.read_bytes()
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["payments"][0]["账单编号"] = "MISSING"
    bad = tmp_path / "bad-backup.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        target.restore(bad)
    except ValueError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("orphan payment in backup accepted")
    assert target.path.read_bytes() == before


def test_project_and_charge_linked_records_cannot_be_deleted(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    store.add_payment(payment())
    try:
        store.delete_charge("R001:2026-01")
    except ValueError as exc:
        assert "已有收款" in str(exc)
    else:
        raise AssertionError("charge with payments deleted")
    try:
        store.delete_lease("R001")
    except ValueError as exc:
        assert "关联账单" in str(exc)
    else:
        raise AssertionError("lease with linked records deleted")


def test_failed_write_rolls_back_records_and_full_audit_history(tmp_path):
    store = module.RentalStore(tmp_path / "rental.json")
    store.audit = [
        {"时间": "2026-01-01T00:00:00", "类别": "租约",
         "编号": "OLD", "操作": "历史", "说明": str(i)}
        for i in range(module.AUDIT_LIMIT)
    ]
    before = store.audit[:]
    store.save = lambda: (_ for _ in ()).throw(OSError("simulated write failure"))
    try:
        store.add_lease(lease())
    except OSError as exc:
        assert "simulated write failure" in str(exc)
    else:
        raise AssertionError("write failure not propagated")
    assert store.leases == []
    assert store.audit == before
    assert len(store.audit) == module.AUDIT_LIMIT


def test_invalid_lease_dates_and_due_day_are_rejected():
    bad = lease(退租日期="2025-12-31")
    try:
        module.normalize_lease(bad)
    except ValueError as exc:
        assert "不能早于" in str(exc)
    else:
        raise AssertionError("end date before start accepted")
    bad = lease(每月缴租日="31")
    try:
        module.normalize_lease(bad)
    except ValueError as exc:
        assert "1 到 28" in str(exc)
    else:
        raise AssertionError("invalid due day accepted")


def test_backup_rejects_wrong_root_shape_and_preserves_existing_data(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    before = store.path.read_bytes()
    bad = tmp_path / "wrong-root.json"
    bad.write_text("[]", encoding="utf-8")
    try:
        store.restore(bad)
    except ValueError as exc:
        assert "格式不受支持" in str(exc)
    else:
        raise AssertionError("wrong backup root accepted")
    assert store.path.read_bytes() == before


def test_backup_write_is_atomic_and_preserves_previous_file(tmp_path, monkeypatch):
    store = prepared_store(tmp_path / "rental.json")
    backup = tmp_path / "backup.json"
    backup.write_text("previous-valid-backup", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        store.backup(backup)
    except OSError as exc:
        assert "simulated replace failure" in str(exc)
    else:
        raise AssertionError("simulated backup replace failure not propagated")
    assert backup.read_text(encoding="utf-8") == "previous-valid-backup"
    assert not list(tmp_path.glob("backup.json.*.tmp"))

def test_lease_billing_terms_are_locked_after_charges_are_generated(tmp_path):
    store = prepared_store(tmp_path / "rental.json")
    updated = lease(月租金="3500")
    try:
        store.update_lease("R001", updated)
    except ValueError as exc:
        assert "已有租金账单" in str(exc)
    else:
        raise AssertionError("lease billing terms changed after bills were generated")
    assert store.leases[0]["月租金(元)"] == "3100.00"
    contact_update = lease(联系电话="13900000000")
    store.update_lease("R001", contact_update)
    assert store.leases[0]["联系电话"] == "13900000000"