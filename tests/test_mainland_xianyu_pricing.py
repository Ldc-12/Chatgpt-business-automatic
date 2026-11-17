import csv
import json
from datetime import date

import pytest

from src import xianyu_pricing as module


def sample(**overrides):
    row = {
        "商品编号": "XY-P-001", "商品名称": "二手测试手机", "品类": "手机数码",
        "购入日期": "2025-11-17", "原价(元)": "1000", "购入成本(元)": "400",
        "成色": "9成新", "配件/瑕疵扣减(元)": "20", "整备费用(元)": "20",
        "包装运费(元)": "10", "售后预留(元)": "5", "平台费率(%)": "1",
        "平台固定费用(元)": "0.5", "目标利润(元)": "100", "议价空间(%)": "8",
        "同类成交中位价(元)": "600", "上架状态": "待上架", "备注": "",
    }
    row.update(overrides)
    return row


def test_age_months_and_category_depreciation_bands():
    assert module.age_in_months("2025-11-17", as_of=date(2026, 11, 17)) == 12
    assert module.age_in_months("2026-05-18", as_of=date(2026, 11, 17)) == 5
    assert module.depreciation_factor("手机数码", 12) == module.Decimal("0.78")
    assert module.depreciation_factor("家用电器", 12) == module.Decimal("0.88")
    assert module.depreciation_factor("手机数码", 60) == module.Decimal("0.28")


def test_price_model_blends_manual_comparables_and_versioned_rules():
    result = module.calculate_price(sample(), as_of=date(2026, 11, 17))
    assert result["规则版本"] == "XY-USED-PRICE-2026.11"
    assert result["使用月数"] == 12
    assert result["折旧系数"] == "0.78"
    assert result["成色系数"] == "0.86"
    assert result["折旧模型估值(元)"] == "650.80"
    assert result["估值基准(元)"] == "620.32"
    assert "40%" in result["估值口径"] and "60%" in result["估值口径"]


def test_price_floor_covers_costs_fees_and_target_profit():
    result = module.calculate_price(sample(), as_of=date(2026, 11, 17))
    assert result["最低接受价(元)"] == "540.91"
    assert result["最低价预计净利润(元)"] == "100.00"
    assert result["建议标价(元)"] == "670.00"
    assert result["标价预计净利润(元)"] == "227.80"


def test_extreme_fee_rate_cannot_create_unbounded_price():
    row = sample(**{
        "购入成本(元)": "1000000000",
        "平台费率(%)": "99.99",
        "目标利润(元)": "0",
    })
    with pytest.raises(ValueError, match="超出支持范围"):
        module.calculate_price(row, as_of=date(2026, 11, 17))


def test_missing_comparables_uses_only_the_rule_model():
    result = module.calculate_price(sample(**{"同类成交中位价(元)": ""}), as_of=date(2026, 11, 17))
    assert result["估值基准(元)"] == "650.80"
    assert "未录入同类成交价" in result["估值口径"]


def test_negotiation_buffer_changes_listing_price_not_minimum_price():
    base = module.calculate_price(sample(**{"议价空间(%)": "0"}), as_of=date(2026, 11, 17))
    buffered = module.calculate_price(sample(**{"议价空间(%)": "10"}), as_of=date(2026, 11, 17))
    assert base["最低接受价(元)"] == buffered["最低接受价(元)"]
    assert buffered["建议标价(元)"] > base["建议标价(元)"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"品类": "不存在的品类"}, "内置列表"),
        ({"成色": "五成新"}, "内置列表"),
        ({"购入日期": "2026-13-01"}, "YYYY-MM-DD"),
        ({"原价(元)": "0"}, "必须大于 0"),
        ({"配件/瑕疵扣减(元)": "1001"}, "不能超过原价"),
        ({"平台费率(%)": "100"}, "小于 100%"),
        ({"议价空间(%)": "51"}, "0–50%"),
        ({"目标利润(元)": "-1"}, "不能为负数"),
        ({"购入成本(元)": "1e1000"}, "超出支持范围"),
    ],
)
def test_invalid_pricing_inputs_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_item_row(sample(**overrides))


def test_store_persists_updates_deletes_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "items.json"
    store = module.PriceStore(path)
    store.add(sample())
    loaded = module.PriceStore(path)
    assert loaded.rows == store.rows
    changed = dict(loaded.rows[0], **{"购入成本(元)": "350"})
    loaded.update("XY-P-001", changed)
    assert module.calculate_price(loaded.rows[0], as_of=date(2026, 11, 17))["最低接受价(元)"] == "490.41"
    with pytest.raises(ValueError, match="已存在"):
        loaded.add(sample(**{"商品名称": "重复编号"}))
    loaded.delete("XY-P-001")
    assert loaded.rows == []


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    store = module.PriceStore(tmp_path / "items.json")
    store.add(sample(**{"商品名称": "=HYPERLINK(\"https://bad.example\",\"click\")"}))
    path = tmp_path / "items.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.PriceStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["商品名称"].startswith("'=")


def test_csv_import_rejects_invalid_rows_atomically(tmp_path):
    store = module.PriceStore(tmp_path / "items.json")
    store.add(sample())
    before = list(store.rows)
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"平台费率(%)": "100"}))
    with pytest.raises(ValueError, match="小于 100%"):
        store.import_csv(path)
    assert store.rows == before


def test_csv_import_rejects_duplicate_ids_and_oversized_files(tmp_path):
    store = module.PriceStore(tmp_path / "items.json")
    store.add(sample())
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在商品编号"):
        store.import_csv(duplicate)
    oversized = tmp_path / "oversized.csv"
    oversized.write_bytes(b"x" * (100 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="100 MiB"):
        store.import_csv(oversized)
    assert len(store.rows) == 1


def test_backup_restore_checks_sha256_before_replacing_data(tmp_path):
    source = module.PriceStore(tmp_path / "source.json")
    source.add(sample())
    backup = tmp_path / "backup.json"
    source.backup(backup)
    target = module.PriceStore(tmp_path / "target.json")
    target.add(sample(**{"商品编号": "XY-OLD", "商品名称": "旧商品"}))
    target.restore(backup)
    assert target.rows == source.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["购入成本(元)"] = "999"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(target.rows)
    with pytest.raises(ValueError, match="SHA256"):
        target.restore(tampered)
    assert target.rows == before


def test_failed_atomic_replace_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "items.json"
    store = module.PriceStore(path)
    store.add(sample())
    original = path.read_bytes()
    monkeypatch.setattr(module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        store.add(sample(**{"商品编号": "XY-P-002", "商品名称": "第二件商品"}))
    assert path.read_bytes() == original
    assert len(store.rows) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_category_summary_and_listing_text_do_not_expose_private_floor():
    row = sample()
    summary = module.category_summary([row])
    assert summary["手机数码"]["商品数"] == 1
    text = module.generate_listing_text(row, as_of=date(2026, 11, 17))
    assert "XY-P-001" not in text
    assert "参考标价：¥670.00" in text
    assert "最低接受价" not in text


def test_self_test_runs_without_gui():
    module.self_test()

def test_analysis_csv_exports_calculated_prices_and_protects_formula_text(tmp_path):
    store = module.PriceStore(tmp_path / "items.json")
    store.add(sample(**{
        "商品名称": "=HYPERLINK(\"https://bad.example\",\"click\")",
        "备注": "@SUM(1,2)",
    }))
    path = tmp_path / "analysis.csv"
    store.export_analysis_csv(path, as_of=date(2026, 11, 17))

    raw = path.read_bytes()
    assert raw.startswith(b"\\xef\\xbb\\xbf")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)
    assert row["建议标价(元)"] == "670.00"
    assert row["最低接受价(元)"] == "540.91"
    assert row["标价预计净利润(元)"] == "227.80"
    assert row["规则版本"] == "XY-USED-PRICE-2026.11"
    assert row["商品名称"].startswith("'=")
    assert row["备注"].startswith("'@")


def test_analysis_csv_empty_store_still_has_stable_headers(tmp_path):
    store = module.PriceStore(tmp_path / "items.json")
    path = tmp_path / "empty-analysis.csv"
    store.export_analysis_csv(path, as_of=date(2026, 11, 17))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert "最低接受价(元)" in reader.fieldnames
        assert "标价预计净利润(元)" in reader.fieldnames
        assert list(reader) == []

