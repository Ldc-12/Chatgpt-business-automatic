import csv
import hashlib
import json
from datetime import timedelta

import pytest

from src import store_coupon as MODULE


def campaign_row(**changes):
    today = MODULE.local_today()
    row = {
        "活动编号": "CAMPAIGN-001",
        "活动名称": "周末满减活动",
        "优惠金额": "10.00",
        "最低消费金额": "50.00",
        "开始日期": today.isoformat(),
        "结束日期": (today + timedelta(days=10)).isoformat(),
        "发行上限": "20",
        "状态": "启用",
        "备注": "",
    }
    row.update(changes)
    return row


def add_campaign(store, **changes):
    return store.create_campaign(campaign_row(**changes))


def test_issue_redeem_persists_and_reloads_campaign_and_coupon(tmp_path):
    path = tmp_path / "coupons.json"
    store = MODULE.CouponStore(path)
    campaign_id = add_campaign(store)
    codes = store.issue_coupons(campaign_id, 2, actor="店员甲")
    store.redeem(codes[0], "ORDER-001", "88.00", actor="店员乙", note="现场核对")

    loaded = MODULE.CouponStore(path)
    assert loaded.summary() == {
        "活动数量": 1,
        "发行优惠券": 2,
        "已核销": 1,
        "未使用": 1,
        "已作废": 0,
        "已过期": 0,
        "实际优惠合计": "10.00",
    }
    assert loaded.coupons[0]["核销订单号"] == "ORDER-001"
    assert loaded.audit_summary()["事件数"] == 3


def test_campaign_rejects_discount_above_minimum_spend(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    with pytest.raises(ValueError, match="最低消费金额不能小于优惠金额"):
        add_campaign(store, **{"优惠金额": "20", "最低消费金额": "10"})
    assert store.campaigns == []
    assert not store.path.exists()


def test_campaign_rejects_invalid_dates_and_duplicate_ids(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        add_campaign(store, **{"开始日期": "2026-12-31", "结束日期": "2026-12-01"})
    add_campaign(store)
    with pytest.raises(ValueError, match="活动编号已存在"):
        add_campaign(store)
    assert len(store.campaigns) == 1


def test_issue_limit_is_enforced_without_partial_writes(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store, **{"发行上限": "2"})
    store.issue_coupons(campaign_id, 2)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="发行上限"):
        store.issue_coupons(campaign_id, 1)
    assert store.path.read_bytes() == before
    assert len(store.coupons) == 2


def test_issue_rejects_disabled_or_not_yet_active_campaign(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    store.set_campaign_status(campaign_id, "停用")
    with pytest.raises(ValueError, match="停用活动"):
        store.issue_coupons(campaign_id, 1)

    future = MODULE.CouponStore(tmp_path / "future.json")
    future_id = add_campaign(
        future,
        **{
            "活动编号": "FUTURE-001",
            "开始日期": (MODULE.local_today() + timedelta(days=1)).isoformat(),
            "结束日期": (MODULE.local_today() + timedelta(days=2)).isoformat(),
        },
    )
    with pytest.raises(ValueError, match="发行有效期"):
        future.issue_coupons(future_id, 1)


def test_redeem_requires_minimum_spend_and_leaves_coupon_unused(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    code = store.issue_coupons(campaign_id, 1)[0]
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="未达到活动最低消费金额"):
        store.redeem(code, "ORDER-LOW", "49.99")
    assert store.path.read_bytes() == before
    assert store._coupon(code)["状态"] == "未使用"


def test_coupon_can_only_be_redeemed_once_and_order_is_case_insensitive(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    first, second = store.issue_coupons(campaign_id, 2)
    store.redeem(first, "order-123", "80")
    with pytest.raises(ValueError, match="重复核销"):
        store.redeem(second, "ORDER-123", "90")
    with pytest.raises(ValueError, match="不能再次核销"):
        store.redeem(first, "ORDER-OTHER", "80")
    assert store._coupon(second)["状态"] == "未使用"


def test_void_only_applies_to_unused_coupons_and_requires_reason(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    first, second = store.issue_coupons(campaign_id, 2)
    with pytest.raises(ValueError, match="作废原因不能为空"):
        store.void_coupon(first, " ")
    store.void_coupon(first, "顾客取消")
    store.redeem(second, "ORDER-2", "50")
    with pytest.raises(ValueError, match="只有未使用"):
        store.void_coupon(second, "已核销不允许作废")
    assert store._coupon(first)["状态"] == "已作废"
    assert store._coupon(second)["状态"] == "已核销"


def test_disabled_campaign_blocks_redemption_but_preserves_history(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    code = store.issue_coupons(campaign_id, 1)[0]
    store.set_campaign_status(campaign_id, "停用")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="活动已停用"):
        store.redeem(code, "ORDER-3", "60")
    assert store.path.read_bytes() == before
    assert store._coupon(code)["状态"] == "未使用"


def test_expired_coupon_is_counted_and_cannot_be_redeemed(tmp_path, monkeypatch):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    today = MODULE.local_today()
    campaign_id = add_campaign(
        store,
        **{
            "开始日期": today.isoformat(),
            "结束日期": (today + timedelta(days=1)).isoformat(),
        },
    )
    code = store.issue_coupons(campaign_id, 1)[0]
    expired_day = today + timedelta(days=2)
    monkeypatch.setattr(MODULE, "local_today", lambda: expired_day)
    assert store.summary()["已过期"] == 1
    with pytest.raises(ValueError, match="核销有效期"):
        store.redeem(code, "ORDER-EXPIRED", "80")


def test_campaign_status_toggle_keeps_issued_coupon_records(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    code = store.issue_coupons(campaign_id, 1)[0]
    store.set_campaign_status(campaign_id, "停用", reason="活动暂停")
    store.set_campaign_status(campaign_id, "启用", reason="恢复活动")
    assert store._coupon(code)["状态"] == "未使用"
    assert store._campaign(campaign_id)["状态"] == "启用"


def test_campaign_csv_import_export_is_utf8_bom_and_formula_safe(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store, **{"备注": '=HYPERLINK("x")'})
    exported = tmp_path / "campaigns.csv"
    store.export_campaigns_csv(exported)
    assert exported.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in exported.read_text(encoding="utf-8-sig")

    imported = MODULE.CouponStore(tmp_path / "second.json")
    assert imported.import_campaigns_csv(exported) == 1
    assert imported.campaigns[0]["活动编号"] == campaign_id
    assert imported.campaigns[0]["备注"].startswith("'=")


def test_campaign_csv_import_is_all_or_nothing(tmp_path):
    source = tmp_path / "invalid.csv"
    rows = [
        campaign_row(**{"活动编号": "CAMPAIGN-OK", "活动名称": "有效"}),
        campaign_row(**{"活动编号": "CAMPAIGN-BAD", "活动名称": "", "开始日期": "bad"}),
    ]
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CAMPAIGN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    with pytest.raises(ValueError, match="第 3 行"):
        store.import_campaigns_csv(source)
    assert store.campaigns == []
    assert not store.path.exists()


def test_campaign_csv_import_rejects_duplicate_existing_ids(tmp_path):
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.CAMPAIGN_FIELDS)
        writer.writeheader()
        writer.writerow(campaign_row())
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    add_campaign(store)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="重复活动编号"):
        store.import_campaigns_csv(source)
    assert store.path.read_bytes() == before


def test_coupon_and_redemption_exports_are_formula_safe_and_filtered(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    first, second = store.issue_coupons(campaign_id, 2, note='=HYPERLINK("x")')
    store.redeem(first, "ORDER-1", "100", note="@internal")
    coupons = tmp_path / "coupons.csv"
    redemptions = tmp_path / "redemptions.csv"
    store.export_coupons_csv(coupons)
    store.export_redemptions_csv(redemptions)
    coupon_text = coupons.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in coupon_text
    assert "'@internal" in coupon_text
    rows = list(csv.DictReader(redemptions.open(encoding="utf-8-sig", newline="")))
    assert len(rows) == 1
    assert rows[0]["券编号"] == first
    assert rows[0]["实际优惠金额"] == "10.00"


def test_campaign_report_aggregates_redemptions_and_unused_coupons(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    first, second, third = store.issue_coupons(campaign_id, 3)
    store.redeem(first, "ORDER-1", "80")
    store.void_coupon(third, "测试作废")
    report = store.campaign_report()[0]
    assert report["活动编号"] == campaign_id
    assert report["发行数量"] == 3
    assert report["已核销"] == 1
    assert report["未使用"] == 1
    assert report["已作废"] == 1
    assert report["实际优惠合计"] == "10.00"


def test_backup_restore_replaces_data_and_records_restore_event(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    code = store.issue_coupons(campaign_id, 1)[0]
    store.redeem(code, "ORDER-1", "100")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    add_campaign(store, **{"活动编号": "CAMPAIGN-002", "活动名称": "新活动"})
    assert len(store.campaigns) == 2
    store.restore(backup)
    assert len(store.campaigns) == 1
    assert store.summary()["已核销"] == 1
    assert store.events[-1]["action"] == "恢复备份"


def test_tampered_backup_is_rejected_without_overwriting_current_data(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    add_campaign(store)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    add_campaign(store, **{"活动编号": "CAMPAIGN-002", "活动名称": "当前活动"})
    before = store.path.read_bytes()
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["活动"][0]["活动名称"] = "被篡改"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        store.restore(corrupt)
    assert store.path.read_bytes() == before


def test_rehashed_backup_with_tampered_audit_event_is_rejected(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    add_campaign(store)
    backup = tmp_path / "backup.json"
    store.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["操作日志"][0]["reason"] = "tampered"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = hashlib.sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "rehashed.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="操作日志 SHA256"):
        store.restore(corrupt)


def test_rehashed_backup_with_invalid_redeemed_discount_is_rejected(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    code = store.issue_coupons(campaign_id, 1)[0]
    store.redeem(code, "ORDER-1", "100")
    backup = tmp_path / "backup.json"
    store.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["优惠券"][0]["实际优惠金额"] = "99.00"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = hashlib.sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "rehashed-coupon.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="不能超过券面优惠金额"):
        store.restore(corrupt)


def test_failed_atomic_write_preserves_memory_and_disk(tmp_path, monkeypatch):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    before = store.path.read_bytes()
    original_campaigns = list(store.campaigns)

    def fail_write(path, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(MODULE, "atomic_write", fail_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.issue_coupons(campaign_id, 1)
    assert store.path.read_bytes() == before
    assert store.campaigns == original_campaigns
    assert store.coupons == []


def test_invalid_money_and_issue_count_are_rejected(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    with pytest.raises(ValueError, match="有效数字"):
        add_campaign(store, **{"优惠金额": "abc"})
    with pytest.raises(ValueError, match="正整数"):
        add_campaign(store, **{"发行上限": "1.5"})
    with pytest.raises(ValueError, match="必须在 0 至"):
        add_campaign(store, **{"优惠金额": "-1"})


def test_coupon_state_requires_existing_campaign_and_unique_order_on_load(tmp_path):
    store = MODULE.CouponStore(tmp_path / "coupons.json")
    campaign_id = add_campaign(store)
    first, second = store.issue_coupons(campaign_id, 2)
    store.redeem(first, "ORDER-1", "100")
    store.redeem(second, "ORDER-2", "100")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["优惠券"][1]["核销订单号"] = "order-1"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = hashlib.sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "duplicate-order.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="同一订单不能重复核销"):
        MODULE.CouponStore(corrupt)


def test_self_test_runs_without_gui():
    MODULE.self_test()
