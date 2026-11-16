import csv
import importlib.util
import json
from datetime import date
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "供应商对账与应付账龄管理助手.py"
SPEC = importlib.util.spec_from_file_location("supplier_ap_app", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def invoice(**overrides):
    row = {
        "单据编号": "AP-001",
        "供应商编号": "SUP-01",
        "供应商名称": "华南供应商",
        "发票号": "INV-001",
        "单据日期": "2026-11-01",
        "到期日期": "2026-11-30",
        "金额": "1000.00",
        "备注": "",
    }
    row.update(overrides)
    return row


def statement_csv(path, rows, headers=None):
    headers = headers or MODULE.STATEMENT_FIELDS
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_decimal_rounding_and_rejects_invalid_amounts():
    assert MODULE.decimal_value("12.345", "金额") == "12.35"
    for value in ("", "NaN", "Infinity", "-1", "0", "0.001", "1e999999", "9" * 40):
        try:
            MODULE.decimal_value(value, "金额")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid amount accepted: {value}")


def test_add_invoice_persists_and_reloads(tmp_path):
    path = tmp_path / "ap.json"
    store = MODULE.SupplierAPStore(path)
    store.add_invoice(invoice())
    loaded = MODULE.SupplierAPStore(path)
    assert loaded.invoices[0]["发票号"] == "INV-001"
    assert loaded.invoice_rows("2026-11-15")[0]["未付金额"] == "1000.00"


def test_duplicate_supplier_invoice_number_is_rejected(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    try:
        store.add_invoice(invoice(**{"单据编号": "AP-002"}))
    except ValueError as exc:
        assert "发票号" in str(exc)
    else:
        raise AssertionError("duplicate supplier invoice accepted")
    assert len(store.invoices) == 1


def test_due_date_before_invoice_date_is_rejected(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    try:
        store.add_invoice(invoice(**{"到期日期": "2026-10-31"}))
    except ValueError as exc:
        assert "到期日期" in str(exc)
    else:
        raise AssertionError("invalid due date accepted")
    assert store.invoices == []


def test_partial_payment_updates_outstanding_and_history(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    invoice_id = store.add_invoice(invoice())
    payment_id = store.add_payment(invoice_id, "250.25", "2026-11-10", "BANK-01", "首付款")
    row = store.invoice_rows("2026-11-15")[0]
    assert row["已付金额"] == "250.25"
    assert row["未付金额"] == "749.75"
    assert len(store.payments_for_invoice(invoice_id)) == 1
    assert store.payments_for_invoice(invoice_id)[0]["付款编号"] == payment_id


def test_overpayment_is_rejected_without_mutating_data(tmp_path):
    path = tmp_path / "ap.json"
    store = MODULE.SupplierAPStore(path)
    invoice_id = store.add_invoice(invoice())
    before = path.read_bytes()
    try:
        store.add_payment(invoice_id, "1000.01", "2026-11-10")
    except ValueError as exc:
        assert "超过未付余额" in str(exc)
    else:
        raise AssertionError("overpayment accepted")
    assert store.payments == []
    assert path.read_bytes() == before


def test_payment_date_before_invoice_date_is_rejected(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    invoice_id = store.add_invoice(invoice())
    try:
        store.add_payment(invoice_id, "100", "2026-10-31")
    except ValueError as exc:
        assert "不能早于单据日期" in str(exc)
    else:
        raise AssertionError("early payment accepted")
    assert store.payments == []


def test_invoice_with_payments_cannot_be_deleted(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    invoice_id = store.add_invoice(invoice())
    store.add_payment(invoice_id, "100", "2026-11-10")
    try:
        store.delete_invoice(invoice_id)
    except ValueError as exc:
        assert "不能删除" in str(exc)
    else:
        raise AssertionError("invoice with payments deleted")
    assert len(store.invoices) == 1


def test_invoice_without_payments_can_be_deleted(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    invoice_id = store.add_invoice(invoice())
    store.delete_invoice(invoice_id)
    assert store.invoices == []


def test_aging_bucket_boundaries(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    as_of = date(2026, 12, 31)
    due_dates = [
        ("2026-12-31", "未到期"),
        ("2026-12-30", "逾期1-30天"),
        ("2026-12-01", "逾期1-30天"),
        ("2026-11-30", "逾期31-60天"),
        ("2026-10-31", "逾期31-60天"),
        ("2026-10-02", "逾期61-90天"),
        ("2026-10-01", "逾期90天以上"),
    ]
    for index, (due, _) in enumerate(due_dates, start=1):
        store.add_invoice(invoice(
            **{
                "单据编号": f"AP-{index:03d}",
                "发票号": f"INV-{index:03d}",
                "单据日期": "2026-09-01",
                "到期日期": due,
            }
        ))
    rows = {row["发票号"]: row["账龄区间"] for row in store.aging_report(as_of.isoformat())}
    assert [rows[f"INV-{index:03d}"] for index in range(1, 8)] == [bucket for _, bucket in due_dates]


def test_fully_paid_invoice_is_not_in_aging_report(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    invoice_id = store.add_invoice(invoice())
    store.add_payment(invoice_id, "1000", "2026-11-10")
    assert store.aging_report("2026-12-31") == []
    assert store.invoice_rows("2026-12-31")[0]["账龄区间"] == "已结清"


def test_aging_summary_groups_by_supplier_and_bucket(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    store.add_invoice(invoice(
        **{"单据编号": "AP-002", "发票号": "INV-002", "金额": "200", "到期日期": "2026-12-31"}
    ))
    rows = store.aging_summary("2026-12-15")
    assert len(rows) == 1
    assert rows[0]["供应商编号"] == "SUP-01"
    assert rows[0]["未付合计"] == "1200.00"
    assert rows[0]["逾期1-30天"] == "1000.00"
    assert rows[0]["未到期"] == "200.00"


def test_due_list_includes_overdue_and_upcoming_within_horizon(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    store.add_invoice(invoice(
        **{"单据编号": "AP-002", "发票号": "INV-002", "到期日期": "2026-12-20"}
    ))
    store.add_invoice(invoice(
        **{"单据编号": "AP-003", "发票号": "INV-003", "到期日期": "2027-02-01"}
    ))
    rows = store.due_list("2026-12-15", 30)
    assert {row["发票号"] for row in rows} == {"INV-001", "INV-002"}
    try:
        store.due_list("2026-12-15", 366)
    except ValueError as exc:
        assert "0 至 365" in str(exc)
    else:
        raise AssertionError("excessive reminder horizon accepted")


def test_invoice_csv_roundtrip_is_utf8_bom_and_formula_safe(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "one.json")
    store.add_invoice(invoice(**{"供应商名称": "=HYPERLINK('x')"}))
    output = tmp_path / "invoices.csv"
    store.export_invoices_csv(output)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    imported = MODULE.SupplierAPStore(tmp_path / "two.json")
    assert imported.import_invoices_csv(output) == 1
    assert imported.invoices[0]["供应商名称"].startswith("'=HYPERLINK(")


def test_invoice_csv_duplicate_import_is_atomic(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    source = tmp_path / "duplicate.csv"
    statement_csv(source, [invoice(**{"单据编号": "AP-002"})], headers=MODULE.INVOICE_FIELDS)
    before = (tmp_path / "ap.json").read_bytes()
    try:
        store.import_invoices_csv(source)
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate CSV import accepted")
    assert len(store.invoices) == 1
    assert (tmp_path / "ap.json").read_bytes() == before


def test_invalid_invoice_csv_does_not_partially_import(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    source = tmp_path / "bad.csv"
    rows = [invoice(), invoice(**{"单据编号": "AP-002", "发票号": "INV-002", "金额": "bad"})]
    statement_csv(source, rows, headers=MODULE.INVOICE_FIELDS)
    try:
        store.import_invoices_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid CSV imported")
    assert store.invoices == []


def test_statement_reconciliation_detects_amount_name_date_and_missing_local(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    store.add_invoice(invoice(**{
        "单据编号": "AP-002", "发票号": "INV-002", "单据日期": "2026-11-05", "金额": "300"
    }))
    source = tmp_path / "statement.csv"
    statement_csv(source, [
        {"供应商编号": "SUP-01", "供应商名称": "错误名称", "发票号": "INV-001", "单据日期": "2026-11-02", "金额": "900"},
        {"供应商编号": "SUP-01", "供应商名称": "华南供应商", "发票号": "INV-999", "单据日期": "2026-11-06", "金额": "500"},
    ])
    issues = store.reconcile_statement_csv(source)
    types = [row["差异类型"] for row in issues]
    assert any("供应商名称不一致" in item for item in types)
    assert any("单据日期不一致" in item for item in types)
    assert any("金额不一致" in item for item in types)
    assert any("本地缺少单据" in item for item in types)
    assert any("对账单缺少本地单据" in item for item in types)
    assert len(store.invoices) == 2


def test_statement_duplicate_supplier_invoice_is_rejected(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    source = tmp_path / "statement.csv"
    row = {"供应商编号": "SUP-01", "供应商名称": "华南供应商", "发票号": "INV-1", "单据日期": "2026-11-01", "金额": "100"}
    statement_csv(source, [row, row])
    try:
        store.reconcile_statement_csv(source)
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate statement line accepted")


def test_statement_header_mismatch_is_rejected(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    source = tmp_path / "statement.csv"
    statement_csv(source, [], headers=["供应商", "发票", "金额"])
    try:
        store.reconcile_statement_csv(source)
    except ValueError as exc:
        assert "表头" in str(exc)
    else:
        raise AssertionError("invalid statement header accepted")


def test_reconciliation_export_is_safe_and_bom_encoded(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice())
    source = tmp_path / "statement.csv"
    statement_csv(source, [{
        "供应商编号": "SUP-01", "供应商名称": "=CMD()", "发票号": "INV-001",
        "单据日期": "2026-11-01", "金额": "1000",
    }])
    issues = store.reconcile_statement_csv(source)
    output = tmp_path / "diff.csv"
    store.export_reconciliation_csv(output, issues)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(output.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["供应商名称"].startswith("'=CMD()")


def test_reconciliation_does_not_mutate_local_data(tmp_path):
    path = tmp_path / "ap.json"
    store = MODULE.SupplierAPStore(path)
    store.add_invoice(invoice())
    before = path.read_bytes()
    source = tmp_path / "statement.csv"
    statement_csv(source, [{"供应商编号": "SUP-01", "供应商名称": "华南供应商", "发票号": "INV-001", "单据日期": "2026-11-01", "金额": "1000.00"}])
    store.reconcile_statement_csv(source)
    assert path.read_bytes() == before


def test_backup_restore_preserves_invoices_and_payments(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "one.json")
    invoice_id = store.add_invoice(invoice())
    store.add_payment(invoice_id, "200", "2026-11-10", "PAY-01")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    restored = MODULE.SupplierAPStore(tmp_path / "two.json")
    restored.restore(backup)
    assert restored.invoices == store.invoices
    assert restored.payments == store.payments
    assert restored.invoice_rows("2026-11-15")[0]["未付金额"] == "800.00"


def test_corrupted_backup_is_rejected_without_overwriting_current_data(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "current.json")
    store.add_invoice(invoice())
    before = (tmp_path / "current.json").read_bytes()
    backup = tmp_path / "bad.json"
    backup.write_text(json.dumps({"格式": MODULE.FORMAT, "版本": MODULE.VERSION, "应付单据": [], "付款记录": [], "SHA256": "bad"}), encoding="utf-8")
    try:
        store.restore(backup)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("corrupted backup restored")
    assert (tmp_path / "current.json").read_bytes() == before
    assert len(store.invoices) == 1


def test_unsupported_backup_format_is_rejected(tmp_path):
    payload = {"格式": "other", "版本": 1, "应付单据": [], "付款记录": []}
    try:
        MODULE.SupplierAPStore.decode(payload)
    except ValueError as exc:
        assert "格式或版本" in str(exc)
    else:
        raise AssertionError("unsupported backup accepted")


def test_failed_atomic_write_rolls_back_memory_and_disk(tmp_path, monkeypatch):
    path = tmp_path / "ap.json"
    store = MODULE.SupplierAPStore(path)
    store.add_invoice(invoice())
    before = path.read_bytes()
    original = MODULE.atomic_write
    def fail_write(target, data):
        raise OSError("simulated disk full")
    monkeypatch.setattr(MODULE, "atomic_write", fail_write)
    try:
        store.add_invoice(invoice(**{"单据编号": "AP-002", "发票号": "INV-002"}))
    except OSError:
        pass
    else:
        raise AssertionError("failed write was ignored")
    assert len(store.invoices) == 1
    assert path.read_bytes() == before
    monkeypatch.setattr(MODULE, "atomic_write", original)


def test_oversized_local_file_is_rejected_before_json_parse(tmp_path):
    path = tmp_path / "ap.json"
    path.write_bytes(b"x" * (MODULE.MAX_BACKUP_BYTES + 1))
    try:
        MODULE.SupplierAPStore(path)
    except ValueError as exc:
        assert "100 MiB" in str(exc)
    else:
        raise AssertionError("oversized local file accepted")


def test_gui_exposes_reconciliation_aging_and_backup_actions():
    source = PATH.read_text(encoding="utf-8")
    for label in ("对账单核对", "账龄报表", "供应商汇总", "备份", "恢复"):
        assert label in source
    assert "self.store.reconcile_statement_csv(path)" in source
    assert "self.store.export_aging_csv(path, day)" in source


def test_empty_supplier_statement_is_not_reported_as_clean(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    source = tmp_path / "empty.csv"
    statement_csv(source, [])
    try:
        store.reconcile_statement_csv(source)
    except ValueError as exc:
        assert "没有数据" in str(exc)
    else:
        raise AssertionError("empty statement was treated as a clean reconciliation")


def test_statement_coverage_ranges_are_scoped_per_supplier(tmp_path):
    store = MODULE.SupplierAPStore(tmp_path / "ap.json")
    store.add_invoice(invoice(**{"单据编号": "A-1", "供应商编号": "SUP-A", "供应商名称": "供应商A", "发票号": "A-INV-1", "单据日期": "2026-11-01"}))
    store.add_invoice(invoice(**{"单据编号": "A-2", "供应商编号": "SUP-A", "供应商名称": "供应商A", "发票号": "A-INV-2", "单据日期": "2026-11-15"}))
    store.add_invoice(invoice(**{"单据编号": "B-1", "供应商编号": "SUP-B", "供应商名称": "供应商B", "发票号": "B-INV-1", "单据日期": "2026-11-30"}))
    source = tmp_path / "multi-supplier.csv"
    statement_csv(source, [
        {"供应商编号": "SUP-A", "供应商名称": "供应商A", "发票号": "A-INV-1", "单据日期": "2026-11-01", "金额": "1000"},
        {"供应商编号": "SUP-B", "供应商名称": "供应商B", "发票号": "B-INV-1", "单据日期": "2026-11-30", "金额": "1000"},
    ])
    issues = store.reconcile_statement_csv(source)
    assert not any(row["发票号"] == "A-INV-2" and "对账单缺少本地单据" in row["差异类型"] for row in issues)
