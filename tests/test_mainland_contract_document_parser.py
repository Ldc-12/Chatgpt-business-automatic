import csv
import importlib.util
from pathlib import Path

import pytest
from docx import Document
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from src.contract_document_parser import (
    CONTRACT_FIELDS,
    REQUIRED_FIELDS,
    REVIEW_FIELDS,
    parse_contract_document,
    read_contract_text,
    write_draft_csv,
)
from src.contract_rules import RULESET_VERSION, review_contract_text

APP_PATH = Path(__file__).resolve().parents[1] / "apps" / "合同台账与到期提醒助手.py"
SPEC = importlib.util.spec_from_file_location("contract_ledger_for_document_tests", APP_PATH)
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


def contract_text(include_all=True):
    lines = [
        "合同编号：HT-2026-001",
        "合同名称：办公设备采购合同",
        "甲方：广州甲方有限公司",
        "乙方：广州乙方有限公司",
        "签订日期：2026年1月2日",
        "生效日期：2026-01-03",
        "到期日期：2026/12/31",
        "合同金额：人民币 12,345.67 元",
    ]
    if include_all:
        lines.extend([
            "付款方式：按月结算，验收后付款。",
            "交付与验收：货物交付后进行验收。",
            "违约责任：逾期付款按约定承担违约金。",
            "争议解决：协商不成提交仲裁。",
            "发票：乙方应开具发票。",
            "质保：提供一年质保，另收保证金，质保期满后30日内退还。",
        ])
    return "\n".join(lines)


def test_txt_extraction_normalizes_fields_and_reports_clause_checks(tmp_path):
    path = tmp_path / "contract.txt"
    path.write_text(contract_text(), encoding="utf-8")
    result = parse_contract_document(path)
    assert result["合同编号"] == "HT-2026-001"
    assert result["合同名称"] == "办公设备采购合同"
    assert result["甲方/客户"] == "广州甲方有限公司"
    assert result["乙方/供应商"] == "广州乙方有限公司"
    assert result["签订日期"] == "2026-01-02"
    assert result["生效日期"] == "2026-01-03"
    assert result["到期日期"] == "2026-12-31"
    assert result["合同金额"] == "12345.67"
    assert result["识别完整度"] == "6/6（100%）"
    assert result["待补齐字段"] == ""
    assert "未检出" not in result["规则提示"]


def test_missing_fields_and_missing_clause_keywords_are_explicit(tmp_path):
    path = tmp_path / "partial.txt"
    path.write_text("合同名称：临时服务合同\n合同期限：自2026年2月1日起至2026年8月31日止", encoding="utf-8")
    result = parse_contract_document(path)
    assert result["合同名称"] == "临时服务合同"
    assert result["生效日期"] == "2026-02-01"
    assert result["到期日期"] == "2026-08-31"
    assert "合同编号" in result["待补齐字段"]
    assert "合同金额" in result["待补齐字段"]
    assert "付款与结算" in result["规则提示"]
    assert "违约责任" in result["规则提示"]


def test_docx_extraction_reads_paragraphs_and_tables(tmp_path):
    path = tmp_path / "contract.docx"
    document = Document()
    document.add_paragraph("合同编号：DOCX-001")
    document.add_paragraph("合同名称：办公装修合同")
    document.add_paragraph("甲方：业主公司")
    document.add_paragraph("乙方：施工公司")
    table = document.add_table(rows=0, cols=2)
    for label, value in [
        ("签订日期", "2026年3月1日"),
        ("生效日期", "2026年3月2日"),
        ("到期日期", "2026年9月30日"),
        ("合同金额", "88,000.00元"),
    ]:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    document.save(path)
    result = parse_contract_document(path)
    assert result["合同编号"] == "DOCX-001"
    assert result["合同名称"] == "办公装修合同"
    assert result["甲方/客户"] == "业主公司"
    assert result["乙方/供应商"] == "施工公司"
    assert result["签订日期"] == "2026-03-01"
    assert result["合同金额"] == "88000.00"


def test_pdf_extraction_reads_searchable_text(tmp_path):
    path = tmp_path / "contract.pdf"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass
    pdf = canvas.Canvas(str(path))
    pdf.setFont("STSong-Light", 11)
    for y, line in zip(
        (780, 760, 740, 720, 700, 680, 660, 640),
        (
            "合同编号：PDF-001",
            "合同名称：软件服务合同",
            "甲方：甲方公司",
            "乙方：乙方公司",
            "签订日期：2026年4月1日",
            "生效日期：2026年4月2日",
            "到期日期：2027年4月1日",
            "合同金额：人民币 5000.00 元",
        ),
    ):
        pdf.drawString(40, y, line)
    pdf.save()
    text = read_contract_text(path)
    assert "PDF-001" in text
    result = parse_contract_document(path)
    assert result["合同编号"] == "PDF-001"
    assert result["合同金额"] == "5000.00"


def test_scanned_or_empty_pdf_is_not_misrepresented_as_recognized(tmp_path):
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.showPage()
    pdf.save()
    with pytest.raises(ValueError, match="扫描版 PDF 暂不支持 OCR"):
        parse_contract_document(path)


def test_unsupported_or_oversized_file_is_rejected(tmp_path, monkeypatch):
    unsupported = tmp_path / "contract.xls"
    unsupported.write_text("not supported", encoding="utf-8")
    with pytest.raises(ValueError, match="仅支持"):
        read_contract_text(unsupported)
    oversized = tmp_path / "large.txt"
    oversized.write_text("12345", encoding="utf-8")
    monkeypatch.setattr("src.contract_document_parser.MAX_FILE_BYTES", 4)
    with pytest.raises(ValueError, match="50 MiB 安全上限"):
        read_contract_text(oversized)


def test_amount_with_more_than_two_decimal_places_is_not_truncated(tmp_path):
    path = tmp_path / "bad-amount.txt"
    path.write_text("合同金额：12,345.678元", encoding="utf-8")
    result = parse_contract_document(path)
    assert result["合同金额"] == ""
    assert "合同金额" in result["待补齐字段"]


def test_invalid_date_is_reported_instead_of_silently_normalized(tmp_path):
    path = tmp_path / "bad-date.txt"
    path.write_text("签订日期：2026年2月30日", encoding="utf-8")
    result = parse_contract_document(path)
    assert result["签订日期"] == ""
    assert "日期格式或日期值无法识别" in result["规则提示"]


def test_batch_draft_csv_is_utf8_bom_and_contains_review_columns(tmp_path):
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text(contract_text(), encoding="utf-8")
    second.write_text("合同名称：第二份合同", encoding="utf-8")
    output = tmp_path / "draft.csv"
    results = write_draft_csv([first, second], output)
    assert len(results) == 2
    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert set(CONTRACT_FIELDS + REVIEW_FIELDS).issubset(reader.fieldnames)
        rows = list(reader)
    assert rows[0]["来源文件"] == "one.txt"
    assert rows[1]["来源文件"] == "two.txt"
    assert rows[1]["待补齐字段"]


def test_batch_failure_does_not_overwrite_existing_draft(tmp_path):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.bin"
    good.write_text(contract_text(), encoding="utf-8")
    bad.write_bytes(b"not a supported document")
    output = tmp_path / "draft.csv"
    output.write_text("keep existing content", encoding="utf-8")
    with pytest.raises(ValueError):
        write_draft_csv([good, bad], output)
    assert output.read_text(encoding="utf-8") == "keep existing content"


def test_review_csv_can_be_completed_then_imported_and_blank_amount_is_rejected(tmp_path):
    source = tmp_path / "partial.txt"
    source.write_text("合同名称：需要补齐的合同", encoding="utf-8")
    draft = tmp_path / "draft.csv"
    write_draft_csv([source], draft)
    with draft.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    rows[0].update({
        "合同编号": "MANUAL-001",
        "签订日期": "2026-01-01",
        "生效日期": "2026-01-02",
        "到期日期": "2026-12-31",
        "合同金额": "0.00",
    })
    with draft.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    store = APP.ContractStore(tmp_path / "contracts.json")
    assert store.import_csv(draft) == 1
    assert store.rows[0]["合同金额"] == "0.00"

    blank_amount = dict(store.rows[0])
    blank_amount["合同编号"] = "MANUAL-002"
    blank_amount["合同金额"] = ""
    with pytest.raises(ValueError, match="合同金额不能为空"):
        APP.normalize(blank_amount)


def test_review_report_has_versioned_risk_fields_and_traceable_detail(tmp_path):
    source = tmp_path / "review.txt"
    source.write_text(contract_text(), encoding="utf-8")
    result = parse_contract_document(source)
    assert result["规则版本"] == RULESET_VERSION
    assert result["风险等级"] in ("中", "低", "无")
    assert int(result["风险命中数"]) >= 0
    assert isinstance(__import__("json").loads(result["风险明细"]), list)
    assert set(REVIEW_FIELDS).issubset(result)


def test_rule_engine_detects_conflicting_total_amounts_with_evidence():
    findings = review_contract_text(
        "合同金额：人民币 10000.00 元\n补充协议约定合同总价：12000.00 元"
    )
    item = next(item for item in findings if item["规则编号"] == "TOTAL_AMOUNT_CONFLICT")
    assert item["等级"] == "高"
    assert "10000.00" in item["风险说明"] and "12000.00" in item["风险说明"]
    assert "第1行" in item["证据摘录"] and "第2行" in item["证据摘录"]


def test_rule_engine_checks_payment_percentage_totals():
    over = review_contract_text("付款安排：签约后支付30%，交付后支付50%，验收后支付30%。")
    item = next(item for item in over if item["规则编号"] == "PAYMENT_PERCENT_TOTAL_OVER_100")
    assert item["等级"] == "高"
    assert "110%" in item["风险说明"]

    under = review_contract_text("付款安排：签约后支付30%，交付后支付50%。")
    item = next(item for item in under if item["规则编号"] == "PAYMENT_PERCENT_TOTAL_UNDER_100")
    assert item["等级"] == "中"
    assert "80%" in item["风险说明"]


def test_rule_engine_detects_conflicting_labeled_dates():
    findings = review_contract_text(
        "生效日期：2026-01-01\n合同生效日期：2026-02-01\n到期日期：2026-12-31"
    )
    item = next(item for item in findings if item["规则编号"] == "生效日期_CONFLICT")
    assert item["等级"] == "中"
    assert "2026-01-01" in item["风险说明"]
    assert "2026-02-01" in item["风险说明"]


def test_rule_engine_flags_deposit_penalty_and_auto_renew_gaps():
    findings = review_contract_text(
        "保证金：人民币10000元\n"
        "违约责任：违约方应承担违约金。\n"
        "合同期满后自动续约一年。"
    )
    codes = {item["规则编号"] for item in findings}
    assert {
        "DEPOSIT_RETURN_NOT_FOUND",
        "PENALTY_METHOD_NOT_FOUND",
        "AUTO_RENEW_NOTICE_WINDOW_NOT_FOUND",
    }.issubset(codes)


def test_rule_engine_does_not_flag_explicitly_quantified_terms():
    findings = review_contract_text(
        "付款安排：签约后支付30%，交付后支付50%，验收后支付20%。\n"
        "违约金：按合同金额10%计算，最高不超过合同金额20%。\n"
        "保证金：验收合格后30日内无息退还。\n"
        "续约：期满自动续约一年，任一方应提前30日书面通知不续约。"
    )
    codes = {item["规则编号"] for item in findings}
    assert "PAYMENT_PERCENT_TOTAL_OVER_100" not in codes
    assert "PAYMENT_PERCENT_TOTAL_UNDER_100" not in codes
    assert "DEPOSIT_RETURN_NOT_FOUND" not in codes
    assert "PENALTY_METHOD_NOT_FOUND" not in codes
    assert "AUTO_RENEW_NOTICE_WINDOW_NOT_FOUND" not in codes


def test_rule_engine_requires_numeric_penalty_limit_and_ignores_unlabelled_dates():
    vague = review_contract_text("违约金不超过合同金额。")
    assert "PENALTY_METHOD_NOT_FOUND" in {item["规则编号"] for item in vague}

    unrelated = review_contract_text(
        "合同金额：详见附件\n签订日期：2026-01-01\n到期日期：2026-12-31"
    )
    assert "TOTAL_AMOUNT_CONFLICT" not in {item["规则编号"] for item in unrelated}
