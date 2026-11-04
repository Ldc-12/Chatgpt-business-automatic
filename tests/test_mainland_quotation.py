import csv
import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from pypdf import PdfReader

path = Path(__file__).resolve().parents[1] / "apps" / "报价单生成器.py"
spec = importlib.util.spec_from_file_location("quotation_generator", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def quote(number="BJ-20261104-001", customer="测试客户", items=None):
    return {
        "报价单号": number, "客户名称": customer, "联系人": "张先生",
        "联系电话": "13800000000", "报价日期": "2026-11-04",
        "有效期至": "2026-11-30", "税率(%)": "13", "备注": "报价测试",
        "明细": items or [
            {"项目名称": "安装服务", "规格型号": "标准", "单位": "项", "数量": "2", "单价": "100", "项目备注": ""},
            {"项目名称": "材料", "规格型号": "A 型", "单位": "套", "数量": "1", "单价": "50", "项目备注": ""},
        ],
    }


def test_calculate_totals_tax_and_rounding():
    totals = module.calculate_totals(quote())
    assert totals == {"subtotal": Decimal("250.00"), "tax": Decimal("32.50"), "total": Decimal("282.50")}


def test_validation_rejects_invalid_quantity_tax_dates_and_empty_items():
    cases = [
        ({"明细": [{"项目名称": "服务", "单位": "项", "数量": "0", "单价": "1"}]}, "数量"),
        ({"税率(%)": "101"}, "税率"),
        ({"报价日期": "2026/11/04"}, "报价日期"),
        ({"有效期至": "2026-10-01"}, "有效期"),
        ({"明细": []}, "明细"),
    ]
    for changes, expected in cases:
        sample = quote()
        sample.update(changes)
        try:
            module.normalize_quote(sample)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"invalid quote accepted: {changes}")


def test_store_persists_updates_and_deletes_atomically(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    store.add(quote())
    loaded = module.QuoteStore(tmp_path / "quotes.json")
    assert len(loaded.quotes) == 1
    changed = quote(customer="新客户")
    loaded.update("BJ-20261104-001", changed)
    assert module.QuoteStore(tmp_path / "quotes.json").quotes[0]["客户名称"] == "新客户"
    loaded.delete("BJ-20261104-001")
    assert module.QuoteStore(tmp_path / "quotes.json").quotes == []


def test_duplicate_quote_number_rejected(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    store.add(quote())
    try:
        store.add(quote())
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate quote number accepted")


def test_csv_roundtrip_groups_multiple_items_into_one_quote(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    store.add(quote())
    exported = tmp_path / "quotes.csv"
    store.export_csv(exported)
    imported = module.QuoteStore(tmp_path / "imported.json")
    assert imported.import_csv(exported) == 1
    assert imported.quotes == store.quotes
    assert len(imported.quotes[0]["明细"]) == 2


def test_csv_import_is_atomic_on_existing_quote_number(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    store.add(quote())
    source = tmp_path / "duplicate.csv"
    store.export_csv(source)
    before = list(store.quotes)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate import accepted")
    assert store.quotes == before


def test_csv_invalid_row_rejects_whole_batch(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    source = tmp_path / "invalid.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.CSV_FIELDS)
        writer.writeheader()
        good = {field: "" for field in module.CSV_FIELDS}
        good.update(quote("BJ-20261104-002"))
        good.update(quote()["明细"][0])
        writer.writerow(good)
        bad = dict(good)
        bad["报价单号"] = "BJ-20261104-003"
        bad["数量"] = "0"
        writer.writerow(bad)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "第 3 行" in str(exc)
    else:
        raise AssertionError("invalid CSV row accepted")
    assert store.quotes == []


def test_backup_restore_roundtrip_and_invalid_backup_preserves_data(tmp_path):
    store = module.QuoteStore(tmp_path / "quotes.json")
    store.add(quote())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(quote("BJ-20261104-002"))
    store.restore(backup)
    assert len(module.QuoteStore(tmp_path / "quotes.json").quotes) == 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "wrong", "version": 99, "quotes": []}), encoding="utf-8")
    try:
        store.restore(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid backup accepted")
    assert len(store.quotes) == 1


def test_next_quote_number_increments_for_today():
    today = date(2026, 11, 4)
    existing = [{"报价单号": "BJ-20261104-001"}, {"报价单号": "BJ-20261104-003"}]
    assert module.next_quote_number(existing, today) == "BJ-20261104-004"


def test_pdf_export_creates_readable_pdf_with_pages(tmp_path):
    output = tmp_path / "quotation.pdf"
    module.export_quote_pdf(quote(), output)
    assert output.read_bytes().startswith(b"%PDF-")
    reader = PdfReader(str(output))
    assert len(reader.pages) == 1
    assert reader.pages[0].extract_text()
