import csv
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "apps" / "门店日结与收银差异核对助手.py"
SPEC = importlib.util.spec_from_file_location("store_cash_close", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(**changes):
    row = {
        "营业日期": "2026-11-16", "门店编号": "S001", "门店名称": "测试门店",
        "班次": "早班", "收银台编号": "POS01", "收银员": "张三",
        "备用金期初": "200", "现金销售": "1000", "微信收款": "500",
        "支付宝收款": "300", "银行卡收款": "200", "其他收款": "0",
        "现金退款": "50", "电子退款": "20", "现金支出": "30",
        "实际现金盘点": "1115", "POS销售合计": "1980", "POS退款合计": "70",
        "复核人": "", "差异处理说明": "", "备注": "正常",
        "状态": "待复核", "封账时间": "",
    }
    row.update(changes)
    return row


def test_calculates_cash_and_pos_differences_exactly():
    values = MODULE.calculate(sample())
    assert values["应有现金"] == "1120.00"
    assert values["现金差异"] == "-5.00"
    assert values["渠道净收"] == "1930.00"
    assert values["POS净收"] == "1910.00"
    assert values["POS差异"] == "20.00"
    assert MODULE.has_variance(values)


def test_decimal_rounding_and_invalid_amounts():
    assert MODULE.decimal_value("12.345", "金额") == "12.35"
    for value in ("NaN", "Infinity", "-1", "not-money"):
        try:
            MODULE.decimal_value(value, "金额")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid amount accepted: {value}")


def test_add_persists_and_duplicate_shift_register_is_rejected_atomically(tmp_path):
    path = tmp_path / "cash.json"
    store = MODULE.CashCloseStore(path)
    record_id = store.add(sample())
    loaded = MODULE.CashCloseStore(path)
    assert loaded.rows[0]["记录编号"] == record_id
    before = path.read_bytes()
    try:
        store.add(sample(**{"收银员": "李四"}))
    except ValueError as exc:
        assert "已存在日结记录" in str(exc)
    else:
        raise AssertionError("duplicate shift/register close accepted")
    assert path.read_bytes() == before
    assert len(store.rows) == 1


def test_review_requires_explanation_for_variance_then_close_and_reopen(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    record_id = store.add(sample())
    try:
        store.close(record_id)
    except ValueError as exc:
        assert "必须先完成复核" in str(exc)
    else:
        raise AssertionError("unreviewed close accepted")
    try:
        store.review(record_id, "店长")
    except ValueError as exc:
        assert "差异处理说明" in str(exc)
    else:
        raise AssertionError("variance reviewed without explanation")
    store.review(record_id, "店长", "现金短款 5 元，POS 差异 20 元，已核对退款凭证")
    store.close(record_id)
    assert store.rows[0]["状态"] == "已封账"
    assert store.rows[0]["封账时间"]
    for operation in (lambda: store.update(record_id, sample()), lambda: store.delete(record_id)):
        try:
            operation()
        except ValueError as exc:
            assert "已封账" in str(exc)
        else:
            raise AssertionError("closed record mutation accepted")
    try:
        store.reopen(record_id, "错")
    except ValueError as exc:
        assert "至少 4 个字符" in str(exc)
    else:
        raise AssertionError("short reopen reason accepted")
    store.reopen(record_id, "补录退款凭证并重新核对", "店长")
    assert store.rows[0]["状态"] == "待复核"
    assert store.rows[0]["封账时间"] == ""
    assert store.events[-1]["action"] == "重新开账"


def test_update_resets_review_and_preserves_record_id(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    record_id = store.add(sample(**{"现金销售": "1000", "实际现金盘点": "1120"}))
    store.review(record_id, "店长", "POS 差异已核对")
    store.update(record_id, sample(**{"现金销售": "1100", "实际现金盘点": "1220"}))
    assert store.rows[0]["记录编号"] == record_id
    assert store.rows[0]["现金销售"] == "1100.00"
    assert store.rows[0]["状态"] == "待复核"
    assert store.rows[0]["复核人"] == ""


def test_summary_groups_by_date_and_store(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    store.add(sample())
    store.add(sample(**{
        "营业日期": "2026-11-16", "收银台编号": "POS02", "收银员": "李四",
        "现金销售": "500", "微信收款": "0", "支付宝收款": "0",
        "银行卡收款": "0", "其他收款": "0", "现金退款": "0",
        "电子退款": "0", "现金支出": "0", "实际现金盘点": "700",
        "POS销售合计": "", "POS退款合计": "",
    }))
    store.add(sample(**{
        "营业日期": "2026-11-15", "门店编号": "S002", "门店名称": "另一家店",
        "收银台编号": "POS01", "现金销售": "100",
    }))
    summary = store.summary_by_store("2026-11-16")
    assert len(summary) == 1
    assert summary[0]["班次数"] == 2
    assert summary[0]["渠道净收"] == "2430.00"
    assert summary[0]["现金差异"] == "-5.00"


def test_csv_roundtrip_is_utf8_bom_formula_safe_and_validates_derived_values(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    store.add(sample(**{"备注": "=HYPERLINK(""x"")"}))
    export = tmp_path / "cash.csv"
    store.export_csv(export)
    assert export.read_bytes().startswith(b"\xef\xbb\xbf")
    text = export.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in text
    imported = MODULE.CashCloseStore(tmp_path / "imported.json")
    assert imported.import_csv(export) == 1
    assert imported.rows[0]["备注"].startswith("'=")
    rows = list(csv.DictReader(text.splitlines()))
    rows[0]["现金差异"] = "999.00"
    bad = tmp_path / "tampered.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        MODULE.CashCloseStore(tmp_path / "empty.json").import_csv(bad)
    except ValueError as exc:
        assert "计算字段" in str(exc)
    else:
        raise AssertionError("tampered derived CSV accepted")


def test_csv_batch_import_is_all_or_nothing(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    source = tmp_path / "bad.csv"
    fields = MODULE.FIELDS
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(sample())
        writer.writerow(sample(**{"门店编号": "", "收银台编号": "POS02"}))
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid batch CSV accepted")
    assert store.rows == []
    assert not store.path.exists()


def test_backup_restore_validates_envelope_and_audit_chain(tmp_path):
    path = tmp_path / "cash.json"
    store = MODULE.CashCloseStore(path)
    store.add(sample())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(sample(**{"收银台编号": "POS02"}))
    store.restore(backup)
    assert len(store.rows) == 1
    assert store.events[-1]["action"] == "恢复"
    before = path.read_bytes()
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["操作日志"][0]["reason"] = "tampered"
    body = {key: value for key, value in payload.items() if key != "SHA256"}
    payload["SHA256"] = __import__("hashlib").sha256(MODULE.canonical(body)).hexdigest()
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        store.restore(corrupt)
    except ValueError as exc:
        assert "操作日志 SHA256" in str(exc)
    else:
        raise AssertionError("tampered audit chain accepted")
    assert path.read_bytes() == before


def test_failed_atomic_write_does_not_change_memory_or_disk(tmp_path, monkeypatch):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    record_id = store.add(sample())
    before = store.path.read_bytes()
    rows = list(store.rows)
    def fail_write(path, data):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(MODULE, "atomic_write", fail_write)
    try:
        store.update(record_id, sample(**{"现金销售": "1200"}))
    except OSError:
        pass
    else:
        raise AssertionError("simulated write failure ignored")
    assert store.path.read_bytes() == before
    assert store.rows == rows


def test_oversized_local_file_is_rejected_without_modification(tmp_path, monkeypatch):
    path = tmp_path / "cash.json"
    path.write_text("{}", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(MODULE, "MAX_BACKUP_BYTES", 1)
    try:
        MODULE.CashCloseStore(path)
    except ValueError as exc:
        assert "100 MiB" in str(exc)
    else:
        raise AssertionError("oversized local file accepted")
    assert path.read_bytes() == before


def test_audit_chain_detects_event_reordering():
    events = MODULE.append_event([], "新增", "A")
    events = MODULE.append_event(events, "复核", "A")
    altered = list(reversed(events))
    try:
        MODULE.verify_audit(altered)
    except ValueError:
        pass
    else:
        raise AssertionError("reordered audit events accepted")


def test_ui_exposes_review_close_reopen_and_summary_actions():
    source = PATH.read_text(encoding="utf-8")
    for action in ("复核", "封账", "重新开账", "门店汇总"):
        assert action in source
    assert "self.store.review" in source
    assert "self.store.close" in source
    assert "self.store.reopen" in source


def test_self_test_runs_without_gui_or_license():
    MODULE.self_test()


def test_summary_csv_keeps_negative_variances_numeric(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    store.add(sample())
    output = tmp_path / "summary.csv"
    store.export_summary_csv(output, "2026-11-16")
    rows = list(csv.DictReader(output.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["现金差异"] == "-5.00"
    assert not rows[0]["现金差异"].startswith("'")


def test_rejects_extreme_amounts_and_unsafe_record_ids():
    for value in ("1e999999", "1000000000000", "9" * 40):
        try:
            MODULE.decimal_value(value, "金额")
        except ValueError:
            pass
        else:
            raise AssertionError(f"extreme amount accepted: {value}")
    try:
        MODULE.normalize(sample(**{"记录编号": "../unsafe"}))
    except ValueError as exc:
        assert "记录编号" in str(exc)
    else:
        raise AssertionError("unsafe record ID accepted")


def test_gui_uses_explicit_simpledialog_import_for_all_prompts():
    source = PATH.read_text(encoding="utf-8")
    assert "from tkinter import filedialog, messagebox, simpledialog, ttk" in source
    assert "tk.simpledialog" not in source
    assert source.count("simpledialog.askstring") >= 4


def test_audit_export_is_bom_formula_safe_and_keeps_verifiable_hashes(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    store.add(sample(), actor="=HYPERLINK(\"https://example.invalid\")")
    output = tmp_path / "audit.csv"
    store.export_audit_csv(output)
    assert output.read_bytes().startswith(b"\\xef\\xbb\\xbf")
    rows = list(csv.DictReader(output.open(encoding="utf-8-sig", newline="")))
    assert len(rows) == 1
    assert rows[0]["操作人"].startswith("'=HYPERLINK(")
    assert rows[0]["本次摘要"] == store.events[0]["hash"]
    summary = store.audit_summary()
    assert summary["事件数"] == 1
    assert summary["最后操作"] == "新增"
    assert summary["最新摘要"] == store.events[0]["hash"]


def test_audit_export_refuses_corrupted_chain_without_overwriting_target(tmp_path):
    store = MODULE.CashCloseStore(tmp_path / "cash.json")
    store.add(sample())
    store.events[0]["reason"] = "tampered"
    output = tmp_path / "audit.csv"
    output.write_text("keep-existing-report", encoding="utf-8")
    try:
        store.export_audit_csv(output)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("corrupted audit chain was exported")
    assert output.read_text(encoding="utf-8") == "keep-existing-report"


def test_audit_ui_exposes_integrity_check_and_log_export():
    source = PATH.read_text(encoding="utf-8")
    assert "校验日志" in source
    assert "导出日志" in source
    assert "self.store.audit_summary()" in source
    assert "self.store.export_audit_csv(path)" in source
