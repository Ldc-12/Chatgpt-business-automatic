from datetime import date, timedelta
import csv
import json

import pytest

from src import store_receiving as MODULE


def line(**changes):
    row = {
        "明细编号": "RCV-LINE-001",
        "收货单号": "RCV-2026-001",
        "采购单号": "PO-2026-001",
        "供应商": "供应商甲",
        "到货日期": date.today().isoformat(),
        "经办人": "张三",
        "备注": "",
        "SKU": "SKU-001",
        "商品名称": "测试商品",
        "订购数量": "10",
        "实收数量": "12",
        "破损数量": "1",
        "拒收数量": "2",
        "采购单价": "10.00",
        "差异原因": "外箱破损并有超收",
        "差异处理": "",
        "处理备注": "拍照留档",
    }
    row.update(changes)
    return row


def store_with_line(tmp_path, **changes):
    store = MODULE.ReceivingStore(tmp_path / "receiving.json")
    store.add_line(line(**changes))
    return store


def test_receiving_line_persists_and_reloads_from_local_json(tmp_path):
    store = store_with_line(tmp_path)
    loaded = MODULE.ReceivingStore(store.path)
    assert loaded.lines == store.lines
    assert loaded.summary()["收货单数"] == 1


def test_receipt_calculates_accepted_short_over_damage_reject_and_amounts(tmp_path):
    store = store_with_line(tmp_path)
    report = store.report_rows()[0]
    assert report["验收合格数量"] == "7"
    assert report["短缺数量"] == "0"
    assert report["超收数量"] == "2"
    assert report["验收金额"] == "70.00"
    assert report["差异金额"] == "50.00"
    summary = store.summary()
    assert summary["差异明细数"] == 1
    assert summary["待处理差异"] == 1
    assert summary["破损数量"] == "1"
    assert summary["拒收数量"] == "2"


def test_shortage_is_pending_and_can_be_resolved_without_erasing_exception(tmp_path):
    store = store_with_line(
        tmp_path,
        **{
            "实收数量": "7",
            "破损数量": "0",
            "拒收数量": "0",
            "差异原因": "少货",
            "差异处理": "",
        },
    )
    report = store.report_rows()[0]
    assert report["验收合格数量"] == "7"
    assert report["短缺数量"] == "3"
    assert report["差异金额"] == "30.00"
    assert store.summary()["待处理差异"] == 1

    changed = line(
        **{
            "实收数量": "7",
            "破损数量": "0",
            "拒收数量": "0",
            "差异原因": "少货",
            "差异处理": "已补发",
        }
    )
    store.update_line("RCV-LINE-001", changed)
    assert store.summary()["待处理差异"] == 0
    assert store.summary()["差异明细数"] == 1


def test_overdelivery_is_not_added_to_payable_quantity(tmp_path):
    store = store_with_line(
        tmp_path,
        **{
            "订购数量": "10",
            "实收数量": "13",
            "破损数量": "0",
            "拒收数量": "0",
            "采购单价": "2.00",
            "差异原因": "供应商多送",
        },
    )
    report = store.report_rows()[0]
    assert report["验收合格数量"] == "10"
    assert report["超收数量"] == "3"
    assert report["验收金额"] == "20.00"
    assert report["差异金额"] == "6.00"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"收货单号": "../escape"}, "收货单号"),
        ({"SKU": "../escape"}, "SKU"),
        ({"供应商": ""}, "供应商"),
        ({"商品名称": ""}, "商品名称"),
        ({"订购数量": "0"}, "订购数量"),
        ({"实收数量": "-1"}, "实收数量"),
        ({"采购单价": "NaN"}, "采购单价"),
        ({"破损数量": "9", "拒收数量": "4"}, "之和不能超过实收数量"),
    ],
)
def test_invalid_receipt_fields_are_rejected(tmp_path, changes, message):
    store = MODULE.ReceivingStore(tmp_path / "bad.json")
    with pytest.raises(ValueError, match=message):
        store.add_line(line(**changes))
    assert store.lines == []


def test_future_receipt_date_is_rejected(tmp_path):
    store = MODULE.ReceivingStore(tmp_path / "future.json")
    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="不能晚于今天"):
        store.add_line(line(**{"到货日期": future}))
    assert store.lines == []


def test_difference_requires_reason_and_valid_resolution_state(tmp_path):
    store = MODULE.ReceivingStore(tmp_path / "reason.json")
    with pytest.raises(ValueError, match="必须填写差异原因"):
        store.add_line(line(**{"差异原因": ""}))
    with pytest.raises(ValueError, match="差异处理状态"):
        store.add_line(line(**{"差异处理": "无需处理"}))
    assert store.lines == []


def test_no_difference_defaults_to_no_action(tmp_path):
    store = store_with_line(
        tmp_path,
        **{
            "实收数量": "10",
            "破损数量": "0",
            "拒收数量": "0",
            "差异原因": "",
            "差异处理": "",
        },
    )
    assert store.lines[0]["差异处理"] == "无需处理"
    assert store.report_rows()[0]["差异状态"] == "无差异"


def test_duplicate_line_ids_are_rejected_case_insensitively(tmp_path):
    store = store_with_line(tmp_path)
    with pytest.raises(ValueError, match="编号已存在"):
        store.add_line(line(**{"明细编号": "rcv-line-001"}))


def test_same_receipt_header_must_be_consistent(tmp_path):
    store = store_with_line(tmp_path)
    with pytest.raises(ValueError, match="同一收货单号"):
        store.add_line(
            line(
                **{
                    "明细编号": "RCV-LINE-002",
                    "SKU": "SKU-002",
                    "供应商": "供应商乙",
                }
            )
        )
    assert len(store.lines) == 1


def test_csv_import_is_all_or_nothing_and_requires_exact_header(tmp_path):
    store = store_with_line(tmp_path)
    path = tmp_path / "incoming.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.LINE_FIELDS)
        writer.writeheader()
        writer.writerow(line(**{"明细编号": "RCV-LINE-002", "收货单号": "RCV-2026-002"}))
        writer.writerow(line(**{"明细编号": "RCV-LINE-001"}))
    with pytest.raises(ValueError, match="重复收货明细编号"):
        store.import_csv(path)
    assert len(store.lines) == 1

    wrong = tmp_path / "wrong.csv"
    wrong.write_text("收货单号,供应商\nRCV-1,供应商甲\n", encoding="utf-8")
    with pytest.raises(ValueError, match="表头不匹配"):
        store.import_csv(wrong)


def test_csv_export_import_roundtrip_preserves_receipt_lines(tmp_path):
    source = store_with_line(tmp_path)
    exported = tmp_path / "receipts.csv"
    source.export_csv(exported)

    target = MODULE.ReceivingStore(tmp_path / "restored.json")
    assert target.import_csv(exported) == 1
    assert target.lines == source.lines


def test_csv_exports_are_utf8_bom_and_formula_safe(tmp_path):
    store = store_with_line(
        tmp_path,
        **{
            "备注": '=HYPERLINK("https://bad")',
            "处理备注": "@supplier",
        },
    )
    output = tmp_path / "all.csv"
    store.export_csv(output)
    content = output.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in content
    assert "'@supplier" in content

    report = tmp_path / "differences.csv"
    store.export_difference_csv(report)
    assert "差异金额" in report.read_text(encoding="utf-8-sig")
    assert "RCV-LINE-001" in report.read_text(encoding="utf-8-sig")


def test_difference_export_excludes_normal_receipts(tmp_path):
    store = store_with_line(tmp_path)
    store.add_line(
        line(
            **{
                "明细编号": "RCV-LINE-002",
                "收货单号": "RCV-2026-002",
                "实收数量": "10",
                "破损数量": "0",
                "拒收数量": "0",
                "差异原因": "",
                "差异处理": "",
            }
        )
    )
    assert len(store.difference_rows()) == 1


def test_backup_restore_verifies_sha_and_replaces_current_state(tmp_path):
    store = store_with_line(tmp_path)
    backup = tmp_path / "backup.json"
    digest = store.backup(backup)
    assert len(digest) == 64
    store.add_line(line(**{"明细编号": "RCV-LINE-002", "收货单号": "RCV-2026-002"}))
    assert len(store.lines) == 2
    assert store.restore(backup) == 1
    assert len(MODULE.ReceivingStore(store.path).lines) == 1


def test_corrupt_backup_does_not_replace_current_data(tmp_path):
    store = store_with_line(tmp_path)
    backup = tmp_path / "bad.json"
    payload = MODULE.ReceivingStore._payload(store.lines)
    payload["收货明细"][0]["商品名称"] = "被篡改"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(backup)
    assert store.lines[0]["商品名称"] == "测试商品"


def test_tampered_local_state_is_rejected_on_reload(tmp_path):
    store = store_with_line(tmp_path)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["收货明细"][0]["实收数量"] = "999"
    store.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        MODULE.ReceivingStore(store.path)


def test_failed_atomic_write_keeps_memory_and_disk_unchanged(tmp_path, monkeypatch):
    store = store_with_line(tmp_path)
    original_bytes = store.path.read_bytes()
    original_lines = list(store.lines)

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(MODULE, "atomic_write", fail_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.add_line(line(**{"明细编号": "RCV-LINE-002", "收货单号": "RCV-2026-002"}))
    assert store.lines == original_lines
    assert store.path.read_bytes() == original_bytes


def test_search_matches_supplier_receipt_and_sku(tmp_path):
    store = store_with_line(tmp_path)
    assert len(store.search_lines("供应商甲")) == 1
    assert len(store.search_lines("RCV-2026")) == 1
    assert len(store.search_lines("SKU-001")) == 1
    assert store.search_lines("not-found") == []


def test_self_test_runs_without_gui_or_network():
    MODULE.self_test()


def test_supplier_summary_groups_receipts_and_separates_pending_from_resolved_amounts(tmp_path):
    store = store_with_line(
        tmp_path,
        **{
            "实收数量": "7",
            "破损数量": "0",
            "拒收数量": "0",
            "采购单价": "10.00",
            "差异原因": "少货",
            "差异处理": "待处理",
        },
    )
    store.add_line(
        line(
            **{
                "明细编号": "RCV-LINE-002",
                "收货单号": "RCV-2026-002",
                "采购单号": "PO-2026-002",
                "SKU": "SKU-002",
                "商品名称": "超收商品",
                "订购数量": "10",
                "实收数量": "12",
                "破损数量": "0",
                "拒收数量": "0",
                "采购单价": "5.00",
                "差异原因": "供应商多送",
                "差异处理": "已折让",
            }
        )
    )
    store.add_line(
        line(
            **{
                "明细编号": "RCV-LINE-003",
                "SKU": "SKU-003",
                "商品名称": "正常商品",
                "订购数量": "10",
                "实收数量": "10",
                "破损数量": "0",
                "拒收数量": "0",
                "采购单价": "1.00",
                "差异原因": "",
                "差异处理": "",
            }
        )
    )

    rows = store.supplier_summary_rows()
    assert len(rows) == 1
    assert rows[0] == {
        "供应商": "供应商甲",
        "统计开始日期": "不限",
        "统计结束日期": "不限",
        "收货单数": 2,
        "收货明细数": 3,
        "差异明细数": 2,
        "待处理差异": 1,
        "短缺数量": "3",
        "超收数量": "2",
        "破损数量": "0",
        "拒收数量": "0",
        "验收金额": "130.00",
        "差异金额": "40.00",
        "待处理差异金额": "30.00",
    }


def test_supplier_summary_export_is_utf8_bom_and_formula_safe(tmp_path):
    store = store_with_line(tmp_path, **{"供应商": "=Vendor"})
    output = tmp_path / "supplier-summary.csv"
    store.export_supplier_summary_csv(output)

    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    content = raw.decode("utf-8-sig")
    assert "'=Vendor" in content
    assert "待处理差异金额" in content



def test_supplier_summary_filters_inclusive_arrival_date_range_and_records_period(tmp_path):
    today = date.today()
    start = today - timedelta(days=10)
    end = today - timedelta(days=5)
    store = MODULE.ReceivingStore(tmp_path / "period.json")
    store.add_line(line(**{
        "明细编号": "RCV-LINE-101",
        "收货单号": "RCV-2026-101",
        "到货日期": start.isoformat(),
    }))
    store.add_line(line(**{
        "明细编号": "RCV-LINE-102",
        "收货单号": "RCV-2026-102",
        "到货日期": end.isoformat(),
    }))
    store.add_line(line(**{
        "明细编号": "RCV-LINE-103",
        "收货单号": "RCV-2026-103",
        "供应商": "供应商乙",
        "到货日期": today.isoformat(),
    }))

    rows = store.supplier_summary_rows(start.isoformat(), end.isoformat())
    assert len(rows) == 1
    assert rows[0]["供应商"] == "供应商甲"
    assert rows[0]["收货单数"] == 2
    assert rows[0]["收货明细数"] == 2
    assert rows[0]["统计开始日期"] == start.isoformat()
    assert rows[0]["统计结束日期"] == end.isoformat()

    assert {row["供应商"] for row in store.supplier_summary_rows(start_date=end.isoformat())} == {
        "供应商甲", "供应商乙"
    }
    assert [row["供应商"] for row in store.supplier_summary_rows(end_date=end.isoformat())] == [
        "供应商甲"
    ]


def test_supplier_summary_rejects_invalid_or_reversed_period(tmp_path):
    store = store_with_line(tmp_path)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        store.supplier_summary_rows("not-a-date", None)
    with pytest.raises(ValueError, match="不能晚于"):
        store.supplier_summary_rows(date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat())



def test_supplier_summary_all_time_export_preserves_legacy_csv_header(tmp_path):
    store = store_with_line(tmp_path, **{"供应商": "=Vendor"})
    output = tmp_path / "supplier-summary-all-time.csv"
    store.export_supplier_summary_csv(output)

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == MODULE.SUPPLIER_SUMMARY_FIELDS
    assert "统计开始日期" not in reader.fieldnames
    assert len(rows) == 1
    assert rows[0]["供应商"] == "'=Vendor"


def test_supplier_summary_unbounded_period_export_keeps_explicit_metadata(tmp_path):
    store = store_with_line(tmp_path)
    output = tmp_path / "supplier-summary-unbounded.csv"
    store.export_supplier_summary_period_csv(output, "", "")

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == MODULE.SUPPLIER_SUMMARY_PERIOD_FIELDS
    assert len(rows) == 1
    assert rows[0]["统计开始日期"] == "不限"
    assert rows[0]["统计结束日期"] == "不限"

def test_supplier_summary_period_export_includes_filter_metadata(tmp_path):
    store = store_with_line(tmp_path)
    start = date.today().isoformat()
    end = start
    output = tmp_path / "supplier-summary-period.csv"
    store.export_supplier_summary_period_csv(output, start, end)

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["统计开始日期"] == start
    assert rows[0]["统计结束日期"] == end
