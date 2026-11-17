import csv
import json
from pathlib import Path

import pytest

from src import xianyu_profit as module


def sample(**overrides):
    row = {
        "记录编号": "XY-001", "订单编号": "XY-ORDER-001", "成交日期": "2026-11-01",
        "商品/SKU": "二手蓝牙耳机", "买家备注": "买家A", "买家实付金额(元)": "100",
        "商品成本(元)": "40", "包装成本(元)": "2", "发货运费(元)": "5",
        "平台费率(%)": "1", "平台固定费用(元)": "0.5", "实际平台费用(元)": "",
        "推广费用(元)": "3", "售后退款(元)": "10", "售后补偿(元)": "2",
        "退货运费(元)": "1", "售后回收金额(元)": "5", "订单状态": "已完成", "备注": "",
    }
    row.update(overrides)
    return row


def test_profit_uses_refund_costs_and_estimated_platform_fee():
    result = module.calculate_order(sample())
    assert result["订单净收入(元)"] == "90.00"
    assert result["平台费用(元)"] == "1.50"
    assert result["平台费用口径"] == "按本单费率估算"
    assert result["成本支出(元)"] == "54.50"
    assert result["售后回收金额(元)"] == "5.00"
    assert result["净利润(元)"] == "40.50"
    assert result["净利率(%)"] == "45.00"


def test_actual_platform_fee_overrides_estimate():
    result = module.calculate_order(sample(**{"实际平台费用(元)": "0.8"}))
    assert result["平台费用(元)"] == "0.80"
    assert result["平台费用口径"] == "实际"
    assert result["净利润(元)"] == "41.20"


def test_break_even_price_rounds_up_and_rejects_full_fee_rate():
    assert module.break_even_price("50", "1", "0.5") == "51.02"
    with pytest.raises(ValueError, match="小于 100%"):
        module.break_even_price("50", "100", "0")


def test_monthly_and_sku_summaries_group_orders():
    rows = [
        sample(),
        sample(**{
            "记录编号": "XY-002", "订单编号": "XY-ORDER-002", "成交日期": "2026-12-02",
            "商品/SKU": "二手蓝牙耳机", "买家实付金额(元)": "80", "商品成本(元)": "30",
            "售后退款(元)": "0", "售后补偿(元)": "0", "退货运费(元)": "0",
            "售后回收金额(元)": "0", "实际平台费用(元)": "0",
        }),
    ]
    monthly = module.monthly_summary(rows)
    assert monthly["2026-11"]["订单数"] == 1
    assert monthly["2026-12"]["净收入(元)"] == "80.00"
    sku = module.sku_summary(rows)
    assert sku["二手蓝牙耳机"]["订单数"] == 2
    assert sku["二手蓝牙耳机"]["净利润(元)"] == "91.70"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"售后退款(元)": "101"}, "不能超过"),
        ({"平台费率(%)": "100"}, "小于 100%"),
        ({"商品成本(元)": "-1"}, "不能为负数"),
        ({"成交日期": "2026-13-01"}, "YYYY-MM-DD"),
        ({"订单状态": "神秘状态"}, "内置列表"),
        ({"买家实付金额(元)": "1e1000"}, "超出支持范围"),
    ],
)
def test_invalid_order_values_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_order_row(sample(**overrides))


def test_store_persists_updates_deletes_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "orders.json"
    store = module.OrderStore(path)
    store.add(sample())
    loaded = module.OrderStore(path)
    assert loaded.rows == store.rows
    changed = dict(loaded.rows[0], **{"商品成本(元)": "35"})
    loaded.update("XY-001", changed)
    assert module.calculate_order(loaded.rows[0])["净利润(元)"] == "45.50"
    with pytest.raises(ValueError, match="已存在"):
        loaded.add(sample(**{"记录编号": "XY-001", "订单编号": "XY-OTHER"}))
    loaded.delete("XY-001")
    assert loaded.rows == []


def test_csv_roundtrip_has_bom_and_formula_safe_text(tmp_path):
    store = module.OrderStore(tmp_path / "orders.json")
    store.add(sample(**{"商品/SKU": "=HYPERLINK(\"https://bad.example\",\"click\")"}))
    csv_path = tmp_path / "orders.csv"
    store.export_csv(csv_path)
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.OrderStore(tmp_path / "imported.json")
    assert imported.import_csv(csv_path) == 1
    assert imported.rows[0]["商品/SKU"].startswith("'=")


def test_csv_import_rejects_bad_rows_and_duplicate_records_atomically(tmp_path):
    store = module.OrderStore(tmp_path / "orders.json")
    store.add(sample())
    before = list(store.rows)
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"售后退款(元)": "200"}))
    with pytest.raises(ValueError, match="不能超过"):
        store.import_csv(bad)
    assert store.rows == before

    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在"):
        store.import_csv(duplicate)
    assert store.rows == before


def test_backup_restore_checks_sha256_before_replacing_data(tmp_path):
    source = module.OrderStore(tmp_path / "source.json")
    source.add(sample())
    backup = tmp_path / "backup.json"
    source.backup(backup)
    target = module.OrderStore(tmp_path / "target.json")
    target.add(sample(**{"记录编号": "XY-OLD", "订单编号": "XY-OLD-ORDER"}))
    target.restore(backup)
    assert target.rows == source.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["orders"][0]["商品成本(元)"] = "999"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(target.rows)
    with pytest.raises(ValueError, match="SHA256"):
        target.restore(tampered)
    assert target.rows == before


def test_failed_atomic_replace_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "orders.json"
    store = module.OrderStore(path)
    store.add(sample())
    original = path.read_bytes()
    monkeypatch.setattr(module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        store.add(sample(**{"记录编号": "XY-002", "订单编号": "XY-ORDER-002"}))
    assert path.read_bytes() == original
    assert len(store.rows) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_self_test_runs_without_gui():
    module.self_test()
