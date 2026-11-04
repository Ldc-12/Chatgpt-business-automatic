import csv
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "小店库存盘点助手.py"
spec = importlib.util.spec_from_file_location("inventory_assistant", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(code="A001", name="测试商品"):
    return {"商品编码": code, "商品名称": name, "分类": "日用品", "单位": "件",
            "库存数量": "8", "预警下限": "2", "进货单价": "3.5", "备注": ""}


def test_add_save_reload_and_update(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    loaded = module.InventoryStore(tmp_path / "inventory.json")
    assert loaded.rows[0]["商品编码"] == "A001"
    loaded.update("A001", row(name="新名称"))
    assert module.InventoryStore(tmp_path / "inventory.json").rows[0]["商品名称"] == "新名称"


def test_csv_roundtrip_and_duplicate_is_atomic(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    source = tmp_path / "items.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS); writer.writeheader(); writer.writerow(row())
    assert store.import_csv(source) == 1
    before = list(store.rows)
    with source.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS); writer.writeheader(); writer.writerow(row())
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate import should fail")
    assert store.rows == before


def test_invalid_csv_does_not_replace_existing_data(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json"); store.add(row())
    bad = tmp_path / "bad.csv"
    bad.write_text("商品编码,商品名称\nA002,缺少字段", encoding="utf-8-sig")
    try: store.import_csv(bad)
    except ValueError: pass
    else: raise AssertionError("invalid CSV accepted")
    assert len(store.rows) == 1


def test_backup_restore_roundtrip(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json"); store.add(row())
    backup = tmp_path / "backup.json"; store.backup(backup)
    store.add(row("A002", "第二件"))
    store.restore(backup)
    assert len(module.InventoryStore(tmp_path / "inventory.json").rows) == 1


def test_restore_rejects_unknown_format_without_overwriting(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json"); store.add(row())
    bad = tmp_path / "bad.json"; bad.write_text('{"format":"unknown","version":9,"items":[]}', encoding="utf-8")
    try: store.restore(bad)
    except ValueError: pass
    else: raise AssertionError("unknown backup accepted")
    assert len(store.rows) == 1


def test_duplicate_product_code_rejected(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json"); store.add(row())
    try: store.add(row())
    except ValueError as exc: assert "已存在" in str(exc)
    else: raise AssertionError("duplicate code accepted")
