import csv
import importlib.util
from decimal import Decimal
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "费用报销管理助手.py"
spec = importlib.util.spec_from_file_location("expense_reimbursement", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def record(store, expense_id=None, **overrides):
    row = {
        "报销单号": expense_id or store.next_id("2026-01-02"),
        "发生日期": "2026-01-02",
        "报销人": "张三",
        "部门/项目": "项目 A",
        "费用类别": "办公用品",
        "费用说明": "打印纸",
        "金额(元)": "12.345",
        "支付方式": "个人垫付",
        "发票状态": "有发票",
        "报销状态": "待提交",
        "付款日期": "",
        "备注": "",
    }
    row.update(overrides)
    return row


def test_add_persist_reload_and_decimal_rounding(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    expense_id = store.add(record(store))
    loaded = module.ExpenseStore(tmp_path / "expenses.json")
    assert loaded.rows[0]["报销单号"] == expense_id
    assert loaded.rows[0]["金额(元)"] == "12.35"


def test_next_id_increments_for_same_date(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    first = store.next_id("2026-01-02")
    store.add(record(store, first))
    assert store.next_id("2026-01-02") == "BX20260102-0002"


def test_duplicate_id_rejected(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    try:
        store.add(record(store, "BX20260102-0001"))
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate reimbursement ID accepted")


def test_update_and_delete_persist(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    expense_id = store.add(record(store))
    store.update(expense_id, record(store, expense_id, **{"费用说明": "火车票", "金额(元)": "88.00"}))
    assert module.ExpenseStore(tmp_path / "expenses.json").rows[0]["费用说明"] == "火车票"
    store.delete(expense_id)
    assert module.ExpenseStore(tmp_path / "expenses.json").rows == []


def test_invalid_amounts_rejected():
    for value in ("0", "-1", "NaN", "Infinity", "abc", ""):
        try:
            module._amount(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid amount accepted: {value}")


def test_amount_uses_decimal_half_up():
    assert module._amount("1.005") == "1.01"
    assert module._amount("1,234.5") == "1234.50"


def test_invalid_date_and_non_padded_date_rejected():
    for value in ("2026-02-30", "2026-1-2", "yesterday"):
        try:
            module._date(value, "发生日期", required=True)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid date accepted: {value}")


def test_paid_record_requires_payment_date(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    try:
        store.add(record(store, **{"报销状态": "已付款"}))
    except ValueError as exc:
        assert "付款日期" in str(exc)
    else:
        raise AssertionError("paid record without payment date accepted")


def test_paid_record_with_date_is_valid(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store, **{"报销状态": "已付款", "付款日期": "2026-01-10"}))
    assert store.rows[0]["付款日期"] == "2026-01-10"


def test_csv_export_import_roundtrip(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    store.add(record(store, "BX20260102-0002", **{"金额(元)": "23.50", "费用说明": "出租车"}))
    exported = tmp_path / "expenses.csv"
    store.export_csv(exported)
    assert exported.read_bytes().startswith(b"\xef\xbb\xbf")
    target = module.ExpenseStore(tmp_path / "target.json")
    assert target.import_csv(exported) == 2
    assert target.rows == store.rows


def test_csv_duplicate_existing_id_is_atomic(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(record(store, store.rows[0]["报销单号"]))
    before = list(store.rows)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate CSV ID accepted")
    assert store.rows == before


def test_csv_duplicate_inside_batch_is_atomic(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    source = tmp_path / "duplicate-batch.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(record(store))
        writer.writerow(record(store))
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "报销单号重复" in str(exc)
    else:
        raise AssertionError("duplicate IDs inside batch accepted")
    assert store.rows == []


def test_csv_invalid_row_does_not_partially_import(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    source = tmp_path / "invalid.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(record(store))
        writer.writerow(record(store, "BX20260102-0002", **{"金额(元)": "-5"}))
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "第 3 行" in str(exc)
    else:
        raise AssertionError("invalid CSV batch accepted")
    assert store.rows == []


def test_csv_requires_exact_headers(tmp_path):
    source = tmp_path / "wrong-headers.csv"
    source.write_text("报销单号,报销人\nBX1,张三", encoding="utf-8-sig")
    store = module.ExpenseStore(tmp_path / "expenses.json")
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "全部规定字段" in str(exc)
    else:
        raise AssertionError("incomplete CSV headers accepted")


def test_backup_restore_roundtrip(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(record(store, "BX20260102-0002"))
    store.restore(backup)
    assert module.ExpenseStore(tmp_path / "expenses.json").rows == store.rows
    assert len(store.rows) == 1


def test_restore_rejects_wrong_format_without_overwrite(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    backup = tmp_path / "wrong.json"
    backup.write_text('{"format":"unknown","version":99,"records":[]}', encoding="utf-8")
    before = list(store.rows)
    try:
        store.restore(backup)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported backup accepted")
    assert store.rows == before
    assert module.ExpenseStore(tmp_path / "expenses.json").rows == before


def test_restore_rejects_duplicate_ids_without_overwrite(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    payload = {
        "format": module.BACKUP_FORMAT,
        "version": module.BACKUP_VERSION,
        "records": [record(store), record(store)],
    }
    backup = tmp_path / "duplicate.json"
    import json
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(store.rows)
    try:
        store.restore(backup)
    except ValueError as exc:
        assert "报销单号重复" in str(exc)
    else:
        raise AssertionError("duplicate backup records accepted")
    assert store.rows == before


def test_filter_and_summary_use_decimal_totals(tmp_path):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    store.add(record(store))
    store.add(record(store, "BX20260201-0001", **{
        "发生日期": "2026-02-01", "费用类别": "差旅交通",
        "金额(元)": "100.10", "报销状态": "已付款", "付款日期": "2026-02-05",
    }))
    january = module.filter_records(store.rows, month="2026-01")
    totals = module.summarize(january)
    assert totals["count"] == 1
    assert totals["total"] == Decimal("12.35")
    assert totals["pending"] == Decimal("12.35")
    assert totals["paid"] == Decimal("0.00")
    february = module.filter_records(store.rows, status="已付款", category="差旅交通")
    assert len(february) == 1
    assert module.summarize(february)["paid"] == Decimal("100.10")


def test_default_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert module.default_data_path() == tmp_path / "MainlandBusinessTools" / "reimbursements.json"


def test_self_test_product_identity():
    assert module.PRODUCT == "费用报销管理助手"


def test_add_rolls_back_memory_when_disk_write_fails(tmp_path, monkeypatch):
    store = module.ExpenseStore(tmp_path / "expenses.json")
    def fail_write(*args, **kwargs):
        raise OSError("simulated disk full")
    monkeypatch.setattr(module, "atomic_write", fail_write)
    try:
        store.add(record(store))
    except OSError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("simulated disk failure was ignored")
    assert store.rows == []
    assert not (tmp_path / "expenses.json").exists()
