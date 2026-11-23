import csv
import importlib.util
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "小店库存盘点助手.py"
spec = importlib.util.spec_from_file_location("inventory_assistant", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(code="A001", name="测试商品", note=""):
    return {"商品编码": code, "商品名称": name, "分类": "日用品", "单位": "件",
            "库存数量": "8", "预警下限": "2", "进货单价": "3.5", "备注": note}


def write_csv(path, rows, fieldnames=None):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or module.FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def expect_value_error(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


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
    write_csv(source, [row()])
    assert store.import_csv(source) == 1
    before = list(store.rows)
    write_csv(source, [row()])
    expect_value_error(lambda: store.import_csv(source))
    assert store.rows == before


def test_invalid_csv_does_not_replace_existing_data(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    bad = tmp_path / "bad.csv"
    bad.write_text("商品编码,商品名称\nA002,缺少字段", encoding="utf-8-sig")
    expect_value_error(lambda: store.import_csv(bad))
    assert len(store.rows) == 1


def test_backup_restore_roundtrip(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(row("A002", "第二件"))
    store.restore(backup)
    assert len(module.InventoryStore(tmp_path / "inventory.json").rows) == 1


def test_restore_rejects_unknown_format_without_overwriting(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    bad = tmp_path / "bad.json"
    bad.write_text('{"format":"unknown","version":9,"items":[]}', encoding="utf-8")
    expect_value_error(lambda: store.restore(bad))
    assert len(store.rows) == 1


def test_duplicate_product_code_rejected(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    expect_value_error(lambda: store.add(row()))


def test_delete_existing_product_persists_removal(tmp_path):
    data_path = tmp_path / "inventory.json"
    store = module.InventoryStore(data_path)
    store.add(row())

    store.delete("A001")

    assert store.rows == []
    assert module.InventoryStore(data_path).rows == []


def test_delete_missing_or_blank_product_code_does_not_rewrite_data(tmp_path):
    data_path = tmp_path / "inventory.json"
    store = module.InventoryStore(data_path)
    store.add(row())
    original_text = data_path.read_text(encoding="utf-8")
    original_rows = list(store.rows)

    expect_value_error(lambda: store.delete("MISSING"))
    expect_value_error(lambda: store.delete("  "))

    assert store.rows == original_rows
    assert data_path.read_text(encoding="utf-8") == original_text


def test_non_finite_inventory_numbers_are_rejected():
    for value in ("nan", "NaN", "inf", "-inf", "Infinity"):
        try:
            module.number(value, "库存数量")
        except ValueError as exc:
            assert "有限数字" in str(exc)
        else:
            raise AssertionError(f"non-finite value accepted: {value}")


def test_failed_atomic_save_preserves_disk_and_memory(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    original_text = store.path.read_text(encoding="utf-8")
    original_rows = list(store.rows)

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        store.add(row("A002", "第二件"))
    except OSError:
        pass
    else:
        raise AssertionError("failed replace should propagate")
    assert store.rows == original_rows
    assert store.path.read_text(encoding="utf-8") == original_text
    assert list(tmp_path.glob(".inventory.json.*.tmp")) == []


def test_failed_csv_export_preserves_previous_file(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    target = tmp_path / "items.csv"
    target.write_text("previous export", encoding="utf-8")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        store.export_csv(target)
    except OSError:
        pass
    else:
        raise AssertionError("failed CSV replace should propagate")
    assert target.read_text(encoding="utf-8") == "previous export"
    assert list(tmp_path.glob(".items.csv.*.tmp")) == []


def test_csv_export_protects_formulas_and_import_restores_text(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row(name="=HYPERLINK('https://example.invalid')", note="=1+1"))
    exported = tmp_path / "safe.csv"
    store.export_csv(exported)
    raw = exported.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with exported.open(encoding="utf-8-sig", newline="") as handle:
        record = next(csv.DictReader(handle))
    assert record["商品名称"].startswith("'=")
    assert module._spreadsheet_safe("\t=1+1") == "'\t=1+1"
    assert record["备注"].startswith("'=")
    restored = module.InventoryStore(tmp_path / "restored.json")
    assert restored.import_csv(exported) == 1
    assert restored.rows[0]["商品名称"] == store.rows[0]["商品名称"]
    assert restored.rows[0]["备注"] == store.rows[0]["备注"]


def test_csv_rejects_duplicate_or_extra_headers_without_mutation(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    original = list(store.rows)
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text("商品编码,商品编码,商品名称,分类,单位,库存数量,预警下限,进货单价,备注\nA002,A002,商品,日用品,件,1,0,2,备注\n", encoding="utf-8-sig")
    expect_value_error(lambda: store.import_csv(duplicate))
    extra = tmp_path / "extra.csv"
    write_csv(extra, [row()], fieldnames=module.FIELDS + ["额外列"])
    expect_value_error(lambda: store.import_csv(extra))
    assert store.rows == original


def test_csv_file_and_row_limits_are_enforced(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    source = tmp_path / "items.csv"
    write_csv(source, [row()])
    monkeypatch.setattr(module, "MAX_CSV_BYTES", source.stat().st_size - 1)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "25 MiB" in str(exc)
    else:
        raise AssertionError("oversized CSV accepted")

    monkeypatch.setattr(module, "MAX_CSV_BYTES", 25 * 1024 * 1024)
    monkeypatch.setattr(module, "MAX_CSV_ROWS", 1)
    write_csv(source, [row(), row("A002", "第二件")])
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "50,000" in str(exc)
    else:
        raise AssertionError("CSV row limit not enforced")


def test_restore_rejects_malformed_json_shapes_without_overwriting(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    original_text = store.path.read_text(encoding="utf-8")
    original_rows = list(store.rows)
    malformed = [
        [],
        {"format": "mainland-inventory-backup", "version": 1, "items": {}},
        {"format": "mainland-inventory-backup", "version": 1, "items": [[]]},
        {"format": "mainland-inventory-backup", "version": 1, "items": [row(), row()]},
    ]
    for index, payload in enumerate(malformed):
        source = tmp_path / f"bad-{index}.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        expect_value_error(lambda source=source: store.restore(source))
        assert store.rows == original_rows
        assert store.path.read_text(encoding="utf-8") == original_text


def test_restore_replace_failure_keeps_current_state(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    other = module.InventoryStore(tmp_path / "other.json")
    other.add(row("B001", "备份商品"))
    other.backup(backup)
    original_text = store.path.read_text(encoding="utf-8")
    original_rows = list(store.rows)

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        store.restore(backup)
    except OSError:
        pass
    else:
        raise AssertionError("restore replace failure should propagate")
    assert store.rows == original_rows
    assert store.path.read_text(encoding="utf-8") == original_text
    assert list(tmp_path.glob(".inventory.json.*.tmp")) == []


def test_inventory_record_limit_prevents_unbackable_state(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    monkeypatch.setattr(module, "MAX_ITEMS", 1)
    try:
        store.add(row("A002", "第二件"))
    except ValueError as exc:
        assert "100,000" in str(exc)
    else:
        raise AssertionError("record limit not enforced")
    assert len(store.rows) == 1


def test_corrupt_inventory_opens_read_only_recovery_mode(tmp_path):
    data_path = tmp_path / "inventory.json"
    original = b"{broken-json"
    data_path.write_bytes(original)
    store = module.InventoryStore.open_for_recovery(data_path)

    assert store.read_only is True
    assert store.rows == []
    assert "库存数据无法读取" in store.load_error

    source = tmp_path / "items.csv"
    write_csv(source, [row()])
    expect_value_error(lambda: store.add(row()))
    expect_value_error(lambda: store.import_csv(source))
    expect_value_error(lambda: store.export_csv(tmp_path / "export.csv"))
    expect_value_error(lambda: store.backup(tmp_path / "backup.json"))

    assert data_path.read_bytes() == original
    assert not (tmp_path / "export.csv").exists()
    assert not (tmp_path / "backup.json").exists()


def test_invalid_backup_keeps_corrupt_inventory_in_recovery_mode(tmp_path):
    data_path = tmp_path / "inventory.json"
    original = b"not-json"
    data_path.write_bytes(original)
    store = module.InventoryStore.open_for_recovery(data_path)
    bad_backup = tmp_path / "bad-backup.json"
    bad_backup.write_text("[]", encoding="utf-8")

    expect_value_error(lambda: store.restore(bad_backup))

    assert store.read_only is True
    assert store.rows == []
    assert data_path.read_bytes() == original


def test_valid_backup_restores_corrupt_inventory_and_reenables_writes(tmp_path):
    source = module.InventoryStore(tmp_path / "source.json")
    source.add(row())
    backup = tmp_path / "valid-backup.json"
    source.backup(backup)

    data_path = tmp_path / "inventory.json"
    data_path.write_bytes(b"{damaged")
    store = module.InventoryStore.open_for_recovery(data_path)
    assert store.read_only is True

    store.restore(backup)

    assert store.read_only is False
    assert store.load_error is None
    assert store.rows == source.rows
    store.add(row("A002", "恢复后新增商品"))
    assert len(module.InventoryStore(data_path).rows) == 2



def test_valuation_report_groups_categories_and_counts_stock_states():
    first = row("A001", "纸巾")
    first.update({"分类": "日用品", "库存数量": "2.5", "预警下限": "3", "进货单价": "4.20"})
    second = row("A002", "洗衣液")
    second.update({"分类": "日用品", "库存数量": "0", "预警下限": "0", "进货单价": "9"})
    third = row("A003", "咖啡")
    third.update({"分类": "", "库存数量": "3", "预警下限": "1", "进货单价": "0.335"})

    report = module.build_valuation_report([first, second, third])

    assert report["summary"] == {
        "商品种类": 3,
        "库存总数量": module.Decimal("5.5"),
        "库存成本估值": module.Decimal("11.51"),
        "零库存商品数": 1,
        "预警商品数": 2,
    }
    assert [item["分类"] for item in report["categories"]] == ["日用品", "未分类"]
    assert report["categories"][0]["库存成本估值"] == module.Decimal("10.50")
    assert report["categories"][0]["零库存商品数"] == 1
    assert report["categories"][0]["预警商品数"] == 2
    assert report["items"][0]["商品编码"] == "A001"
    assert report["items"][1]["库存成本估值"] == module.Decimal("1.01")
    assert report["items"][2]["库存状态"] == "零库存"


def test_valuation_report_empty_inventory_returns_zero_totals():
    report = module.build_valuation_report([])

    assert report["summary"]["商品种类"] == 0
    assert report["summary"]["库存总数量"] == module.Decimal("0")
    assert report["summary"]["库存成本估值"] == module.Decimal("0.00")
    assert report["categories"] == []
    assert report["items"] == []


def test_valuation_report_does_not_mutate_inventory_rows():
    source = row(name="原始商品")
    original = dict(source)

    module.build_valuation_report([source])

    assert source == original


def test_valuation_csv_export_protects_formula_text_and_keeps_money_rounded(tmp_path):
    store = module.InventoryStore(tmp_path / "inventory.json")
    unsafe = row(code="=1+1", name="+SUM(A1:A2)")
    unsafe.update({"分类": "@分类", "单位": "-件", "库存数量": "3", "进货单价": "0.335"})
    store.add(unsafe)
    target = tmp_path / "valuation.csv"

    assert module.export_valuation_csv(target, store.rows) == 1
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    with target.open(encoding="utf-8-sig", newline="") as handle:
        record = next(csv.DictReader(handle))

    assert record["商品编码"] == "'=1+1"
    assert record["商品名称"] == "'+SUM(A1:A2)"
    assert record["分类"] == "'@分类"
    assert record["单位"] == "'-件"
    assert record["库存成本估值"] == "1.01"
    assert record["库存状态"] == "库存正常"


def test_valuation_csv_export_replace_failure_preserves_previous_file(tmp_path, monkeypatch):
    store = module.InventoryStore(tmp_path / "inventory.json")
    store.add(row())
    target = tmp_path / "valuation.csv"
    target.write_text("previous report", encoding="utf-8")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    try:
        module.export_valuation_csv(target, store.rows)
    except OSError:
        pass
    else:
        raise AssertionError("failed valuation export should propagate")

    assert target.read_text(encoding="utf-8") == "previous report"
    assert list(tmp_path.glob(".valuation.csv.*.tmp")) == []
