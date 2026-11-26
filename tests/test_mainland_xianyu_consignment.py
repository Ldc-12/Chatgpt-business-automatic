import csv
import json

import pytest

from src import xianyu_consignment as module


def sample(**overrides):
    row = {
        "记录编号": "CY-001",
        "货主编号": "OWNER-001",
        "货主名称": "货主甲",
        "联系方式备注": "仅作本地联系备注",
        "商品编号/SKU": "SKU-001",
        "商品名称": "二手蓝牙耳机",
        "商品成色/瑕疵": "九成新",
        "收货日期": "2026-11-01",
        "约定上架价(元)": "120",
        "货主约定结算额(元)": "70",
        "当前标价(元)": "120",
        "商品状态": "已售",
        "成交日期": "2026-11-10",
        "实际成交金额(元)": "100",
        "平台实际费用(元)": "1.50",
        "发货运费(元)": "5",
        "包装整备成本(元)": "2",
        "已结算金额(元)": "20",
        "结算期限": "2026-11-20",
        "最后结算日期": "2026-11-12",
        "退回日期": "",
        "备注": "",
    }
    row.update(overrides)
    return row


def test_calculate_consignment_settlement_and_seller_margin():
    result = module.calculate_item(sample())
    assert result["成交净回款(元)"] == "91.50"
    assert result["货主应结算金额(元)"] == "70.00"
    assert result["已结算金额(元)"] == "20.00"
    assert result["待结算金额(元)"] == "50.00"
    assert result["卖家毛利(元)"] == "21.50"
    assert result["回款缺口(元)"] == "0.00"
    assert result["结算状态"] == "部分结算"


def test_negative_margin_exposes_owner_payout_shortfall():
    result = module.calculate_item(sample(**{
        "实际成交金额(元)": "80",
        "货主约定结算额(元)": "75",
        "已结算金额(元)": "0",
        "最后结算日期": "",
        "平台实际费用(元)": "2",
        "发货运费(元)": "10",
        "包装整备成本(元)": "3",
    }))
    assert result["成交净回款(元)"] == "65.00"
    assert result["卖家毛利(元)"] == "-10.00"
    assert result["回款缺口(元)"] == "10.00"
    assert result["结算状态"] == "待结算"


def test_unsold_item_does_not_create_owner_payable():
    result = module.calculate_item(sample(
        **{
            "商品状态": "在售",
            "当前标价(元)": "118",
            "成交日期": "",
            "实际成交金额(元)": "0",
            "已结算金额(元)": "0",
            "结算期限": "",
            "最后结算日期": "",
        }
    ))
    assert result["待结算金额(元)"] == "0.00"
    assert result["卖家毛利(元)"] == "0.00"
    assert result["结算状态"] == "未成交"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"商品状态": "未知状态"}, "内置列表"),
        ({"收货日期": "2026-13-01"}, "YYYY-MM-DD"),
        ({"商品状态": "在售", "当前标价(元)": "0"}, "当前标价"),
        ({"商品状态": "在售", "当前标价(元)": "120", "成交日期": "", "实际成交金额(元)": "100", "已结算金额(元)": "0", "结算期限": "", "最后结算日期": ""}, "只有已售商品"),
        ({"成交日期": "2026-10-31"}, "不能早于收货日期"),
        ({"实际成交金额(元)": "0"}, "必须填写成交日期"),
        ({"已结算金额(元)": "71"}, "不能超过"),
        ({"已结算金额(元)": "10", "最后结算日期": ""}, "必须填写最后结算日期"),
        ({"结算期限": "2026-11-09"}, "不能早于成交日期"),
        ({
            "商品状态": "在售", "当前标价(元)": "120", "成交日期": "",
            "实际成交金额(元)": "0", "已结算金额(元)": "0",
            "结算期限": "", "最后结算日期": "", "退回日期": "2026-11-05",
        }, "只有已退回商品"),
        ({
            "商品状态": "已退回", "成交日期": "", "实际成交金额(元)": "0",
            "已结算金额(元)": "0", "结算期限": "", "最后结算日期": "",
            "退回日期": "",
        }, "必须填写退回日期"),
        ({"货主约定结算额(元)": "-1"}, "不能为负数"),
        ({"实际成交金额(元)": "1e1000"}, "超出支持范围"),
    ],
)
def test_invalid_consignment_records_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_row(sample(**overrides))


def test_owner_summary_groups_by_owner_and_flags_overdue_unsettled_items():
    rows = [
        sample(),
        sample(**{
            "记录编号": "CY-002",
            "商品编号/SKU": "SKU-002",
            "商品名称": "二手键盘",
            "实际成交金额(元)": "150",
            "货主约定结算额(元)": "100",
            "已结算金额(元)": "100",
            "最后结算日期": "2026-11-18",
            "结算期限": "2026-11-19",
        }),
        sample(**{
            "记录编号": "CY-003",
            "货主编号": "OWNER-002",
            "货主名称": "货主乙",
            "商品编号/SKU": "SKU-003",
            "商品名称": "二手显示器",
            "实际成交金额(元)": "200",
            "货主约定结算额(元)": "130",
            "已结算金额(元)": "0",
            "最后结算日期": "",
            "结算期限": "2026-11-21",
        }),
    ]
    report = module.owner_summary(rows, as_of=module.date(2026, 11, 26))
    assert report["OWNER-001"]["商品数"] == 2
    assert report["OWNER-001"]["已售数"] == 2
    assert report["OWNER-001"]["应结算金额(元)"] == "170.00"
    assert report["OWNER-001"]["已结算金额(元)"] == "120.00"
    assert report["OWNER-001"]["待结算金额(元)"] == "50.00"
    assert report["OWNER-001"]["逾期待结算数"] == 1
    assert report["OWNER-002"]["待结算金额(元)"] == "130.00"


def test_owner_id_cannot_be_reused_with_a_different_name_in_summary():
    with pytest.raises(ValueError, match="多个名称"):
        module.owner_summary([
            sample(),
            sample(**{"记录编号": "CY-002", "货主名称": "错误名称"}),
        ])


def test_store_persists_updates_deletes_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "consignments.json"
    store = module.ConsignmentStore(path)
    store.add(sample())
    loaded = module.ConsignmentStore(path)
    assert loaded.rows == store.rows
    changed = dict(loaded.rows[0], **{"已结算金额(元)": "40", "最后结算日期": "2026-11-15"})
    loaded.update("CY-001", changed)
    assert module.calculate_item(loaded.rows[0])["待结算金额(元)"] == "30.00"
    with pytest.raises(ValueError, match="已存在"):
        loaded.add(sample(**{"记录编号": "CY-001", "商品编号/SKU": "SKU-OTHER"}))
    loaded.delete("CY-001")
    assert loaded.rows == []


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    original_name = "=HYPERLINK(\"https://bad.example\",\"click\")"
    store = module.ConsignmentStore(tmp_path / "consignments.json")
    store.add(sample(**{"货主名称": original_name}))
    path = tmp_path / "consignments.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.ConsignmentStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["货主名称"] == original_name


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+SUM(A1:A2)", "'=1+1", "''=1+1", "'普通备注", "普通备注"],
)
def test_csv_roundtrip_preserves_formula_like_text_and_leading_apostrophes(tmp_path, value):
    store = module.ConsignmentStore(tmp_path / "source.json")
    store.add(sample(**{"货主名称": value}))
    path = tmp_path / "export.csv"
    store.export_csv(path)
    imported = module.ConsignmentStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["货主名称"] == value


def test_csv_safety_helpers_preserve_leading_spaces_around_formula():
    original = "  =1+1"
    safe = module._safe_csv_text(original)
    assert safe == "'  =1+1"
    assert module._restore_csv_text(safe) == original


def test_csv_import_accepts_gb18030_encoding(tmp_path):
    store = module.ConsignmentStore(tmp_path / "store.json")
    path = tmp_path / "gb18030.csv"
    with path.open("w", encoding="gb18030", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"货主名称": "广州寄售货主", "备注": "中文备注"}))
    assert store.import_csv(path) == 1
    assert store.rows[0]["货主名称"] == "广州寄售货主"
    assert store.rows[0]["备注"] == "中文备注"

def test_csv_import_rejects_invalid_rows_and_duplicate_records_atomically(tmp_path):
    store = module.ConsignmentStore(tmp_path / "consignments.json")
    store.add(sample())
    before = list(store.rows)
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"已结算金额(元)": "90"}))
    with pytest.raises(ValueError, match="不能超过"):
        store.import_csv(bad)
    assert store.rows == before

    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在"):
        store.import_csv(duplicate)
    assert store.rows == before


def test_backup_restore_checks_sha256_before_replacing_data(tmp_path):
    source = module.ConsignmentStore(tmp_path / "source.json")
    source.add(sample())
    backup = tmp_path / "backup.json"
    source.backup(backup)
    target = module.ConsignmentStore(tmp_path / "target.json")
    target.add(sample(**{"记录编号": "CY-OLD", "商品编号/SKU": "SKU-OLD"}))
    target.restore(backup)
    assert target.rows == source.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["records"][0]["货主约定结算额(元)"] = "999"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(target.rows)
    with pytest.raises(ValueError, match="SHA256"):
        target.restore(tampered)
    assert target.rows == before


def test_failed_atomic_replace_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "consignments.json"
    store = module.ConsignmentStore(path)
    store.add(sample())
    original = path.read_bytes()
    monkeypatch.setattr(
        module.os, "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        store.add(sample(**{"记录编号": "CY-002", "商品编号/SKU": "SKU-002"}))
    assert path.read_bytes() == original
    assert len(store.rows) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_self_test_runs_without_gui():
    module.self_test()
