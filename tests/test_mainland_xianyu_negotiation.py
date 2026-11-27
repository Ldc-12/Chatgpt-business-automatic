import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.xianyu_negotiation import (
    FIELDS, MAX_IMPORT_BYTES, PRODUCT, NegotiationStore, _money, _safe_text, _restore_safe_text, default_data_path,
    followup_rows, normalize_row, self_test, summary_rows,
)


def row(**overrides):
    value = {
        "记录编号": "XN-001", "商品编号": "XY-001", "订单编号": "ORDER-001",
        "商品名称": "二手手机", "SKU": "BLACK-128", "买家备注": "买家A",
        "询价日期": "2026-11-20", "标价": "1000", "最低接受价": "850",
        "买家报价": "800", "卖家回价": "900", "成交价": "",
        "商品成本": "600", "平台费用": "10", "运费成本": "8",
        "结果": "议价中", "最近沟通日期": "2026-11-20",
        "下次跟进日期": "2026-11-21", "未成交原因": "", "内部备注": "",
    }
    value.update(overrides)
    return value


def test_money_uses_decimal_rounding_and_currency_separators():
    assert _money("￥1,234.567", "金额") == Decimal("1234.57")


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "10000000000", "not-money"])
def test_money_rejects_negative_non_finite_and_out_of_range_values(value):
    with pytest.raises(ValueError):
        _money(value, "金额")


def test_normalize_requires_listing_and_inquiry_date():
    with pytest.raises(ValueError, match="商品编号不能为空"):
        normalize_row(row(商品编号=""))
    with pytest.raises(ValueError, match="询价日期不能为空"):
        normalize_row(row(询价日期=""))


def test_normalize_rejects_invalid_dates_and_date_order():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        normalize_row(row(询价日期="20261120"))
    with pytest.raises(ValueError, match="不能早于询价日期"):
        normalize_row(row(最近沟通日期="2026-11-19"))


def test_normalize_requires_positive_asking_price_and_valid_outcome():
    with pytest.raises(ValueError, match="标价必须大于 0"):
        normalize_row(row(标价="0"))
    with pytest.raises(ValueError, match="结果必须是"):
        normalize_row(row(结果="未知"))


def test_sold_requires_final_price_and_open_record_cannot_have_final_price():
    with pytest.raises(ValueError, match="必须填写大于 0 的成交价"):
        normalize_row(row(结果="已成交", 成交价=""))
    with pytest.raises(ValueError, match="只有已成交记录才能填写成交价"):
        normalize_row(row(结果="议价中", 成交价="900"))


def test_add_persists_and_update_preserves_record_id(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    added = store.add(row())
    record_id = added["记录编号"]
    updated = store.update(record_id, {**added, "结果": "已成交", "成交价": "920"})
    assert updated["记录编号"] == record_id
    assert NegotiationStore(store.path).rows == [updated]


def test_delete_and_duplicate_ids_are_checked(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row())
    with pytest.raises(ValueError, match="记录编号已存在"):
        store.add(row(商品编号="XY-002"))
    store.delete("XN-001")
    assert store.rows == []
    with pytest.raises(ValueError, match="找不到"):
        store.delete("missing")


def test_followup_rows_only_include_open_due_records(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row(记录编号="XN-1", 询价日期="2026-11-18", 下次跟进日期="2026-11-19"))
    store.add(row(记录编号="XN-2", 结果="待回复", 下次跟进日期="2026-11-22"))
    store.add(row(记录编号="XN-3", 结果="已成交", 成交价="900", 下次跟进日期="2026-11-20"))
    store.add(row(记录编号="XN-4", 结果="未成交", 下次跟进日期="2026-11-20"))
    due = followup_rows(store.rows, "2026-11-20")
    assert [item["记录编号"] for item in due] == ["XN-1"]


def test_summary_calculates_conversion_discount_and_estimated_profit():
    sold = row(记录编号="XN-SOLD", 结果="已成交", 成交价="900", 最低接受价="950")
    pending = row(记录编号="XN-PENDING", 结果="待回复", 买家报价="0", 卖家回价="0", 下次跟进日期="")
    report = summary_rows([normalize_row(sold), normalize_row(pending)])[0]
    assert report["询价数"] == 2
    assert report["成交数"] == 1
    assert report["转化率"] == "50.00%"
    assert report["平均议价幅度"] == "10.00%"
    assert report["成交金额"] == "900.00"
    assert report["估算毛利"] == "282.00"
    assert report["低于底价成交数"] == 1


def test_summary_keeps_different_listing_or_sku_groups_separate():
    first = normalize_row(row(记录编号="XN-1"))
    second = normalize_row(row(记录编号="XN-2", SKU="WHITE-128"))
    third = normalize_row(row(记录编号="XN-3", 商品编号="XY-002"))
    assert len(summary_rows([first, second, third])) == 3


def test_import_csv_is_all_or_nothing_and_rejects_duplicate_existing_ids(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row())
    csv_path = tmp_path / "import.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerow(row(记录编号="XN-NEW", 商品编号="XY-002"))
        writer.writerow(row(记录编号="XN-001", 商品编号="XY-003"))
    before = list(store.rows)
    with pytest.raises(ValueError, match="记录编号重复"):
        store.import_csv(csv_path)
    assert store.rows == before


def test_import_supports_gb18030_and_deterministic_missing_ids(tmp_path):
    csv_path = tmp_path / "gb.csv"
    csv_path.write_bytes("商品编号,商品名称,询价日期,标价,结果\nXY-9,二手相机,2026-11-20,500,待回复\n".encode("gb18030"))
    store = NegotiationStore(tmp_path / "data.json")
    assert store.import_csv(csv_path) == 1
    first_id = store.rows[0]["记录编号"]
    other = NegotiationStore(tmp_path / "other.json")
    assert other.import_csv(csv_path) == 1
    assert other.rows[0]["记录编号"] == first_id


def test_import_rejects_missing_duplicate_headers_and_extra_columns(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    missing = tmp_path / "missing.csv"
    missing.write_text("商品编号,商品名称\nXY-1,手机\n", encoding="utf-8")
    with pytest.raises(ValueError, match="必须包含"):
        store.import_csv(missing)
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text("商品编号,商品名称,询价日期,询价日期\nXY-1,手机,2026-11-20,2026-11-21\n", encoding="utf-8")
    with pytest.raises(ValueError, match="列名不能重复"):
        store.import_csv(duplicate)
    extra = tmp_path / "extra.csv"
    extra.write_text("商品编号,商品名称,询价日期\nXY-1,手机,2026-11-20,unexpected\n", encoding="utf-8")
    with pytest.raises(ValueError, match="列数超过表头"):
        store.import_csv(extra)


def test_formula_safe_export_roundtrips_formula_like_text(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row(买家备注='=HYPERLINK("bad")', 内部备注="@SUM(1,1)"))
    export = tmp_path / "safe.csv"
    store.export_csv(export)
    raw = export.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in raw
    assert "'@SUM" in raw
    restored = NegotiationStore(tmp_path / "restored.json")
    assert restored.import_csv(export) == 1
    assert restored.rows[0]["买家备注"] == '=HYPERLINK("bad")'
    assert restored.rows[0]["内部备注"] == "@SUM(1,1)"


def test_summary_and_followup_exports_are_formula_safe(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row(买家备注="=1+1"))
    assert store.export_followups_csv(tmp_path / "due.csv", "2026-11-21") == 1
    assert store.export_summary_csv(tmp_path / "summary.csv") == 1
    assert "'=1+1" in (tmp_path / "due.csv").read_text(encoding="utf-8-sig")


@pytest.mark.parametrize(
    "value",
    [
        "=1+1", "+SUM(1,1)", "-1+1", "@SUM(1,1)",
        "  =1+1", "\\t=1+1", "\\r=1+1", "\\n=1+1",
        "\\u00a0=1+1", "'=1+1", "'ordinary text",
    ],
)
def test_formula_safe_export_guards_leading_whitespace_and_controls_and_roundtrips(tmp_path, value):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row(买家备注=value))
    export = tmp_path / "formula-safe.csv"
    store.export_csv(export)
    with export.open("r", encoding="utf-8-sig", newline="") as stream:
        exported = next(csv.DictReader(stream))["买家备注"]
    assert exported.startswith("'")
    assert _restore_safe_text(_safe_text(value)) == value

    restored = NegotiationStore(tmp_path / "restored.json")
    assert restored.import_csv(export) == 1
    # normalize_row intentionally trims surrounding whitespace in user-entered fields.
    assert restored.rows[0]["买家备注"] == value.strip()


def test_backup_restore_roundtrip_and_tamper_rejection_preserves_current_data(tmp_path):
    store = NegotiationStore(tmp_path / "data.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    target = NegotiationStore(tmp_path / "target.json")
    target.add(row(记录编号="XN-OLD", 商品编号="XY-OLD"))
    assert target.restore(backup) == 1
    assert target.rows == store.rows
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["商品名称"] = "被篡改"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(target.rows)
    with pytest.raises(ValueError, match="SHA256"):
        target.restore(tampered)
    assert target.rows == before


@pytest.mark.parametrize("payload", [[], {"version": 1, "items": {}}, {"version": 2, "items": []}, {"version": 1, "items": [None]}])
def test_malformed_backup_shapes_are_rejected(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = NegotiationStore(tmp_path / "data.json")
    with pytest.raises(ValueError):
        store.restore(path)


def test_malformed_data_file_shape_is_rejected(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"version": 1, "items": [None]}), encoding="utf-8")
    with pytest.raises(ValueError, match="明细结构无效"):
        NegotiationStore(path)


def test_default_data_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_data_path() == tmp_path / "MainlandBusinessTools" / "xianyu_negotiation_review.json"


def test_product_identity_and_self_test():
    assert PRODUCT == "闲鱼询价转化与议价复盘助手"
    self_test()



def test_import_csv_rejects_oversized_file_before_reading(tmp_path, monkeypatch):
    csv_path = tmp_path / "oversized.csv"
    with csv_path.open("wb") as stream:
        stream.truncate(MAX_IMPORT_BYTES + 1)
    store = NegotiationStore(tmp_path / "data.json")

    def forbidden_open(self, *args, **kwargs):
        raise AssertionError("oversized CSV must be rejected before opening it")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(ValueError, match="超过 20 MB 限制"):
        store.import_csv(csv_path)
    assert store.rows == []
