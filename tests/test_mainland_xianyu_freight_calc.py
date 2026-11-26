import csv
import json

import pytest

from src import xianyu_freight_calc as module


def rate(**changes):
    row = {
        "规则编号": "FR-001", "承运商": "中通快递", "目的地区关键词": "全国",
        "抛重系数(cm³/kg)": "6000", "首重(kg)": "1", "首费(元)": "8",
        "续重单位(kg)": "0.5", "续费(元)": "2", "附加费(元)": "1",
        "有效起始日期": "2026-01-01", "有效结束日期": "2026-12-31", "备注": "测试费率",
    }
    row.update(changes)
    return row


def package(**changes):
    row = {
        "订单编号": "XY-001", "商品/SKU": "测试商品", "承运商": "中通快递",
        "目的地区": "广东省广州市", "实重(kg)": "2", "长(cm)": "40",
        "宽(cm)": "30", "高(cm)": "20", "试算日期": "2026-11-26",
    }
    row.update(changes)
    return row


def test_volumetric_weight_and_step_rounding_are_calculated_with_decimal():
    result = module.calculate_freight(package(), rate())
    assert result["体积重(kg)"] == "4"
    assert result["计费重量(kg)"] == "4"
    assert result["预估运费(元)"] == "21.00"


def test_actual_weight_wins_when_heavier_than_volumetric_weight():
    result = module.calculate_freight(package(**{"实重(kg)": "8"}), rate())
    assert result["体积重(kg)"] == "4"
    assert result["计费重量(kg)"] == "8"
    assert result["预估运费(元)"] == "37.00"


def test_region_specific_rate_beats_nationwide_rule():
    national = rate()
    local = rate(**{"规则编号": "FR-GD", "目的地区关键词": "广东", "首费(元)": "5"})
    selected = module.match_rate([national, local], "中通快递", "广东省广州市", on_date=module.date(2026, 11, 26))
    assert selected["规则编号"] == "FR-GD"


def test_ambiguous_same_specificity_rules_are_rejected():
    rules = [rate(**{"规则编号": "FR-A", "目的地区关键词": "广东"}), rate(**{"规则编号": "FR-B", "目的地区关键词": "广东"})]
    with pytest.raises(ValueError, match="匹配不唯一"):
        module.match_rate(rules, "中通快递", "广东省广州市", on_date=module.date(2026, 11, 26))


def test_rule_validity_window_is_enforced():
    with pytest.raises(ValueError, match="没有匹配"):
        module.match_rate([rate(**{"有效结束日期": "2026-10-31"})], "中通快递", "广东省广州市", on_date=module.date(2026, 11, 26))


@pytest.mark.parametrize("changes", [
    {"实重(kg)": "0"}, {"长(cm)": "-1"}, {"宽(cm)": "0"}, {"高(cm)": "NaN"},
])
def test_invalid_package_dimensions_and_weights_are_rejected(changes):
    with pytest.raises(ValueError):
        module.calculate_freight(package(**changes), rate())


def test_invalid_rate_steps_and_negative_fees_are_rejected():
    with pytest.raises(ValueError, match="续重单位"):
        module.normalize_rate(rate(**{"续重单位(kg)": "0"}))
    with pytest.raises(ValueError, match="不能为负数"):
        module.normalize_rate(rate(**{"续费(元)": "-1"}))


def test_store_persists_rates_quotes_and_actual_freight(tmp_path):
    path = tmp_path / "data.json"
    store = module.FreightStore(path)
    store.add_rate(rate())
    row = store.quote(package())
    store.update_actual(row["试算编号"], "23.5")
    loaded = module.FreightStore(path)
    assert loaded.rates == store.rates
    assert loaded.rows == store.rows
    assert loaded.rows[0]["运费差额(元)"] == "2.50"


def test_csv_roundtrip_is_utf8_bom_and_formula_safe(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    store.add_rate(rate())
    note = '=HYPERLINK("https://bad.example","click")'
    row = store.quote(package(**{"备注": note}))
    path = tmp_path / "quotes.csv"
    assert store.export_csv(path) == 1
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in raw.decode("utf-8-sig")
    imported = module.FreightStore(tmp_path / "imported.json")
    assert imported.import_csv(path) == 1
    assert imported.rows[0]["备注"] == note
    assert imported.rows[0]["试算编号"] == row["试算编号"]


def test_rate_csv_roundtrip_and_duplicate_import_rejection(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    store.add_rate(rate())
    path = tmp_path / "rates.csv"
    assert store.export_rate_csv(path) == 1
    imported = module.FreightStore(tmp_path / "imported.json")
    assert imported.import_rate_csv(path) == 1
    assert imported.rates == store.rates
    before = imported.path.read_bytes()
    with pytest.raises(ValueError, match="重复"):
        imported.import_rate_csv(path)
    assert imported.path.read_bytes() == before


def test_invalid_quote_csv_batch_does_not_partially_write(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    store.add_rate(rate())
    first = store.quote(package())
    before = store.path.read_bytes()
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.QUOTE_FIELDS)
        writer.writeheader()
        writer.writerow({**first, "试算编号": "FQ-002", "实重(kg)": "-1"})
    with pytest.raises(ValueError):
        store.import_csv(bad)
    assert store.path.read_bytes() == before


def test_backup_restore_checks_sha256_and_keeps_current_data_on_tamper(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    store.add_rate(rate())
    store.quote(package())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    restored = module.FreightStore(tmp_path / "restored.json")
    assert restored.restore(backup) == 1
    assert restored.rates == store.rates and restored.rows == store.rows
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["items"][0]["备注"] = "tampered"
    backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = restored.path.read_bytes()
    with pytest.raises(ValueError, match="SHA256"):
        restored.restore(backup)
    assert restored.path.read_bytes() == before


def test_summary_uses_only_entered_actual_freight(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    store.add_rate(rate())
    first = store.quote(package())
    store.quote(package(**{"订单编号": "XY-002", "试算编号": "FQ-002"}))
    store.update_actual(first["试算编号"], "23")
    report = module.freight_summary(store.rows)
    assert report["试算总数"] == 2
    assert report["已录实际运费单数"] == 1
    assert report["累计预估运费(元)"] == "42.00"
    assert report["累计实际运费(元)"] == "23.00"


def test_self_test_uses_temporary_local_data(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "default_data_path", lambda: tmp_path / "unused.json")
    module.self_test()
    assert not (tmp_path / "unused.json").exists()


def test_csv_roundtrip_preserves_literal_leading_apostrophe_before_formula():
    original = "'=1+1"
    exported = module._safe_text(original)
    assert exported == "''=1+1"
    assert module._restore_safe_text(exported) == original
    formula = "=1+1"
    assert module._restore_safe_text(module._safe_text(formula)) == formula


def test_quote_import_rejects_unknown_carrier_and_invalid_encoding(tmp_path):
    store = module.FreightStore(tmp_path / "data.json")
    bad = tmp_path / "unknown-carrier.csv"
    row = {field: "" for field in module.QUOTE_FIELDS}
    row.update({
        "试算编号": "FQ-UNKNOWN", "订单编号": "XY-001", "承运商": "未知快递",
        "目的地区": "广东省广州市", "费率规则编号": "FR-001", "实重(kg)": "1",
        "长(cm)": "10", "宽(cm)": "10", "高(cm)": "10",
        "抛重系数(cm³/kg)": "6000", "首重(kg)": "1", "首费(元)": "8",
        "续重单位(kg)": "0.5", "续费(元)": "2", "附加费(元)": "0",
        "体积重(kg)": "0.167", "计费重量(kg)": "1", "预估运费(元)": "8",
        "试算日期": "2026-11-26",
    })
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.QUOTE_FIELDS)
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(ValueError, match="承运商"):
        store.import_csv(bad)
    invalid = tmp_path / "invalid.csv"
    invalid.write_bytes(b"\x81\x81\x81")
    with pytest.raises(ValueError, match="编码"):
        store.import_csv(invalid)
