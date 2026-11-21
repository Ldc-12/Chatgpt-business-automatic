from datetime import date, timedelta
import csv
import json

import pytest

from src import store_replenishment as MODULE


def item(**changes):
    row = {
        "SKU": "SKU-001", "商品名称": "测试商品", "当前库存": "12", "已预留": "2",
        "采购提前期天数": "3", "安全库存天数": "2", "目标覆盖天数": "5",
        "整箱数量": "6", "最低起订量": "15", "采购单价": "2.50",
        "供应商": "供应商甲", "备注": "",
    }
    row.update(changes)
    return row


def store_with_item(tmp_path, **changes):
    store = MODULE.ReplenishmentStore(tmp_path / "replenishment.json")
    store.add_item(item(**changes))
    return store


def add_sales(store, *, days=10, quantity="2"):
    current = date.today()
    for offset in range(days):
        store.record_sale({
            "销售编号": f"SALE-{offset:03d}", "SKU": "SKU-001",
            "日期": (current - timedelta(days=offset)).isoformat(), "销量": quantity,
        })


def test_item_persists_and_reloads_from_local_json(tmp_path):
    store = store_with_item(tmp_path)
    loaded = MODULE.ReplenishmentStore(store.path)
    assert loaded.items == store.items
    assert loaded.sales == []


def test_duplicate_sku_is_rejected_case_insensitively(tmp_path):
    store = store_with_item(tmp_path)
    with pytest.raises(ValueError, match="SKU 已存在"):
        store.add_item(item(SKU="sku-001"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"SKU": "../escape"}, "SKU"),
        ({"商品名称": ""}, "商品名称"),
        ({"当前库存": "-1"}, "当前库存"),
        ({"整箱数量": "0"}, "整箱数量"),
        ({"采购提前期天数": "366"}, "采购提前期天数"),
        ({"目标覆盖天数": "0"}, "目标覆盖天数"),
        ({"采购单价": "NaN"}, "采购单价"),
    ],
)
def test_invalid_item_fields_are_rejected(tmp_path, changes, message):
    store = MODULE.ReplenishmentStore(tmp_path / "bad.json")
    with pytest.raises(ValueError, match=message):
        store.add_item(item(**changes))
    assert store.items == []


def test_replenishment_formula_applies_lead_safety_pack_and_moq(tmp_path):
    store = store_with_item(tmp_path)
    add_sales(store, days=10, quantity="2")
    row = store.plan(10)[0]
    assert row["日均销量"] == "2"
    assert row["可用库存"] == "10"
    assert row["补货触发库存"] == "10"
    assert row["目标库存"] == "20"
    assert row["建议采购量"] == "18"
    assert row["预计采购金额"] == "45.00"
    assert row["建议状态"] == "建议补货"


def test_average_uses_full_lookback_window_including_zero_sales_days(tmp_path):
    store = store_with_item(tmp_path)
    store.record_sale({"销售编号": "S1", "SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "10"})
    row = store.plan(10)[0]
    assert row["日均销量"] == "1"
    assert row["建议状态"] == "库存充足"


def test_sales_outside_lookback_window_are_ignored(tmp_path):
    store = store_with_item(tmp_path)
    old_day = (date.today() - timedelta(days=60)).isoformat()
    store.record_sale({"销售编号": "OLD", "SKU": "SKU-001", "日期": old_day, "销量": "100"})
    assert store.plan(30)[0]["建议状态"] == "缺少销量数据"


def test_no_sales_history_is_not_mistaken_for_zero_demand(tmp_path):
    store = store_with_item(tmp_path)
    row = store.plan(30)[0]
    assert row["建议状态"] == "缺少销量数据"
    assert row["建议采购量"] == "0"


def test_explicit_zero_sales_record_means_no_demand(tmp_path):
    store = store_with_item(tmp_path)
    store.record_sale({"销售编号": "ZERO", "SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "0"})
    assert store.plan(30)[0]["建议状态"] == "无销量需求"


def test_reserved_stock_reduces_available_inventory(tmp_path):
    store = store_with_item(tmp_path, **{"当前库存": "20", "已预留": "18", "整箱数量": "1", "最低起订量": "0"})
    add_sales(store, days=10, quantity="1")
    row = store.plan(10)[0]
    assert row["可用库存"] == "2"
    assert row["建议采购量"] == "8"


def test_future_sales_date_is_rejected(tmp_path):
    store = store_with_item(tmp_path)
    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="不能晚于今天"):
        store.record_sale({"SKU": "SKU-001", "日期": future, "销量": "1"})
    assert store.sales == []


def test_unknown_sku_and_duplicate_sale_id_are_rejected(tmp_path):
    store = store_with_item(tmp_path)
    with pytest.raises(ValueError, match="不存在的 SKU"):
        store.record_sale({"SKU": "MISSING", "日期": date.today().isoformat(), "销量": "1"})
    store.record_sale({"销售编号": "DUP", "SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "1"})
    with pytest.raises(ValueError, match="销售编号重复"):
        store.record_sale({"销售编号": "DUP", "SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "1"})


def test_item_sku_cannot_be_renamed_after_sales_exist(tmp_path):
    store = store_with_item(tmp_path)
    store.record_sale({"SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "1"})
    with pytest.raises(ValueError, match="不能直接修改 SKU"):
        store.update_item("SKU-001", item(SKU="SKU-NEW"))
    assert store.items[0]["SKU"] == "SKU-001"


def test_update_stock_and_supplier_persists(tmp_path):
    store = store_with_item(tmp_path)
    store.update_item("SKU-001", item(**{"当前库存": "30", "已预留": "4", "供应商": "供应商乙"}))
    loaded = MODULE.ReplenishmentStore(store.path)
    assert loaded.items[0]["当前库存"] == "30.000"
    assert loaded.items[0]["供应商"] == "供应商乙"


def test_items_csv_import_is_all_or_nothing_and_rejects_duplicate_sku(tmp_path):
    store = store_with_item(tmp_path)
    path = tmp_path / "items.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.ITEM_FIELDS)
        writer.writeheader()
        writer.writerow(item(SKU="SKU-002"))
        writer.writerow(item(SKU="SKU-001"))
    with pytest.raises(ValueError, match="重复 SKU"):
        store.import_items_csv(path)
    assert len(store.items) == 1
    assert store.items[0]["SKU"] == "SKU-001"


def test_sales_csv_import_is_all_or_nothing(tmp_path):
    store = store_with_item(tmp_path)
    path = tmp_path / "sales.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.SALES_FIELDS)
        writer.writeheader()
        writer.writerow({"销售编号": "S1", "SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "2", "备注": ""})
        writer.writerow({"销售编号": "S2", "SKU": "UNKNOWN", "日期": date.today().isoformat(), "销量": "3", "备注": ""})
    with pytest.raises(ValueError, match="不存在的 SKU"):
        store.import_sales_csv(path)
    assert store.sales == []


def test_csv_header_must_match_export_template(tmp_path):
    store = store_with_item(tmp_path)
    path = tmp_path / "wrong.csv"
    path.write_text("SKU,商品名称\nA,商品\n", encoding="utf-8")
    with pytest.raises(ValueError, match="表头不匹配"):
        store.import_items_csv(path)


def test_exports_are_utf8_bom_and_formula_safe(tmp_path):
    store = store_with_item(tmp_path, **{"商品名称": "=HYPERLINK(\"https://bad\")", "供应商": "@supplier"})
    output = tmp_path / "items.csv"
    store.export_items_csv(output)
    content = output.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in content
    assert "'@supplier" in content
    plan = tmp_path / "plan.csv"
    store.export_plan_csv(plan)
    assert "建议采购量" in plan.read_text(encoding="utf-8-sig")


def test_backup_restore_verifies_sha_and_replaces_current_state(tmp_path):
    store = store_with_item(tmp_path)
    store.record_sale({"SKU": "SKU-001", "日期": date.today().isoformat(), "销量": "2"})
    backup = tmp_path / "backup.json"
    digest = store.backup(backup)
    assert len(digest) == 64
    store.add_item(item(SKU="SKU-002", **{"商品名称": "第二个商品"}))
    assert len(store.items) == 2
    assert store.restore(backup) == (1, 1)
    assert len(MODULE.ReplenishmentStore(store.path).items) == 1


def test_corrupt_backup_does_not_replace_current_data(tmp_path):
    store = store_with_item(tmp_path)
    backup = tmp_path / "bad.json"
    payload = MODULE.ReplenishmentStore._payload(store.items, store.sales)
    payload["商品"][0]["商品名称"] = "被篡改"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(backup)
    assert store.items[0]["商品名称"] == "测试商品"


def test_tampered_local_state_is_rejected_on_reload(tmp_path):
    store = store_with_item(tmp_path)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["商品"][0]["当前库存"] = "999"
    store.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        MODULE.ReplenishmentStore(store.path)


def test_search_and_pagination_are_bounded_and_non_mutating(tmp_path):
    store = store_with_item(tmp_path)
    store.add_item(item(SKU="SKU-002", **{"商品名称": "第二个商品", "供应商": "乙方"}))
    rows = store.search_items("乙方")
    assert [row["SKU"] for row in rows] == ["SKU-002"]
    page, current, pages, total = store.paginate(store.items, 99, 1)
    assert len(page) == 1 and current == 2 and pages == 2 and total == 2
    with pytest.raises(ValueError, match="每页数量"):
        store.paginate(store.items, 1, 0)


def test_summary_counts_replenishment_and_budget(tmp_path):
    store = store_with_item(tmp_path)
    add_sales(store, days=10, quantity="2")
    summary = store.summary(10)
    assert summary["商品 SKU"] == 1
    assert summary["建议补货 SKU"] == 1
    assert summary["预计采购金额"] == "45.00"


def test_self_test_runs_without_gui_or_network():
    MODULE.self_test()
