from datetime import date, timedelta
import csv
import hashlib
import io
import json
import pytest
from src import store_purchase_orders as MODULE


def line(**changes):
    today = date.today()
    row = {
        "明细编号": "PO-LINE-001", "采购单号": "PO-2026-001",
        "供应商": "供应商甲", "下单日期": today.isoformat(),
        "预计到货日期": (today + timedelta(days=3)).isoformat(),
        "采购员": "张三", "SKU": "SKU-001", "商品名称": "测试商品",
        "订购数量": "10", "采购单价": "5.00", "备注": "",
    }
    row.update(changes)
    return row


def receipt(**changes):
    row = {
        "到货记录编号": "PO-RCV-001", "明细编号": "PO-LINE-001",
        "到货日期": date.today().isoformat(), "合格数量": "3",
        "破损数量": "1", "拒收数量": "0", "处理备注": "首批到货",
    }
    row.update(changes)
    return row


def store_with_line(tmp_path, **changes):
    store = MODULE.PurchaseOrderStore(tmp_path / "purchase-orders.json")
    store.add_line(line(**changes))
    return store


def test_purchase_order_and_receipts_persist_and_reload(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt())
    loaded = MODULE.PurchaseOrderStore(store.path)
    assert loaded.lines == store.lines
    assert loaded.receipts == store.receipts
    assert loaded.summary()["采购单数"] == 1


def test_partial_receipt_tracks_good_damaged_and_outstanding_amount(tmp_path):
    store = store_with_line(tmp_path)
    assert store.report_rows()[0]["状态"] == "待到货"
    store.record_receipt(receipt())
    row = store.report_rows()[0]
    assert row["到货总量"] == "4"
    assert row["合格到货"] == "3"
    assert row["破损数量"] == "1"
    assert row["剩余待到货"] == "7"
    assert row["待到货金额"] == "35.00"
    assert row["已验收金额"] == "15.00"
    assert row["状态"] == "部分到货"


def test_overdue_partial_receipt_is_distinguished_from_never_received(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt(**{"合格数量": "2", "破损数量": "0"}))
    future_today = date.today() + timedelta(days=5)
    assert store.report_rows(today=future_today)[0]["状态"] == "逾期部分到货"
    assert store.summary(today=future_today)["逾期未齐明细"] == 1


def test_overdue_without_receipt_is_marked_separately(tmp_path):
    store = store_with_line(tmp_path)
    future_today = date.today() + timedelta(days=5)
    assert store.report_rows(today=future_today)[0]["状态"] == "逾期未到货"


def test_accepted_quantity_completes_order_even_if_damaged_items_were_also_received(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt(**{"合格数量": "10", "破损数量": "2"}))
    row = store.report_rows()[0]
    assert row["状态"] == "已到齐"
    assert row["剩余待到货"] == "0"
    assert row["破损数量"] == "2"


def test_accepted_overdelivery_is_reported_without_negative_outstanding(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt(**{"合格数量": "12", "破损数量": "0"}))
    row = store.report_rows()[0]
    assert row["超出订购"] == "2"
    assert row["剩余待到货"] == "0"
    assert row["待到货金额"] == "0.00"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"采购单号": "../escape"}, "采购单号"),
        ({"SKU": "../escape"}, "SKU"),
        ({"供应商": ""}, "供应商"),
        ({"商品名称": ""}, "商品名称"),
        ({"订购数量": "0"}, "订购数量"),
        ({"订购数量": "-1"}, "订购数量"),
        ({"采购单价": "NaN"}, "采购单价"),
        ({"预计到货日期": "2026-02-30"}, "预计到货日期"),
    ],
)
def test_invalid_purchase_lines_are_rejected(tmp_path, changes, message):
    store = MODULE.PurchaseOrderStore(tmp_path / "invalid.json")
    with pytest.raises(ValueError, match=message):
        store.add_line(line(**changes))
    assert store.lines == []


def test_expected_delivery_cannot_precede_order_date(tmp_path):
    today = date.today()
    store = MODULE.PurchaseOrderStore(tmp_path / "dates.json")
    with pytest.raises(ValueError, match="不能早于下单日期"):
        store.add_line(line(**{
            "下单日期": (today - timedelta(days=2)).isoformat(),
            "预计到货日期": (today - timedelta(days=3)).isoformat(),
        }))


def test_future_order_date_is_rejected_but_future_expected_date_is_allowed(tmp_path):
    today = date.today()
    store = MODULE.PurchaseOrderStore(tmp_path / "future.json")
    with pytest.raises(ValueError, match="下单日期不能晚于今天"):
        store.add_line(line(**{"下单日期": (today + timedelta(days=1)).isoformat()}))
    store.add_line(line(**{"预计到货日期": (today + timedelta(days=60)).isoformat()}))


def test_same_purchase_order_header_must_be_consistent(tmp_path):
    store = store_with_line(tmp_path)
    with pytest.raises(ValueError, match="同一采购单号"):
        store.add_line(line(**{"明细编号": "PO-LINE-002", "供应商": "另一供应商"}))
    assert len(store.lines) == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"明细编号": "UNKNOWN"}, "不存在的采购明细"),
        ({"合格数量": "-1"}, "合格数量"),
        ({"合格数量": "0", "破损数量": "0", "拒收数量": "0"}, "之和必须大于 0"),
        ({"到货日期": (date.today() + timedelta(days=1)).isoformat()}, "到货日期不能晚于今天"),
    ],
)
def test_invalid_receipts_are_rejected_without_mutating_store(tmp_path, changes, message):
    store = store_with_line(tmp_path)
    with pytest.raises(ValueError, match=message):
        store.record_receipt(receipt(**changes))
    assert store.receipts == []


def test_receipt_date_cannot_precede_purchase_order_date(tmp_path):
    store = store_with_line(tmp_path, **{"下单日期": (date.today() - timedelta(days=5)).isoformat()})
    with pytest.raises(ValueError, match="到货日期不能早于下单日期"):
        store.record_receipt(receipt(**{"到货日期": (date.today() - timedelta(days=6)).isoformat()}))


def test_duplicate_receipt_id_is_rejected(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt())
    with pytest.raises(ValueError, match="已存在"):
        store.record_receipt(receipt(**{"合格数量": "1"}))
    assert len(store.receipts) == 1


def test_search_and_supplier_summary_are_deterministic(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt())
    assert [row["SKU"] for row in store.search_lines("sku-001")] == ["SKU-001"]
    summary = store.supplier_summary_rows()[0]
    assert summary["供应商"] == "供应商甲"
    assert summary["采购单数"] == 1
    assert summary["待到货数量"] == "7"
    assert summary["待到货金额"] == "35.00"


def test_line_and_receipt_csv_roundtrip_and_formula_protection(tmp_path):
    store = store_with_line(tmp_path, **{"备注": "=HYPERLINK(\"https://example.invalid\",\"open\")"})
    store.record_receipt(receipt())
    line_csv = tmp_path / "lines.csv"
    receipt_csv = tmp_path / "receipts.csv"
    store.export_lines_csv(line_csv)
    store.export_receipts_csv(receipt_csv)
    assert "'=HYPERLINK" in line_csv.read_text(encoding="utf-8-sig")
    imported = MODULE.PurchaseOrderStore(tmp_path / "imported.json")
    assert imported.import_lines_csv(line_csv) == 1
    assert imported.import_receipts_csv(receipt_csv) == 1
    assert imported.lines[0]["备注"] == "=HYPERLINK(\"https://example.invalid\",\"open\")"
    assert imported.receipts == store.receipts


def test_gb18030_csv_import_is_supported(tmp_path):
    store = MODULE.PurchaseOrderStore(tmp_path / "gb.json")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=MODULE.LINE_FIELDS)
    writer.writeheader()
    writer.writerow(line())
    path = tmp_path / "gb18030.csv"
    path.write_bytes(buffer.getvalue().encode("gb18030"))
    assert store.import_lines_csv(path) == 1
    assert store.lines[0]["供应商"] == "供应商甲"


def test_duplicate_line_import_is_all_or_nothing(tmp_path):
    store = store_with_line(tmp_path)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=MODULE.LINE_FIELDS)
    writer.writeheader()
    writer.writerow(line(**{"明细编号": "PO-LINE-002", "采购单号": "PO-2026-002"}))
    writer.writerow(line(**{"明细编号": "PO-LINE-001"}))
    path = tmp_path / "duplicate.csv"
    path.write_text(buffer.getvalue(), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="重复编号"):
        store.import_lines_csv(path)
    assert [row["明细编号"] for row in store.lines] == ["PO-LINE-001"]


def test_receipt_import_rejects_unknown_line_without_partial_commit(tmp_path):
    store = store_with_line(tmp_path)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=MODULE.RECEIPT_FIELDS)
    writer.writeheader()
    writer.writerow(receipt())
    writer.writerow(receipt(**{"到货记录编号": "PO-RCV-002", "明细编号": "MISSING"}))
    path = tmp_path / "bad-receipts.csv"
    path.write_text(buffer.getvalue(), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="不存在的采购明细"):
        store.import_receipts_csv(path)
    assert store.receipts == []


def test_backup_restore_preserves_receipts_and_returns_sha256(tmp_path):
    store = store_with_line(tmp_path)
    store.record_receipt(receipt())
    backup = tmp_path / "backup.json"
    digest = store.backup(backup)
    assert digest == hashlib.sha256(backup.read_bytes()).hexdigest()
    restored = MODULE.PurchaseOrderStore(tmp_path / "restored.json")
    assert restored.restore(backup) == (1, 1)
    assert restored.lines == store.lines
    assert restored.receipts == store.receipts


def test_tampered_backup_is_rejected_without_replacing_current_data(tmp_path):
    store = store_with_line(tmp_path)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["采购明细"][0]["商品名称"] = "被篡改"
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(bad)
    assert store.lines[0]["商品名称"] == "测试商品"


def test_report_and_supplier_exports_use_spreadsheet_safe_cells(tmp_path):
    store = store_with_line(tmp_path, **{"供应商": "=CMD()", "备注": "@SUM(A1)"})
    report = tmp_path / "report.csv"
    summary = tmp_path / "summary.csv"
    store.export_report_csv(report)
    store.export_supplier_summary_csv(summary)
    assert "'=CMD()" in report.read_text(encoding="utf-8-sig")
    assert "'=CMD()" in summary.read_text(encoding="utf-8-sig")


def test_self_test_runs_without_external_services():
    MODULE.self_test()
