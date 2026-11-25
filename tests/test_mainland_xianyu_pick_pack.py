import csv
import json
from datetime import date
import pytest
from src import xianyu_pick_pack as module


def sample(**overrides):
    row = {
        "明细编号": "PP-001", "订单编号": "XY-ORDER-001", "商品名称": "二手键盘",
        "SKU": "KB-87", "规格/成色": "黑色/九成新", "数量": 2,
        "已拣数量": 0, "已打包数量": 0, "包裹编号": "",
        "订单日期": date.today().isoformat(), "买家备注": "", "内部备注": "",
    }
    row.update(overrides)
    return row


def test_normalize_requires_order_item_and_valid_quantity_boundaries():
    assert module.normalize_row(sample())["数量"] == 2
    with pytest.raises(ValueError, match="订单编号不能为空"):
        module.normalize_row(sample(**{"订单编号": ""}))
    with pytest.raises(ValueError, match="商品名称不能为空"):
        module.normalize_row(sample(**{"商品名称": ""}))
    with pytest.raises(ValueError, match="整数"):
        module.normalize_row(sample(**{"数量": "1.5"}))
    with pytest.raises(ValueError, match="不能超过订单数量"):
        module.normalize_row(sample(**{"已拣数量": 3}))
    with pytest.raises(ValueError, match="不能超过已拣数量"):
        module.normalize_row(sample(**{"已打包数量": 1}))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        module.normalize_row(sample(**{"订单日期": "2026/11/25"}))


def test_picking_summary_groups_same_sku_and_variant_across_orders():
    rows = [
        module.normalize_row(sample()),
        module.normalize_row(sample(**{"明细编号": "PP-002", "订单编号": "XY-ORDER-002", "商品名称": "键盘（同款）", "数量": 3, "已拣数量": 1, "已打包数量": 1})),
        module.normalize_row(sample(**{"明细编号": "PP-003", "SKU": "KB-104", "数量": 1})),
    ]
    summary = module.picking_summary(rows)
    assert len(summary) == 2
    group = next(item for item in summary if item["SKU/商品"] == "KB-87")
    assert group["订单数"] == 2
    assert group["需求数量"] == 5
    assert group["已拣数量"] == 1
    assert group["待拣数量"] == 4
    assert group["待打包数量"] == 4


def test_line_status_and_progress_are_derived_from_quantities():
    assert module.line_status(module.normalize_row(sample())) == "待拣货"
    assert module.line_status(module.normalize_row(sample(**{"已拣数量": 2}))) == "已拣货"
    assert module.line_status(module.normalize_row(sample(**{"已拣数量": 2, "已打包数量": 1}))) == "打包中"
    packed = module.normalize_row(sample(**{"已拣数量": 2, "已打包数量": 2}))
    assert module.line_status(packed) == "已打包"
    assert module.packing_progress([packed])["待打包数量"] == 0


def test_store_persists_add_update_delete_and_rejects_invalid_progress(tmp_path):
    path = tmp_path / "pick-pack.json"
    store = module.PickPackStore(path)
    added = store.add(sample())
    assert module.PickPackStore(path).rows == store.rows
    store.update(added["明细编号"], {**added, "已拣数量": 2, "已打包数量": 1, "包裹编号": "PKG-001"})
    assert module.line_status(store.rows[0]) == "打包中"
    with pytest.raises(ValueError, match="不能超过已拣数量"):
        store.update(added["明细编号"], {**store.rows[0], "已打包数量": 3})
    assert module.PickPackStore(path).rows == store.rows
    store.delete(added["明细编号"])
    assert store.rows == []


def test_csv_roundtrip_is_utf8_bom_and_formula_safe(tmp_path):
    store = module.PickPackStore(tmp_path / "data.json")
    formula = '=HYPERLINK("https://bad.example","click")'
    store.add(sample(**{"买家备注": formula}))
    path = tmp_path / "orders.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.PickPackStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["买家备注"] == formula


def test_csv_import_accepts_gb18030_and_requires_minimum_headers(tmp_path):
    path = tmp_path / "legacy.csv"
    path.write_bytes("订单编号,商品名称,数量\nXY-1,测试商品,2\n".encode("gb18030"))
    store = module.PickPackStore(tmp_path / "data.json")
    assert store.import_csv(path) == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("订单编号,商品名称\nXY-2,缺少数量\n", encoding="utf-8")
    with pytest.raises(ValueError, match="必须包含"):
        store.import_csv(bad)


def test_csv_import_rejects_invalid_batch_without_partial_write(tmp_path):
    store = module.PickPackStore(tmp_path / "data.json")
    store.add(sample())
    before_rows, before_bytes = list(store.rows), store.path.read_bytes()
    bad = tmp_path / "invalid.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"明细编号": "PP-002", "数量": -1}))
    with pytest.raises(ValueError, match="数量必须在"):
        store.import_csv(bad)
    assert store.rows == before_rows
    assert store.path.read_bytes() == before_bytes


def test_csv_import_rejects_duplicate_ids_in_existing_ledger(tmp_path):
    store = module.PickPackStore(tmp_path / "data.json")
    store.add(sample())
    path = tmp_path / "duplicate.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="重复"):
        store.import_csv(path)


def test_picking_and_packing_exports_include_aggregate_and_order_detail_rows(tmp_path):
    store = module.PickPackStore(tmp_path / "data.json")
    store.add(sample())
    store.add(sample(**{"明细编号": "PP-002", "订单编号": "XY-ORDER-002"}))
    picking, packing = tmp_path / "picking.csv", tmp_path / "packing.csv"
    assert store.export_picking_list_csv(picking) == 1
    assert store.export_packing_list_csv(packing) == 2
    with picking.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["需求数量"] == "4"
    assert rows[0]["订单数"] == "2"
    with packing.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["处理状态"] == "待拣货"


def test_backup_restore_checks_sha256_before_replacing_current_data(tmp_path):
    store = module.PickPackStore(tmp_path / "data.json")
    store.add(sample())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    restored = module.PickPackStore(tmp_path / "restored.json")
    assert restored.restore(backup) == 1
    assert restored.rows == store.rows
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["买家备注"] = "tampered"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before_rows, before_bytes = list(restored.rows), restored.path.read_bytes()
    with pytest.raises(ValueError, match="SHA256"):
        restored.restore(backup)
    assert restored.rows == before_rows
    assert restored.path.read_bytes() == before_bytes


def test_self_test_is_local_and_does_not_touch_default_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "default_data_path", lambda: tmp_path / "unused.json")
    module.self_test()
    assert not (tmp_path / "unused.json").exists()
