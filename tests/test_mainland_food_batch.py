import csv
import importlib.util
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "食品批次与保质期追踪助手.py"
SPEC = importlib.util.spec_from_file_location("food_batch_assistant", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def batch(batch_id="LOT-001", *, sku="SKU-01", name="牛奶", expiry=None, qty="10", received=None):
    today = date.today()
    expiry = expiry or today + timedelta(days=10)
    received = received or min(today, expiry)
    produced = min(today, received)
    return {
        "批次编号": batch_id,
        "商品编码": sku,
        "商品名称": name,
        "供应商": "测试供应商",
        "生产日期": produced.isoformat(),
        "到期日期": expiry.isoformat(),
        "入库日期": received.isoformat(),
        "当前数量": qty,
        "单位": "盒",
        "成本单价": "2.50",
        "库位": "冷藏 A1",
        "备注": "",
    }


def test_add_persists_batch_and_initial_inbound_movement(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    loaded = MODULE.FoodBatchStore(tmp_path / "food.json")
    assert loaded.batches[0]["批次编号"] == "LOT-001"
    assert len(loaded.movements) == 1
    assert loaded.movements[0]["类型"] == "入库"
    assert loaded.movements[0]["变动数量"] == "10"


def test_fefo_issues_earliest_expiry_across_multiple_batches(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    today = date.today()
    store.add_batch(batch("LOT-LATE", expiry=today + timedelta(days=20), qty="8"))
    store.add_batch(batch("LOT-EARLY", expiry=today + timedelta(days=3), qty="4"))
    allocations = store.issue_by_fefo("SKU-01", "6", "门店销售", "日常销售", today=today)
    assert allocations == [
        {"批次编号": "LOT-EARLY", "数量": "4", "到期日期": (today + timedelta(days=3)).isoformat()},
        {"批次编号": "LOT-LATE", "数量": "2", "到期日期": (today + timedelta(days=20)).isoformat()},
    ]
    assert {row["批次编号"]: row["当前数量"] for row in store.batches} == {"LOT-LATE": "6", "LOT-EARLY": "0"}
    assert len(store.movements) == 4


def test_expired_and_zero_stock_batches_are_excluded_from_fefo(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    today = date.today()
    store.add_batch(batch("LOT-EXPIRED", expiry=today - timedelta(days=1), qty="5", received=today - timedelta(days=3)))
    store.add_batch(batch("LOT-ZERO", expiry=today + timedelta(days=1), qty="0"))
    store.add_batch(batch("LOT-OK", expiry=today + timedelta(days=2), qty="3"))
    assert [row["批次编号"] for row in store.fefo_batches(today=today)] == ["LOT-OK"]
    allocations = store.issue_by_fefo("SKU-01", "3", "客户甲", "销售", today=today)
    assert [row["批次编号"] for row in allocations] == ["LOT-OK"]


def test_fefo_insufficient_stock_is_atomic(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    before_batches = list(store.batches)
    before_movements = list(store.movements)
    try:
        store.issue_by_fefo("SKU-01", "11", "门店", "销售")
    except ValueError as exc:
        assert "库存不足" in str(exc)
    else:
        raise AssertionError("insufficient FEFO stock should be rejected")
    assert store.batches == before_batches
    assert store.movements == before_movements


def test_batch_metadata_edit_does_not_change_quantity_or_history(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    edited = batch(name="新商品名", qty="999")
    store.update_batch("LOT-001", edited)
    assert store.batches[0]["商品名称"] == "新商品名"
    assert store.batches[0]["当前数量"] == "10"
    assert len(store.movements) == 1


def test_adjustment_and_void_are_audited(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    store.adjust_batch("LOT-001", "减少", "2", "盘点差异")
    store.adjust_batch("LOT-001", "增加", "1", "补录入库")
    store.void_batch("LOT-001", "包装破损")
    assert store.batches[0]["当前数量"] == "0"
    assert [row["类型"] for row in store.movements] == ["入库", "调整", "调整", "作废"]
    assert store.movements[-1]["变动数量"] == "9"


def test_csv_roundtrip_and_import_movement(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    source = tmp_path / "batches.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS)
        writer.writeheader()
        writer.writerow(batch())
    assert store.import_csv(source) == 1
    assert store.movements[0]["原因"] == "CSV 期初批次导入"
    output = tmp_path / "export.csv"
    store.export_csv(output)
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["批次编号"] == "LOT-001"
    assert rows[0]["到期日期"] == batch()["到期日期"]


def test_duplicate_csv_import_is_rejected_without_partial_changes(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS)
        writer.writeheader()
        writer.writerow(batch("LOT-002"))
        writer.writerow(batch("LOT-001"))
    before = (list(store.batches), list(store.movements))
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "未导入任何数据" in str(exc)
    else:
        raise AssertionError("duplicate batch import should fail")
    assert (store.batches, store.movements) == before


def test_invalid_csv_does_not_change_existing_data(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    source = tmp_path / "bad.csv"
    source.write_text("批次编号,商品编码\nLOT-2,SKU-2", encoding="utf-8-sig")
    before = (list(store.batches), list(store.movements))
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid CSV should fail")
    assert (store.batches, store.movements) == before


def test_backup_restore_roundtrip_includes_traceability(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    store.issue_by_fefo("SKU-01", "3", "客户甲", "销售")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.adjust_batch("LOT-001", "增加", "2", "盘点修正")
    store.restore(backup)
    restored = MODULE.FoodBatchStore(tmp_path / "food.json")
    assert restored.batches[0]["当前数量"] == "7"
    assert len(restored.movements) == 2
    assert restored.movements[-1]["去向"] == "客户甲"


def test_invalid_backup_is_rejected_without_overwriting(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    backup = tmp_path / "bad.json"
    backup.write_text('{"format":"unknown","version":99,"batches":[],"movements":[]}', encoding="utf-8")
    before = (list(store.batches), list(store.movements))
    try:
        store.restore(backup)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid backup should fail")
    assert (store.batches, store.movements) == before


def test_restore_rejects_movement_for_missing_batch(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    payload = {
        "format": MODULE.BACKUP_FORMAT,
        "version": MODULE.BACKUP_VERSION,
        "batches": [batch()],
        "movements": [{
            "流水编号": "BAD", "批次编号": "NO-SUCH-LOT", "商品编码": "SKU-01",
            "商品名称": "牛奶", "类型": "出库", "变动方向": "减少", "变动数量": "1",
            "发生时间": "2026-11-11T10:00:00", "去向": "客户", "原因": "销售",
        }],
    }
    backup = tmp_path / "bad-reference.json"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = (list(store.batches), list(store.movements))
    try:
        store.restore(backup)
    except ValueError as exc:
        assert "不存在的批次" in str(exc)
    else:
        raise AssertionError("orphan movement should be rejected")
    assert (store.batches, store.movements) == before


def test_expiry_state_boundaries(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    today = date.today()
    assert store.expiry_state(MODULE.normalize_batch(batch("A", expiry=today - timedelta(days=1)))) == ("已过期", -1)
    assert store.expiry_state(MODULE.normalize_batch(batch("B", expiry=today))) == ("3日内到期", 0)
    assert store.expiry_state(MODULE.normalize_batch(batch("C", expiry=today + timedelta(days=4)))) == ("4–7日内到期", 4)
    assert store.expiry_state(MODULE.normalize_batch(batch("D", expiry=today + timedelta(days=15)))) == ("8–30日内到期", 15)
    assert store.expiry_state(MODULE.normalize_batch(batch("E", expiry=today + timedelta(days=31)))) == ("正常", 31)


def test_batch_id_cannot_be_changed_after_history_exists(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    changed = batch("LOT-RENAMED")
    try:
        store.update_batch("LOT-001", changed)
    except ValueError as exc:
        assert "不可修改" in str(exc)
    else:
        raise AssertionError("batch ID change should be rejected")
    assert store.batches[0]["批次编号"] == "LOT-001"
    assert store.movements[0]["批次编号"] == "LOT-001"


def test_fefo_requires_sku_destination_and_reason(tmp_path):
    store = MODULE.FoodBatchStore(tmp_path / "food.json")
    store.add_batch(batch())
    for args in [
        ("", "1", "门店", "销售"),
        ("SKU-01", "1", "", "销售"),
        ("SKU-01", "1", "门店", ""),
    ]:
        try:
            store.issue_by_fefo(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("incomplete FEFO issue should be rejected")
    assert store.batches[0]["当前数量"] == "10"
