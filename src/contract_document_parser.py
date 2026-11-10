"""Offline, deterministic contract document extraction for human-reviewed CSV drafts.

This module never uploads documents and never uses OCR, AI, network services, or macros.
It extracts searchable text from PDF, DOCX and TXT files, then creates a draft CSV.
"""
import csv
import os
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from docx import Document
from pypdf import PdfReader

CONTRACT_FIELDS = [
    "合同编号", "合同名称", "甲方/客户", "乙方/供应商", "签订日期", "生效日期", "到期日期",
    "合同金额", "续约提醒提前天数", "状态", "负责人", "联系方式", "备注",
]
REVIEW_FIELDS = ["来源文件", "识别完整度", "待补齐字段", "规则提示"]
REQUIRED_FIELDS = ["合同编号", "合同名称", "签订日期", "生效日期", "到期日期", "合同金额"]
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_TEXT_CHARS = 2_000_000

DATE_RE = re.compile(
    r"(?<!\d)(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?"
)
AMOUNT_RE = re.compile(r"(?:人民币|RMB|CNY)?\s*[￥¥]?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?![\d.,])\s*(?:元)?", re.I)

LABELS = {
    "合同编号": ("合同编号", "合同号", "协议编号", "协议号"),
    "合同名称": ("合同名称", "协议名称", "项目名称"),
    "签订日期": ("签订日期", "签署日期", "签约日期"),
    "生效日期": ("生效日期", "合同生效日期", "开始日期", "履行开始日期"),
    "到期日期": ("到期日期", "终止日期", "合同截止日期", "结束日期", "履行结束日期"),
    "合同金额": ("合同金额", "合同总价", "合同价款", "总金额", "含税总价"),
    "甲方/客户": ("甲方", "甲方名称", "甲方单位", "委托方", "采购方"),
    "乙方/供应商": ("乙方", "乙方名称", "乙方单位", "受托方", "供应方", "承包方"),
}
CLAUSE_CHECKS = (
    ("付款与结算", ("付款", "支付", "结算")),
    ("交付与验收", ("交付", "验收", "交接")),
    ("违约责任", ("违约责任", "违约金")),
    ("争议解决", ("争议解决", "仲裁", "诉讼", "管辖")),
    ("发票约定", ("发票", "开票")),
    ("质保或保证金", ("质保", "保修", "保证金")),
)


def _check_file(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"文件不存在：{path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"文件超过 50 MiB 安全上限：{path.name}")
    return path


def _read_docx(path):
    document = Document(str(path))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if len(cells) >= 2:
                parts.append(f"{cells[0]}：{'；'.join(cells[1:])}")
            elif cells:
                parts.append(cells[0])
    for section in document.sections:
        for paragraph in section.header.paragraphs + section.footer.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text.strip())
    return "\n".join(parts)


def read_contract_text(path):
    """Read searchable text from a supported local contract file."""
    path = _check_file(path)
    suffix = path.suffix.casefold()
    try:
        if suffix == ".pdf":
            reader = PdfReader(str(path), strict=False)
            if reader.is_encrypted:
                raise ValueError("PDF 已加密，请先在本机解密后再识别")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError(f"PDF 超过 {MAX_PDF_PAGES} 页安全上限")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            text = _read_docx(path)
        elif suffix in (".txt", ".md"):
            raw = path.read_bytes()
            text = None
            for encoding in ("utf-8-sig", "utf-8", "gb18030"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise ValueError("文本文件编码无法识别，请另存为 UTF-8")
        else:
            raise ValueError("仅支持可搜索 PDF、DOCX、TXT 或 MD 文件")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"读取文件失败：{exc}") from exc

    text = text.replace("\u00a0", " ").replace("\r", "\n")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("提取文本超过 200 万字符安全上限")
    if not text.strip():
        if suffix == ".pdf":
            raise ValueError("未提取到可搜索文字；扫描版 PDF 暂不支持 OCR，请使用可复制文字的 PDF")
        raise ValueError("文件中没有可识别的文字")
    return text


def _label_value(text, labels):
    alternatives = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    pattern = re.compile(
        rf"^\s*(?:{alternatives})(?:（[^）]*）|\([^)]*\))?\s*[：:]\s*(.*?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(1).strip().strip("；;，,。 ")


def _dates(value):
    found = []
    invalid = False
    for match in DATE_RE.finditer(value or ""):
        try:
            found.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat())
        except ValueError:
            invalid = True
    return found, invalid


def _extract_party(text, labels):
    value = _label_value(text, labels)
    return value.split("；", 1)[0].strip()


def _extract_amount(text):
    value = _label_value(text, LABELS["合同金额"])
    if not value:
        return ""
    match = AMOUNT_RE.search(value)
    if not match:
        return ""
    try:
        amount = Decimal(match.group(1).replace(",", "")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        return ""
    if not amount.is_finite() or amount < 0:
        return ""
    return str(amount)


def parse_contract_document(path):
    """Return extracted contract fields plus transparent review findings."""
    path = _check_file(path)
    text = read_contract_text(path)
    row = {field: "" for field in CONTRACT_FIELDS}
    row["续约提醒提前天数"] = "30"
    row["状态"] = "执行中"

    row["合同编号"] = _label_value(text, LABELS["合同编号"])
    row["合同名称"] = _label_value(text, LABELS["合同名称"])
    row["甲方/客户"] = _extract_party(text, LABELS["甲方/客户"])
    row["乙方/供应商"] = _extract_party(text, LABELS["乙方/供应商"])
    row["合同金额"] = _extract_amount(text)

    invalid_date_labels = []
    for field in ("签订日期", "生效日期", "到期日期"):
        value = _label_value(text, LABELS[field])
        dates, invalid = _dates(value)
        if dates:
            row[field] = dates[0]
        if invalid:
            invalid_date_labels.append(field)

    # A clearly labelled contract term can supply the start/end dates when
    # dedicated effective/expiry labels are absent.
    period = _label_value(text, ("合同期限", "履行期限", "租赁期限"))
    period_dates, period_invalid = _dates(period)
    if period_dates:
        if not row["生效日期"]:
            row["生效日期"] = period_dates[0]
        if len(period_dates) > 1 and not row["到期日期"]:
            row["到期日期"] = period_dates[-1]
    if period_invalid:
        invalid_date_labels.append("合同期限")

    missing = [field for field in REQUIRED_FIELDS if not row[field]]
    warnings = []
    if invalid_date_labels:
        warnings.append("日期格式或日期值无法识别：" + "、".join(sorted(set(invalid_date_labels))))
    if row["生效日期"] and row["到期日期"] and row["生效日期"] > row["到期日期"]:
        warnings.append("生效日期晚于到期日期，请核对")
    if not row["甲方/客户"] or not row["乙方/供应商"]:
        warnings.append("甲方或乙方信息未完整识别，请人工核对")
    for label, terms in CLAUSE_CHECKS:
        if not any(term in text for term in terms):
            warnings.append(f"未检出“{label}”相关表述，请人工核对原文")
    if missing:
        warnings.insert(0, "待补齐字段：" + "、".join(missing))
    if not warnings:
        warnings.append("已提取主要字段；仍须逐项对照合同原文复核")

    complete = len(REQUIRED_FIELDS) - len(missing)
    return {
        **row,
        "来源文件": path.name,
        "识别完整度": f"{complete}/{len(REQUIRED_FIELDS)}（{round(complete * 100 / len(REQUIRED_FIELDS))}%）",
        "待补齐字段": "、".join(missing),
        "规则提示": "；".join(warnings),
    }


def write_draft_csv(paths, output_path):
    """Parse every file first, then atomically write a UTF-8-BOM review CSV."""
    paths = list(paths)
    if not paths:
        raise ValueError("请至少选择一份合同文件")
    parsed = [parse_contract_document(path) for path in paths]
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = CONTRACT_FIELDS + REVIEW_FIELDS
    fd, temp_name = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in parsed:
                writer.writerow({field: row.get(field, "") for field in fields})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return parsed
