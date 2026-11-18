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


def delivered_sample(
    shipment_id, *, carrier="顺丰速运", pickup_days=3,
    expected_days=1, signed_days=1, freight="8",
):
    today = date.today()
    return sample(**{
        "发货编号": shipment_id,
        "订单编号": "ORDER-" + shipment_id,
        "承运商": carrier,
        "运单号": "WAY-" + shipment_id,
        "下单日期": (today - timedelta(days=10)).isoformat(),
        "承诺发货日期": (today - timedelta(days=8)).isoformat(),
        "实际发货日期": (today - timedelta(days=5)).isoformat(),
        "揽收确认日期": (today - timedelta(days=pickup_days)).isoformat(),
        "预计送达日期": (
            (today - timedelta(days=expected_days)).isoformat()
            if expected_days is not None else ""
        ),
        "签收日期": (today - timedelta(days=signed_days)).isoformat(),
        "物流状态": "已签收",
        "运费(元)": freight,
    })


def test_carrier_performance_counts_only_assessed_signed_orders():
    today = date.today()
    rows = [
        delivered_sample("XY-S-C1", pickup_days=3, expected_days=1, signed_days=1),
        delivered_sample("XY-S-C2", pickup_days=4, expected_days=1, signed_days=0, freight="10"),
        delivered_sample("XY-S-C3", pickup_days=2, expected_days=None, signed_days=0, freight="12"),
        sample(**{
            "发货编号": "XY-S-C4",
            "订单编号": "ORDER-C4",
            "承运商": "顺丰速运",
            "运单号": "WAY-C4",
            "下单日期": (today - timedelta(days=5)).isoformat(),
            "承诺发货日期": (today - timedelta(days=3)).isoformat(),
            "实际发货日期": (today - timedelta(days=2)).isoformat(),
            "揽收确认日期": (today - timedelta(days=1)).isoformat(),
            "预计送达日期": (today + timedelta(days=2)).isoformat(),
            "物流状态": "运输中",
            "运费(元)": "6",
        }),
        sample(**{"发货编号": "XY-S-C5", "订单编号": "ORDER-C5", "运费(元)": "2"}),
    ]
    report = module.carrier_performance(rows)
    assert report["承运商数量"] == 1
    assert report["未填写承运商单数"] == 1
    stat = report["承运商明细"][0]
    assert stat["承运商"] == "顺丰速运"
    assert stat["发货单数"] == 4
    assert stat["已签收单数"] == 3
    assert stat["准时评估单数"] == 2
    assert stat["准时签收单数"] == 1
    assert stat["逾期签收单数"] == 1
    assert stat["未设置预计送达单数"] == 1
    assert stat["准时率(%)"] == "50.00"
    assert stat["平均揽收到签收天数"] == "2.67"
    assert stat["累计运费(元)"] == "36.00"
    assert stat["已签收运费(元)"] == "30.00"


def test_carrier_performance_empty_and_unassessed_data_are_safe():
    assert module.carrier_performance([]) == {
        "承运商数量": 0, "未填写承运商单数": 0, "承运商明细": [],
    }
    row = delivered_sample("XY-S-NO-ETA", expected_days=None)
    stat = module.carrier_performance([row])["承运商明细"][0]
    assert stat["准时评估单数"] == 0
    assert stat["准时率(%)"] == ""
    assert stat["未设置预计送达单数"] == 1
    assert stat["平均揽收到签收天数"] == "2.00"


def test_carrier_performance_csv_is_formula_safe_and_does_not_mutate_rows(tmp_path):
    row = delivered_sample("XY-S-CSV", carrier="=恶意承运商")
    before = dict(row)
    path = tmp_path / "carrier-performance.csv"
    assert module.export_carrier_performance_csv([row], path) == 1
    assert row == before
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["承运商"] == "'=恶意承运商"
    assert exported[0]["准时率(%)"] == "100.00"

def test_transition_status_respects_backdated_change_dates(tmp_path):
    store = module.ShippingStore(tmp_path / "shipping.json")
    store.add(sample())
    prepared = dict(
        store.rows[0],
        **{"承运商": "顺丰速运", "运单号": "SF-HISTORY-001"},
    )
    store.update("XY-S-001", prepared)

    shipped_on = date.today() - timedelta(days=2)
    picked_up_on = date.today() - timedelta(days=1)
    signed_on = date.today()
    store.transition_status("XY-S-001", "待揽收", changed_on=shipped_on)
    assert store.rows[0]["实际发货日期"] == shipped_on.isoformat()
    store.transition_status("XY-S-001", "运输中", changed_on=picked_up_on)
    assert store.rows[0]["揽收确认日期"] == picked_up_on.isoformat()
    store.transition_status("XY-S-001", "派送中", changed_on=picked_up_on)
    store.transition_status("XY-S-001", "已签收", changed_on=signed_on)
    assert store.rows[0]["签收日期"] == signed_on.isoformat()
    assert module.ShippingStore(store.path).rows == store.rows



def test_attention_export_contains_only_actionable_rows_and_is_formula_safe(tmp_path):
    today = date.today()
    late_dispatch = sample(**{
        "发货编号": "XY-S-A1",
        "订单编号": "=HYPERLINK(\"https://bad.example\",\"open\")",
        "下单日期": (today - timedelta(days=5)).isoformat(),
        "承诺发货日期": (today - timedelta(days=2)).isoformat(),
    })
    awaiting_pickup = sample(**{
        "发货编号": "XY-S-A2",
        "订单编号": "ORDER-A2",
        "承运商": "顺丰速运",
        "运单号": "SF-A2",
        "下单日期": (today - timedelta(days=4)).isoformat(),
        "承诺发货日期": (today - timedelta(days=3)).isoformat(),
        "实际发货日期": (today - timedelta(days=1)).isoformat(),
        "物流状态": "待揽收",
    })
    overdue_delivery = sample(**{
        "发货编号": "XY-S-A3",
        "订单编号": "ORDER-A3",
        "承运商": "中通快递",
        "运单号": "ZT-A3",
        "下单日期": (today - timedelta(days=7)).isoformat(),
        "承诺发货日期": (today - timedelta(days=6)).isoformat(),
        "实际发货日期": (today - timedelta(days=5)).isoformat(),
        "揽收确认日期": (today - timedelta(days=4)).isoformat(),
        "预计送达日期": (today - timedelta(days=1)).isoformat(),
        "物流状态": "运输中",
    })
    exception = sample(**{
        "发货编号": "XY-S-A4",
        "订单编号": "ORDER-A4",
        "物流状态": "异常",
        "异常说明": "买家地址需要人工核实",
    })
    normal = sample(**{
        "发货编号": "XY-S-A5",
        "订单编号": "ORDER-A5",
        "承诺发货日期": (today + timedelta(days=1)).isoformat(),
    })
    delivered = delivered_sample("XY-S-A6", expected_days=2, signed_days=1)
    rows = [
        late_dispatch, awaiting_pickup, overdue_delivery,
        exception, normal, delivered,
    ]
    before = [dict(row) for row in rows]
    path = tmp_path / "attention.csv"

    assert module.export_shipping_attention_csv(rows, path, as_of=today) == 4
    assert rows == before
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert [row["待处理类型"] for row in exported] == [
        "发货逾期", "物流异常", "送达逾期", "等待揽收",
    ]
    assert exported[0]["订单编号"].startswith("'=HYPERLINK")
    assert exported[0]["逾期天数"] == "2"
    assert exported[2]["逾期天数"] == "1"
    assert exported[1]["逾期天数"] == ""
    assert exported[3]["逾期天数"] == ""
    assert "XY-S-A5" not in {row["发货编号"] for row in exported}
    assert "XY-S-A6" not in {row["发货编号"] for row in exported}


def test_attention_export_writes_header_when_no_follow_up_is_needed(tmp_path):
    row = sample(**{
        "承诺发货日期": (date.today() + timedelta(days=2)).isoformat(),
    })
    path = tmp_path / "empty-attention.csv"
    assert module.export_shipping_attention_csv([row], path) == 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        assert next(reader) == list(module.ATTENTION_FIELDS)
        assert list(reader) == []
