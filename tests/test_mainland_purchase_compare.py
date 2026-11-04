import csv
import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "供应商采购比价助手.py"
spec = importlib.util.spec_from_file_location("purchase_compare", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def quote(qid="Q001", supplier="甲供应商", price="10", tax="13", qty="100", freight="20", valid="2099-12-31"):
    return {
        "报价编号": qid, "物料编码": "M001", "物料名称": "包装纸箱",
        "供应商": supplier, "规格": "五层 40×30", "单位": "个",
        "未税单价": price, "税率(%)": tax, "采购数量": qty, "运费总额": freight,
        "报价日期": "2026-11-01", "有效期至": valid, "备注": "",
    }


def test_landed_unit_cost_includes_tax_and_allocated_freight():
    normalized = module.normalize_quote(quote())
    assert module.landed_unit_cost(normalized) == Decimal("11.70")


def test_best_quote_compares_landed_cost_not_sticker_price():
    a = module.normalize_quote(quote("Q001", "甲供应商", price="9", tax="13", qty="100", freight="400"))
    b = module.normalize_quote(quote("Q002", "乙供应商", price="10", tax="13", qty="100", freight="20"))
    best = module.best_quote_by_material([a, b], date(2026, 11, 4))
    assert best["M001"]["报价编号"] == "Q002"


def test_expired_quotes_are_not_recommended():
    expired = module.normalize_quote(quote("Q001", valid="2026-11-02"))
    current = module.normalize_quote(quote("Q002", supplier="乙供应商", price="12", valid="2026-12-01"))
    best = module.best_quote_by_material([expired, current], date(2026, 11, 4))
    assert best["M001"]["报价编号"] == "Q002"
    assert module.quote_status(expired, date(2026, 11, 4)) == "已过期"


def test_all_expired_material_has_no_recommendation():
    expired = module.normalize_quote(quote(valid="2026-11-02"))
    assert module.best_quote_by_material([expired], date(2026, 11, 4)) == {}


def test_store_persists_quotes_and_supports_update_delete(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    loaded = module.PurchaseStore(tmp_path / "quotes.json")
    assert loaded.quotes[0]["报价编号"] == "Q001"
    changed = quote("Q001", supplier="新供应商", price="8")
    loaded.update("Q001", changed)
    assert module.PurchaseStore(tmp_path / "quotes.json").quotes[0]["供应商"] == "新供应商"
    loaded.delete("Q001")
    assert module.PurchaseStore(tmp_path / "quotes.json").quotes == []


def test_csv_export_import_roundtrip(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    exported = tmp_path / "export.csv"
    store.export_csv(exported)
    imported = module.PurchaseStore(tmp_path / "other.json")
    assert imported.import_csv(exported) == 1
    assert imported.quotes == store.quotes


def test_csv_duplicate_import_is_atomic(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(quote())
    before = list(store.quotes)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate import should fail")
    assert store.quotes == before


def test_invalid_csv_row_is_rejected_without_partial_import(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    source = tmp_path / "invalid.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(quote("Q002"))
        bad = quote("Q003")
        bad["采购数量"] = "0"
        writer.writerow(bad)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "第 3 行" in str(exc)
    else:
        raise AssertionError("invalid row should reject the complete import")
    assert [q["报价编号"] for q in store.quotes] == ["Q001"]


def test_backup_restore_roundtrip_and_invalid_backup_preserves_data(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(quote("Q002", supplier="乙供应商"))
    store.restore(backup)
    assert len(module.PurchaseStore(tmp_path / "quotes.json").quotes) == 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "unknown", "version": 9, "quotes": []}), encoding="utf-8")
    try:
        store.restore(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown backup accepted")
    assert len(store.quotes) == 1


def test_validation_rejects_bad_tax_quantity_dates_and_duplicate_ids(tmp_path):
    for changes, expected in [
        ({"税率(%)": "101"}, "税率"),
        ({"采购数量": "0"}, "采购数量"),
        ({"报价日期": "2026/11/01"}, "报价日期"),
        ({"有效期至": "2026-10-31"}, "有效期"),
    ]:
        bad = quote()
        bad.update(changes)
        try:
            module.normalize_quote(bad)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"invalid quote accepted: {changes}")
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    try:
        store.add(quote())
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate quote ID accepted")


def test_malformed_backup_shapes_are_rejected_without_data_loss(tmp_path):
    store = module.PurchaseStore(tmp_path / "quotes.json")
    store.add(quote())
    for payload in [[], {"format": module.BACKUP_FORMAT, "version": 1, "quotes": [None]}]:
        bad = tmp_path / "malformed.json"
        bad.write_text(json.dumps(payload), encoding="utf-8")
        try:
            store.restore(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed backup accepted")
        assert len(module.PurchaseStore(tmp_path / "quotes.json").quotes) == 1
