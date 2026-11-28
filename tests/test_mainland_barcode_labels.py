import csv
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from src import barcode_labels as module


def item(sku="SKU-001", name="测试商品", **changes):
    row = {
        "SKU": sku,
        "商品名称": name,
        "规格": "500g",
        "价格": "12.5",
        "条码": sku,
        "打印数量": "1",
    }
    row.update(changes)
    return row


def test_normalize_validates_sku_barcode_price_and_quantity():
    normalized = module.normalize_item(item())
    assert normalized["价格"] == "12.50"
    assert normalized["打印数量"] == "1"
    invalid = [
        (item(sku="-BAD"), "SKU"),
        (item(name=""), "商品名称"),
        (item(条码="=1+1"), "条码"),
        (item(价格="-1"), "价格"),
        (item(打印数量="1.5"), "打印数量"),
        (item(打印数量="10000"), "打印数量"),
    ]
    for row, expected in invalid:
        with pytest.raises(ValueError, match=expected):
            module.normalize_item(row)


def test_store_persists_and_rejects_duplicate_sku_or_barcode(tmp_path):
    path = tmp_path / "barcode-labels.json"
    store = module.BarcodeLabelStore(path)
    store.add_item(item())
    store.add_item(item("SKU-002", "另一商品", 条码="CODE-002"))
    loaded = module.BarcodeLabelStore(path)
    assert len(loaded.items) == 2
    assert loaded.search_items("另一商品")[0]["SKU"] == "SKU-002"
    with pytest.raises(ValueError, match="SKU 已存在"):
        loaded.add_item(item("sku-001", "重复 SKU", 条码="CODE-003"))
    with pytest.raises(ValueError, match="条码重复"):
        loaded.add_item(item("SKU-003", "重复条码", 条码="CODE-002"))


def test_csv_roundtrip_supports_utf8_and_gb18030_and_formula_safe_export(tmp_path):
    store = module.BarcodeLabelStore(tmp_path / "items.json")
    store.add_item(item(name="普通商品"))
    csv_path = tmp_path / "items.csv"
    store.export_csv(csv_path)
    imported = module.BarcodeLabelStore(tmp_path / "imported.json")
    assert imported.import_csv(csv_path) == 1
    assert imported.items == store.items

    formula_store = module.BarcodeLabelStore(tmp_path / "formula.json")
    formula_store.add_item(item("SKU-002", "=HYPERLINK(\"https://example.invalid\")"))
    formula_path = tmp_path / "formula.csv"
    formula_store.export_csv(formula_path)
    with formula_path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["商品名称"].startswith("'=")

    gb_path = tmp_path / "gb.csv"
    with gb_path.open("w", encoding="gb18030", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.LINE_FIELDS)
        writer.writeheader()
        writer.writerow(item("SKU-003", "广东商品"))
    gb_import = module.BarcodeLabelStore(tmp_path / "gb.json")
    assert gb_import.import_csv(gb_path) == 1
    assert gb_import.items[0]["商品名称"] == "广东商品"


def test_csv_import_is_atomic_on_invalid_row_or_existing_sku(tmp_path):
    store = module.BarcodeLabelStore(tmp_path / "items.json")
    store.add_item(item())
    before = list(store.items)

    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.LINE_FIELDS)
        writer.writeheader()
        writer.writerow(item("SKU-002", "新商品"))
        writer.writerow(item("SKU-001", "已存在"))
    with pytest.raises(ValueError, match="未导入任何数据"):
        store.import_csv(duplicate)
    assert store.items == before

    invalid = tmp_path / "invalid.csv"
    with invalid.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.LINE_FIELDS)
        writer.writeheader()
        writer.writerow(item("SKU-003", "有效商品"))
        writer.writerow(item("SKU-004", "", 价格="not-a-price"))
    with pytest.raises(ValueError, match="商品名称"):
        store.import_csv(invalid)
    assert store.items == before


def test_backup_restore_roundtrip_and_tampering_preserves_existing_data(tmp_path):
    store = module.BarcodeLabelStore(tmp_path / "items.json")
    store.add_item(item())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add_item(item("SKU-002", "新增商品"))
    assert len(store.items) == 2

    restored = module.BarcodeLabelStore(tmp_path / "restored.json")
    assert restored.restore(backup) == 1
    assert restored.items[0]["SKU"] == "SKU-001"

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["价格"] = "999.00"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(restored.items)
    with pytest.raises(ValueError, match="SHA256"):
        restored.restore(tampered)
    assert restored.items == before
    assert module.BarcodeLabelStore(restored.path).items == before


def test_pdf_export_creates_two_pages_for_twenty_five_labels(tmp_path):
    rows = [item("SKU-001", "测试商品", 打印数量="25", 价格="12.50")]
    output = tmp_path / "labels.pdf"
    assert module.export_labels_pdf(rows, output) == 25
    assert output.read_bytes().startswith(b"%PDF-")
    reader = PdfReader(str(output))
    assert len(reader.pages) == 2
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "SKU-001" in extracted
    assert "测试商品" in extracted


def test_pdf_export_rejects_empty_catalog_and_excessive_batch(tmp_path):
    with pytest.raises(ValueError, match="没有可打印"):
        module.export_labels_pdf([], tmp_path / "empty.pdf")
    rows = [
        item("SKU-001", "商品一", 打印数量="9999"),
        item("SKU-002", "商品二", 打印数量="9999"),
        item("SKU-003", "商品三", 打印数量="3"),
    ]
    with pytest.raises(ValueError, match="最多生成"):
        module.export_labels_pdf(rows, tmp_path / "too-many.pdf")


def test_self_test_runs_store_csv_backup_and_pdf(tmp_path):
    assert module.self_test() is True
