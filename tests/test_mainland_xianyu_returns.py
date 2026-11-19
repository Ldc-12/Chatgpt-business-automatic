import csv
import json
from datetime import date, timedelta

import pytest

from src import xianyu_returns as module


def sample(**overrides):
    today = date.today()
    row = {
        "记录编号": "XY-R-001",
        "订单编号": "ORDER-001",
        "商品/SKU": "二手测试手机",
        "售后类型": "退货退款",
        "申请日期": (today - timedelta(days=3)).isoformat(),
        "订单成交金额(元)": "100",
        "申请金额(元)": "80",
        "实际退款金额(元)": "60",
        "补偿金额(元)": "5",
        "退货运费(元)": "8",
        "运费承担方": "卖家",
        "责任归属": "待核实",
        "处理状态": "待退款",
        "处理截止日期": today.isoformat(),
        "下一步动作": "核对退货商品后退款",
        "买家寄回运单号": "SF-001",
        "买家寄回日期": (today - timedelta(days=1)).isoformat(),
        "卖家收货日期": "",
        "退款完成日期": "",
        "本地证据目录": "",
        "处理摘要": "买家申请退货退款",
        "备注": "卖家内部记录",
    }
    row.update(overrides)
    return row


def test_normalize_money_and_required_fields():
    row = module.normalize_row(sample())
    assert row["订单成交金额(元)"] == "100.00"
    assert row["实际退款金额(元)"] == "60.00"
    with pytest.raises(ValueError, match="订单编号不能为空"):
        module.normalize_row(sample(**{"订单编号": ""}))
    with pytest.raises(ValueError, match="申请日期不能为空"):
        module.normalize_row(sample(**{"申请日期": ""}))


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"售后类型": "平台退款"}, "售后类型不在内置列表"),
        ({"处理状态": "已退款"}, "处理状态不在内置列表"),
        ({"订单成交金额(元)": "NaN"}, "有效数字"),
        ({"实际退款金额(元)": "Infinity"}, "有效数字"),
        ({"实际退款金额(元)": "-1"}, "不能为负数"),
        ({"申请金额(元)": "101"}, "不能超过订单成交金额"),
        ({"实际退款金额(元)": "81"}, "不能超过申请金额"),
        ({"申请日期": "2026/11/18"}, "YYYY-MM-DD"),
        ({"处理截止日期": "2026/11/18"}, "YYYY-MM-DD"),
        ({"售后类型": "仅退款", "买家寄回日期": "2026-11-18"}, "不能填写买家寄回日期"),
        ({"卖家收货日期": "2026-11-18", "买家寄回日期": ""}, "需要先填写买家寄回日期"),
        ({"退款完成日期": "2026-11-18", "实际退款金额(元)": "0"}, "需要填写大于 0"),
        ({"处理状态": "待买家寄回", "售后类型": "仅退款", "买家寄回日期": "", "买家寄回运单号": ""}, "不能进入待买家寄回状态"),
    ],
)
def test_invalid_return_fields_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_row(sample(**overrides))


def test_return_dates_must_follow_case_timeline():
    today = date.today()
    with pytest.raises(ValueError, match="不能早于申请日期"):
        module.normalize_row(sample(**{
            "申请日期": today.isoformat(),
            "买家寄回日期": (today - timedelta(days=1)).isoformat(),
        }))
    with pytest.raises(ValueError, match="不能早于买家寄回日期"):
        module.normalize_row(sample(**{
            "买家寄回日期": today.isoformat(),
            "卖家收货日期": (today - timedelta(days=1)).isoformat(),
        }))


def test_case_risk_and_summary_use_seller_entered_deadline():
    today = date.today()
    overdue = sample(**{
        "记录编号": "XY-R-OVERDUE",
        "订单编号": "ORDER-OVERDUE",
        "处理截止日期": (today - timedelta(days=4)).isoformat(),
    })
    due_today = sample(**{
        "记录编号": "XY-R-TODAY",
        "订单编号": "ORDER-TODAY",
        "处理截止日期": today.isoformat(),
    })
    soon = sample(**{
        "记录编号": "XY-R-SOON",
        "订单编号": "ORDER-SOON",
        "处理截止日期": (today + timedelta(days=2)).isoformat(),
    })
    far = sample(**{
        "记录编号": "XY-R-FAR",
        "订单编号": "ORDER-FAR",
        "处理截止日期": (today + timedelta(days=5)).isoformat(),
    })
    completed = sample(**{
        "记录编号": "XY-R-DONE",
        "订单编号": "ORDER-DONE",
        "处理状态": "已完成",
        "退款完成日期": today.isoformat(),
        "处理截止日期": (today - timedelta(days=5)).isoformat(),
    })
    assert module.case_risk(overdue, as_of=today)["逾期天数"] == 4
    assert module.case_risk(due_today, as_of=today)["待处理类型"] == "今日到期"
    assert module.case_risk(soon, as_of=today)["待处理类型"] == "3日内到期"
    assert module.case_risk(far, as_of=today)["需要跟进"] is False
    assert module.case_risk(completed, as_of=today)["需要跟进"] is False

    report = module.after_sales_summary(
        [overdue, due_today, soon, far, completed], as_of=today
    )
    assert report["案件总数"] == 5
    assert report["未结案件数"] == 4
    assert report["逾期案件数"] == 1
    assert report["待退款案件数"] == 4
    assert report["实际退款合计(元)"] == "300.00"
    assert report["补偿合计(元)"] == "25.00"
    assert report["卖家承担退货运费(元)"] == "40.00"
    assert report["已登记售后支出(元)"] == "365.00"


def test_actionable_cases_are_sorted_and_exclude_terminal_or_far_deadlines():
    today = date.today()
    rows = [
        sample(**{
            "记录编号": "XY-R-SOON",
            "订单编号": "ORDER-SOON",
            "处理截止日期": (today + timedelta(days=2)).isoformat(),
        }),
        sample(**{
            "记录编号": "XY-R-LATE",
            "订单编号": "ORDER-LATE",
            "处理截止日期": (today - timedelta(days=1)).isoformat(),
        }),
        sample(**{
            "记录编号": "XY-R-DUE",
            "订单编号": "ORDER-DUE",
            "处理截止日期": today.isoformat(),
        }),
        sample(**{
            "记录编号": "XY-R-FAR",
            "订单编号": "ORDER-FAR",
            "处理截止日期": (today + timedelta(days=9)).isoformat(),
        }),
        sample(**{
            "记录编号": "XY-R-DONE",
            "订单编号": "ORDER-DONE",
            "处理状态": "已完成",
            "退款完成日期": today.isoformat(),
            "处理截止日期": (today - timedelta(days=2)).isoformat(),
        }),
    ]
    result = module.actionable_cases(rows, as_of=today)
    assert [row["记录编号"] for row in result] == [
        "XY-R-LATE", "XY-R-DUE", "XY-R-SOON",
    ]
    assert result[0]["逾期天数"] == 1


def test_store_persists_and_status_transitions_are_validated(tmp_path):
    path = tmp_path / "returns.json"
    store = module.ReturnFollowupStore(path)
    store.add(sample())
    loaded = module.ReturnFollowupStore(path)
    assert loaded.rows == store.rows

    loaded.transition_status("XY-R-001", "待平台处理")
    assert loaded.rows[0]["处理状态"] == "待平台处理"
    loaded.transition_status("XY-R-001", "待退款")
    loaded.update("XY-R-001", dict(loaded.rows[0], **{"处理状态": "已完成", "退款完成日期": date.today().isoformat()}))
    assert module.ReturnFollowupStore(path).rows == loaded.rows


def test_invalid_transition_does_not_change_disk_or_memory(tmp_path):
    path = tmp_path / "returns.json"
    store = module.ReturnFollowupStore(path)
    store.add(sample())
    before_rows = list(store.rows)
    before_bytes = path.read_bytes()
    with pytest.raises(ValueError, match="不允许"):
        store.transition_status("XY-R-001", "待买家寄回")
    assert store.rows == before_rows
    assert path.read_bytes() == before_bytes


def test_update_rejects_id_changes_and_missing_delete(tmp_path):
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(sample())
    with pytest.raises(ValueError, match="不能修改"):
        store.update("XY-R-001", dict(store.rows[0], **{"记录编号": "XY-R-999"}))
    with pytest.raises(ValueError, match="找不到要删除"):
        store.delete("MISSING")


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(sample(**{
        "订单编号": '=HYPERLINK("https://bad.example","click")',
        "备注": "+malicious",
    }))
    path = tmp_path / "returns.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    assert "'+malicious" in raw.decode("utf-8-sig")
    imported = module.ReturnFollowupStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["订单编号"].startswith("'=")


def test_csv_import_rejects_invalid_batch_without_partial_write(tmp_path):
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(sample())
    before_rows = list(store.rows)
    before_bytes = store.path.read_bytes()
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"实际退款金额(元)": "999"}))
    with pytest.raises(ValueError, match="不能超过申请金额"):
        store.import_csv(path)
    assert store.rows == before_rows
    assert store.path.read_bytes() == before_bytes


def test_csv_import_rejects_existing_duplicate_ids(tmp_path):
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(sample())
    path = tmp_path / "duplicate.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在记录编号"):
        store.import_csv(path)


def test_action_export_is_formula_safe_and_writes_header_when_empty(tmp_path):
    today = date.today()
    row = sample(**{
        "订单编号": "=HYPERLINK(1,2)",
        "处理截止日期": today.isoformat(),
    })
    path = tmp_path / "actions.csv"
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(row)
    assert store.export_action_csv(path, as_of=today) == 1
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["订单编号"].startswith("'=")
    assert exported[0]["待处理类型"] == "今日到期"

    empty = module.ReturnFollowupStore(tmp_path / "empty.json")
    empty_path = tmp_path / "empty-actions.csv"
    assert empty.export_action_csv(empty_path, as_of=today) == 0
    with empty_path.open("r", encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == list(module.ACTION_FIELDS)


def test_backup_restore_checks_sha256_before_replacing_current_data(tmp_path):
    store = module.ReturnFollowupStore(tmp_path / "returns.json")
    store.add(sample())
    backup = tmp_path / "returns.backup.json"
    store.backup(backup)
    restored = module.ReturnFollowupStore(tmp_path / "restored.json")
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



def test_completed_refund_requires_completion_date():
    with pytest.raises(ValueError, match="必须填写退款完成日期"):
        module.normalize_row(sample(**{"处理状态": "已完成"}))
