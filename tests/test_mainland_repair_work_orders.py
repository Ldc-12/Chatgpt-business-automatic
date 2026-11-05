import csv
import importlib.util
from decimal import Decimal
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "售后维修工单管理助手.py"
spec = importlib.util.spec_from_file_location("repair_work_order", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def order(store, work_id=None, **overrides):
    row = {
        "工单号": work_id or store.next_id("2026-02-03"),
        "登记日期": "2026-02-03",
        "客户姓名": "李先生",
        "联系电话": "13800000000",
        "设备/商品": "笔记本电脑",
        "故障描述": "无法开机",
        "处理进度": "待检测",
        "预计费用(元)": "120.456",
        "实收金额(元)": "0",
        "预约取件日期": "2026-02-05",
        "完工日期": "",
        "备注": "测试工单",
    }
    row.update(overrides)
    return row


def test_add_persist_reload_and_decimal_rounding(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    work_id = store.add(order(store))
    loaded = module.WorkOrderStore(tmp_path / "orders.json")
    assert loaded.rows[0]["工单号"] == work_id
    assert loaded.rows[0]["预计费用(元)"] == "120.46"


def test_next_id_increments_for_same_date(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    first = store.next_id("2026-02-03")
    store.add(order(store, first))
    assert store.next_id("2026-02-03") == "WX20260203-0002"


def test_completed_order_requires_completion_date(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    try:
        store.add(order(store, **{"处理进度": "已完成"}))
    except ValueError as exc:
        assert "完工日期" in str(exc)
    else:
        raise AssertionError("completed order without completion date was accepted")


def test_completed_order_with_date_is_accepted(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    row = order(store, **{"处理进度": "已完成", "完工日期": "2026-02-04"})
    store.add(row)
    assert store.rows[0]["处理进度"] == "已完成"


def test_invalid_dates_and_negative_amounts_are_rejected(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    for changes in ({"登记日期": "2026/02/03"}, {"预约取件日期": "2026-02-02"},
                    {"预计费用(元)": "-1"}, {"实收金额(元)": "NaN"}):
        try:
            store.add(order(store, **changes))
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid order accepted: {changes}")
    assert store.rows == []


def test_duplicate_work_order_id_rejected(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    existing_id = store.rows[0]["工单号"]
    try:
        store.add(order(store, existing_id))
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate work order ID accepted")


def test_update_and_delete_persist(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    work_id = store.add(order(store))
    store.update(work_id, order(store, work_id, **{"处理进度": "维修中"}))
    assert module.WorkOrderStore(store.path).rows[0]["处理进度"] == "维修中"
    store.delete(work_id)
    assert module.WorkOrderStore(store.path).rows == []


def test_csv_roundtrip_and_utf8_bom(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    exported = tmp_path / "export.csv"
    store.export_csv(exported)
    assert exported.read_bytes().startswith(b"\xef\xbb\xbf")
    imported = module.WorkOrderStore(tmp_path / "imported.json")
    assert imported.import_csv(exported) == 1
    assert imported.rows == store.rows


def test_duplicate_csv_import_is_atomic(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(order(store))
    before = list(store.rows)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate CSV import was accepted")
    assert store.rows == before


def test_invalid_csv_row_does_not_modify_existing_data(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    source = tmp_path / "invalid.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        bad = order(store, "WX20260203-0099", **{"预计费用(元)": "not-money"})
        writer.writerow(bad)
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid CSV row was accepted")
    assert len(store.rows) == 1


def test_csv_requires_exact_headers_and_rejects_extra_columns(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    source = tmp_path / "extra.csv"
    source.write_text("工单号,登记日期,多余列\nA,2026-02-03,x", encoding="utf-8-sig")
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("CSV with incomplete headers was accepted")


def test_backup_restore_roundtrip(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(order(store, "WX20260203-0002"))
    store.restore(backup)
    assert len(module.WorkOrderStore(store.path).rows) == 1


def test_invalid_backup_is_rejected_without_overwrite(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    bad = tmp_path / "bad.json"
    bad.write_text('{"format":"unknown","version":99,"orders":[]}', encoding="utf-8")
    try:
        store.restore(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported backup was accepted")
    assert len(store.rows) == 1


def test_filter_and_summary(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    store.add(order(store))
    second = order(store, "WX20260203-0002", **{
        "处理进度": "已完成", "完工日期": "2026-02-04", "实收金额(元)": "100.00",
        "客户姓名": "王女士",
    })
    store.add(second)
    rows = module.filter_orders(store.rows, keyword="王女士", month="2026-02", status="已完成")
    totals = module.summarize_orders(rows)
    assert totals == {"count": 1, "estimated": Decimal("120.46"), "received": Decimal("100.00")}


def test_invalid_month_filter_is_rejected(tmp_path):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    try:
        module.filter_orders([], month="2026/02")
    except ValueError as exc:
        assert "YYYY-MM" in str(exc)
    else:
        raise AssertionError("invalid month filter accepted")


def test_failed_disk_write_rolls_back_memory(tmp_path, monkeypatch):
    store = module.WorkOrderStore(tmp_path / "orders.json")
    original = module.atomic_write
    def fail(*args, **kwargs):
        raise OSError("simulated disk full")
    monkeypatch.setattr(module, "atomic_write", fail)
    try:
        store.add(order(store))
    except OSError:
        pass
    else:
        raise AssertionError("simulated write failure did not propagate")
    assert store.rows == []
    monkeypatch.setattr(module, "atomic_write", original)
