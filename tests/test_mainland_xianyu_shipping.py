import csv
import json
from datetime import date, timedelta

import pytest

from src import xianyu_shipping as module


def sample(**overrides):
    today = date.today()
    row = {
        "发货编号": "XY-S-001",
        "订单编号": "ORDER-001",
        "商品/SKU": "二手测试手机",
        "买家备注": "",
        "承运商": "",
        "运单号": "",
        "下单日期": (today - timedelta(days=3)).isoformat(),
        "承诺发货日期": (today - timedelta(days=1)).isoformat(),
        "实际发货日期": "",
        "揽收确认日期": "",
        "预计送达日期": "",
        "签收日期": "",
        "物流状态": "待打包",
        "包裹重量(kg)": "0.5",
        "运费(元)": "8",
        "异常说明": "",
        "备注": "卖家内部记录",
    }
    row.update(overrides)
    return row


def test_normalize_money_weight_and_required_fields():
    row = module.normalize_row(sample())
    assert row["运费(元)"] == "8.00"
    assert row["包裹重量(kg)"] == "0.5"
    with pytest.raises(ValueError, match="订单编号不能为空"):
        module.normalize_row(sample(**{"订单编号": ""}))
    with pytest.raises(ValueError, match="承诺发货日期不能为空"):
        module.normalize_row(sample(**{"承诺发货日期": ""}))


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"物流状态": "已发货"}, "物流状态不在内置列表"),
        ({"包裹重量(kg)": "-0.1"}, "0–1000 kg"),
        ({"包裹重量(kg)": "NaN"}, "有效数字"),
        ({"运费(元)": "-1"}, "不能为负数"),
        ({"运费(元)": "Infinity"}, "有效数字"),
        ({"承诺发货日期": "2026/11/18"}, "YYYY-MM-DD"),
        ({"承诺发货日期": "2026-11-17", "下单日期": "2026-11-18"}, "不能早于下单日期"),
        ({"揽收确认日期": "2026-11-18"}, "需要先填写实际发货日期"),
        ({"物流状态": "待揽收"}, "必须填写承运商"),
        ({"物流状态": "运输中"}, "必须填写承运商"),
        ({"物流状态": "已签收"}, "必须填写承运商"),
        ({"物流状态": "异常"}, "必须填写异常说明"),
    ],
)
def test_invalid_shipping_fields_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_row(sample(**overrides))


def test_shipping_risk_boundaries_and_summary():
    today = date.today()
    late = sample()
    awaiting = sample(
        **{
            "发货编号": "XY-S-002",
            "订单编号": "ORDER-002",
            "承运商": "顺丰速运",
            "运单号": "SF-002",
            "实际发货日期": (today - timedelta(days=1)).isoformat(),
            "物流状态": "待揽收",
            "运费(元)": "10.50",
        }
    )
    transit = sample(
        **{
            "发货编号": "XY-S-003",
            "订单编号": "ORDER-003",
            "下单日期": (today - timedelta(days=7)).isoformat(),
            "承运商": "中通快递",
            "运单号": "ZT-003",
            "实际发货日期": (today - timedelta(days=5)).isoformat(),
            "揽收确认日期": (today - timedelta(days=4)).isoformat(),
            "预计送达日期": (today - timedelta(days=1)).isoformat(),
            "物流状态": "运输中",
            "运费(元)": "6.50",
        }
    )
    assert module.shipping_risk(late, as_of=today)["发货逾期"] is True
    assert module.shipping_risk(awaiting, as_of=today)["等待揽收"] is True
    assert module.shipping_risk(transit, as_of=today)["送达逾期"] is True
    assert module.shipping_risk(transit, as_of=today)["逾期天数"] == 1
    report = module.shipping_summary([late, awaiting, transit], as_of=today)
    assert report["发货总数"] == 3
    assert report["发货逾期数量"] == 1
    assert report["等待揽收数量"] == 1
    assert report["送达逾期数量"] == 1
    assert report["累计运费(元)"] == "25.00"


def test_store_persists_and_status_transitions_stamp_dates_atomically(tmp_path):
    path = tmp_path / "shipping.json"
    store = module.ShippingStore(path)
    store.add(sample())
    loaded = module.ShippingStore(path)
    assert loaded.rows == store.rows

    prepared = dict(
        loaded.rows[0],
        **{"承运商": "顺丰速运", "运单号": "SF-001", "物流状态": "待揽收"},
    )
    loaded.update("XY-S-001", prepared)
    assert loaded.rows[0]["实际发货日期"] == date.today().isoformat()

    loaded.transition_status("XY-S-001", "运输中")
    assert loaded.rows[0]["揽收确认日期"] == date.today().isoformat()
    loaded.transition_status("XY-S-001", "派送中")
    loaded.transition_status("XY-S-001", "已签收")
    assert loaded.rows[0]["签收日期"] == date.today().isoformat()
    assert module.ShippingStore(path).rows == loaded.rows


def test_invalid_status_transition_does_not_change_disk_or_memory(tmp_path):
    path = tmp_path / "shipping.json"
    store = module.ShippingStore(path)
    store.add(sample())
    before_rows = list(store.rows)
    before_bytes = path.read_bytes()
    with pytest.raises(ValueError, match="不允许"):
        store.transition_status("XY-S-001", "运输中")
    assert store.rows == before_rows
    assert path.read_bytes() == before_bytes


def test_update_rejects_id_changes_and_missing_delete(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample())
    with pytest.raises(ValueError, match="不能修改"):
        store.update("XY-S-001", dict(store.rows[0], **{"发货编号": "XY-S-999"}))
    with pytest.raises(ValueError, match="找不到要删除"):
        store.delete("MISSING")


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample(**{"买家备注": "=HYPERLINK(\"https://bad.example\",\"click\")"}))
    path = tmp_path / "shipping.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.ShippingStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["买家备注"].startswith("'=")


def test_csv_import_rejects_invalid_batch_without_partial_write(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample())
    before_rows = list(store.rows)
    before_bytes = store.path.read_bytes()
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"运费(元)": "-9"}))
    with pytest.raises(ValueError, match="运费不能为负数"):
        store.import_csv(path)
    assert store.rows == before_rows
    assert store.path.read_bytes() == before_bytes


def test_csv_import_rejects_existing_duplicate_ids(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample())
    path = tmp_path / "duplicate.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在发货编号"):
        store.import_csv(path)


def test_backup_restore_checks_sha256_before_replacing_current_data(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample())
    backup = tmp_path / "shipping.backup.json"
    store.backup(backup)
    restored = module.ShippingStore(tmp_path / "restored.json")
    restored.restore(backup)
    assert restored.rows == store.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["备注"] = "tampered"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(restored.rows)
    before_bytes = restored.path.read_bytes()
    with pytest.raises(ValueError, match="SHA256"):
        restored.restore(backup)
    assert restored.rows == before
    assert restored.path.read_bytes() == before_bytes


def test_self_test_runs_without_network_or_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "default_data_path", lambda: tmp_path / "default.json")
    module.self_test()
