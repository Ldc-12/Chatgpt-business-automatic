import csv
import json
from datetime import date, timedelta

import pytest

from src import xianyu_listing as module


def sample(**overrides):
    today = date.today()
    row = {
        "商品编号": "XY-L-001",
        "商品名称": "二手测试手机",
        "品类": "手机数码",
        "成色": "9成新",
        "SKU/库存位": "A-01",
        "标价(元)": "680",
        "最低接受价(元)": "500",
        "库存数量": "2",
        "上架状态": "已上架",
        "计划上架日期": "",
        "实际上架日期": (today - timedelta(days=10)).isoformat(),
        "最后刷新日期": (today - timedelta(days=7)).isoformat(),
        "刷新间隔(天)": "7",
        "商品链接": "",
        "瑕疵/配件说明": "含充电线，边框轻微划痕",
        "备注": "卖家内部备注",
    }
    row.update(overrides)
    return row


def test_refresh_due_boundary_and_status_filtering():
    today = date.today()
    row = sample()
    assert module.refresh_due_info(row, as_of=today - timedelta(days=1))["due"] is False
    assert module.refresh_due_info(row, as_of=today)["due"] is True
    paused = dict(row, **{"上架状态": "已暂停"})
    assert module.refresh_due_info(paused, as_of=today)["next_refresh_date"] == ""
    no_date = dict(row, **{"最后刷新日期": "", "实际上架日期": ""})
    assert module.refresh_due_info(no_date, as_of=today)["due"] is False


def test_summary_counts_status_inventory_and_due_items():
    today = date.today()
    rows = [sample(), sample(**{
        "商品编号": "XY-L-002", "商品名称": "待上架键盘",
        "上架状态": "待上架", "库存数量": "1", "实际上架日期": "", "最后刷新日期": "",
    })]
    result = module.listing_summary(rows, as_of=today)
    assert result["商品总数"] == 2
    assert result["状态数量"]["已上架"] == 1
    assert result["状态数量"]["待上架"] == 1
    assert result["库存总量"] == 3
    assert result["待刷新数量"] == 1
    assert result["待刷新商品"][0]["商品编号"] == "XY-L-001"
    assert result["在售标价库存额(元)"] == "1360.00"


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"品类": "未知品类"}, "内置列表"),
        ({"成色": "五成新"}, "内置列表"),
        ({"上架状态": "已发布"}, "内置列表"),
        ({"标价(元)": "0"}, "大于 0"),
        ({"最低接受价(元)": "700"}, "不能高于标价"),
        ({"最低接受价(元)": "-1"}, "不能为负数"),
        ({"库存数量": "-1"}, "0–100000"),
        ({"库存数量": "1.5"}, "整数"),
        ({"刷新间隔(天)": "0"}, "1–365"),
        ({"实际上架日期": "2099-01-01"}, "不能晚于今天"),
        ({"商品链接": "javascript:alert(1)"}, "http/https"),
    ],
)
def test_invalid_listing_fields_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        module.normalize_row(sample(**overrides))


def test_listing_store_persists_updates_deletes_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "listing.json"
    store = module.ListingStore(path)
    store.add(sample())
    loaded = module.ListingStore(path)
    assert loaded.rows == store.rows
    changed = dict(loaded.rows[0], **{"标价(元)": "700"})
    loaded.update("XY-L-001", changed)
    assert loaded.rows[0]["标价(元)"] == "700.00"
    with pytest.raises(ValueError, match="已存在"):
        loaded.add(sample(**{"商品名称": "重复编号"}))
    loaded.delete("XY-L-001")
    assert loaded.rows == []


def test_status_transitions_record_publish_date_and_lock_sold_items(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    draft = sample(**{
        "上架状态": "草稿", "实际上架日期": "", "最后刷新日期": "",
    })
    store.add(draft)
    store.transition_status("XY-L-001", "待上架")
    store.transition_status("XY-L-001", "已上架")
    assert store.rows[0]["实际上架日期"] == date.today().isoformat()
    store.transition_status("XY-L-001", "已售出")
    with pytest.raises(ValueError, match="不允许"):
        store.transition_status("XY-L-001", "已上架")
    with pytest.raises(ValueError, match="不允许"):
        store.update("XY-L-001", dict(store.rows[0], **{"上架状态": "已上架"}))


def test_mark_refreshed_requires_active_listing(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    store.add(sample())
    store.mark_refreshed("XY-L-001")
    assert store.rows[0]["最后刷新日期"] == date.today().isoformat()
    paused = dict(store.rows[0], **{"上架状态": "已暂停"})
    store.update("XY-L-001", paused)
    with pytest.raises(ValueError, match="只有已上架"):
        store.mark_refreshed("XY-L-001")


def test_csv_roundtrip_uses_bom_and_formula_safe_text(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    store.add(sample(**{"商品名称": "=HYPERLINK(\"https://bad.example\",\"click\")"}))
    path = tmp_path / "listing.csv"
    store.export_csv(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.ListingStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["商品名称"].startswith("'=")


def test_csv_import_rejects_invalid_rows_atomically(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    store.add(sample())
    before = list(store.rows)
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample(**{"最低接受价(元)": "999"}))
    with pytest.raises(ValueError, match="不能高于标价"):
        store.import_csv(path)
    assert store.rows == before


def test_csv_import_rejects_existing_duplicate_ids(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    store.add(sample())
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(sample())
    with pytest.raises(ValueError, match="已存在商品编号"):
        store.import_csv(duplicate)


def test_backup_restore_checks_sha256_before_replacing_data(tmp_path):
    store = module.ListingStore(tmp_path / "listing.json")
    store.add(sample())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    restored = module.ListingStore(tmp_path / "restored.json")
    restored.restore(backup)
    assert restored.rows == store.rows

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["标价(元)"] = "999"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = list(restored.rows)
    with pytest.raises(ValueError, match="SHA256"):
        restored.restore(backup)
    assert restored.rows == before


def test_listing_copy_never_discloses_floor_or_private_notes():
    text = module.generate_listing_text(sample())
    assert "二手测试手机" in text
    assert "¥680.00" in text
    assert "500" not in text
    assert "卖家内部备注" not in text
    assert "含充电线" in text


def test_default_data_path_is_local_and_uses_localappdata_when_available(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    assert module.default_data_path().as_posix().endswith(
        "MainlandBusinessTools/xianyu_listing_ledger.json"
    )


def test_self_test_runs_without_gui(capsys):
    module.self_test()
    assert "SELF_TEST_OK" in capsys.readouterr().out
