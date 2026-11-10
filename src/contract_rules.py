"""Deterministic, offline contract clause checks with traceable evidence.

The rules are operational screening aids, not legal advice. Every finding
includes the source line(s) that triggered it so users can verify the original.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

RULESET_VERSION = "CN-CONTRACT-2026.11.1"

CLAUSE_CHECKS = (
    ("付款与结算", ("付款", "支付", "结算")),
    ("交付与验收", ("交付", "验收", "交接")),
    ("违约责任", ("违约责任", "违约金")),
    ("争议解决", ("争议解决", "仲裁", "诉讼", "管辖")),
    ("发票约定", ("发票", "开票")),
    ("质保或保证金", ("质保", "保修", "保证金")),
)

DATE_LABELS = {
    "签订日期": ("签订日期", "签署日期", "签约日期"),
    "生效日期": ("生效日期", "合同生效日期", "开始日期", "履行开始日期"),
    "到期日期": ("到期日期", "终止日期", "合同截止日期", "结束日期", "履行结束日期"),
}
DATE_TOKEN = re.compile(
    r"(?<!\\d)(\\d{4})\\s*(?:年|[-/.])\\s*(\\d{1,2})\\s*(?:月|[-/.])\\s*(\\d{1,2})\\s*日?(?!\\d)"
)
AMOUNT_LABEL = re.compile(r"合同金额|合同总价|合同价款|含税总价|总价款|总金额")
AMOUNT_AFTER_LABEL = re.compile(
    r"(?:人民币|RMB|CNY)?\\s*[￥¥]?\\s*((?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d{1,2})?)\\s*(?:元)?",
    re.I,
)
PERCENT = re.compile(r"(?<![\\d.])(\\d+(?:\\.\\d+)?)\\s*%")
PAYMENT_TERMS = ("付款", "支付", "预付款", "进度款", "尾款", "结算")
PAYMENT_EXCLUSIONS = ("违约金", "滞纳金", "利息", "税率", "增值税", "折扣", "保证金", "质保金", "押金")
PENALTY_TERMS = ("违约金", "违约责任", "逾期违约")
PENALTY_QUANTIFIERS = re.compile(
    r"按日|每日|每逾期|万分之|千分之|百分之|不超过|最高|上限|按合同金额|\\d+(?:\\.\\d+)?\\s*%|\\d[\\d,]*(?:\\.\\d+)?\\s*元"
)
DEPOSIT_TERMS = ("保证金", "押金", "质保金")
REFUND_TERMS = ("退还", "返还", "退回", "无息退还", "到期退还", "期满返还")
AUTO_RENEW_TERMS = ("自动续约", "自动续期", "期满自动续签", "自动延长")
NOTICE_WINDOW = re.compile(r"提前\\s*\\d+\\s*(?:日|天)")


def _valid_dates(value):
    found = []
    for match in DATE_TOKEN.finditer(value):
        try:
            found.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
    return found


def review_contract_text(text):
    """Return sorted, explainable findings from the supplied contract text."""
    lines = [(number, line.strip()) for number, line in enumerate(str(text or "").splitlines(), 1) if line.strip()]
    findings = []

    def add(level, code, label, description, action, line_numbers=(), note=""):
        evidence = []
        for number in sorted(set(line_numbers)):
            source = next((line for line_no, line in lines if line_no == number), "")
            if source:
                evidence.append(f"第{number}行：{source[:180]}")
        if not evidence and note:
            evidence.append(note)
        findings.append({
            "等级": level,
            "规则编号": code,
            "检查项": label,
            "风险说明": description,
            "证据摘录": "；".join(evidence),
            "建议动作": action,
        })

    full_text = "\\n".join(line for _, line in lines)

    # Missing keywords are deliberately low-severity prompts, never proof that
    # a clause is absent. Users must inspect the complete signed document.
    for label, terms in CLAUSE_CHECKS:
        if not any(term in full_text for term in terms):
            suffix = {
                "付款与结算": "PAYMENT",
                "交付与验收": "DELIVERY",
                "违约责任": "DEFAULT",
                "争议解决": "DISPUTE",
                "发票约定": "INVOICE",
                "质保或保证金": "WARRANTY",
            }[label]
            add(
                "低", f"CLAUSE_KEYWORD_NOT_FOUND_{suffix}", label,
                f"全文未检出“{label}”相关关键词；这不代表合同一定缺少该条款",
                "对照合同原文确认是否有相应约定，必要时补录人工核对结果",
                note="未检出关键词不是缺失条款的结论",
            )

    # Compare only explicitly labelled total-amount fields. Other figures on
    # the same line (tax rates, unit prices, deposits) are not treated as totals.
    labelled_amounts = []
    for number, line in lines:
        for match in AMOUNT_LABEL.finditer(line):
            tail = line[match.end():match.end() + 80]
            amount_match = AMOUNT_AFTER_LABEL.search(tail)
            if not amount_match:
                continue
            try:
                amount = Decimal(amount_match.group(1).replace(",", "")).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                continue
            if amount.is_finite() and amount >= 0:
                labelled_amounts.append((number, match.group(0), amount))
    distinct_amounts = {amount for _, _, amount in labelled_amounts}
    if len(distinct_amounts) > 1:
        add(
            "高", "TOTAL_AMOUNT_CONFLICT", "合同总金额",
            "不同明确标注的合同总金额字段出现不一致数值：" + "、".join(f"{value:.2f}" for value in sorted(distinct_amounts)),
            "核对含税/不含税口径、补充协议及最终签署金额后再录入台账",
            [number for number, _, _ in labelled_amounts],
        )

    # Sum only percentages in payment-related sentence fragments. Penalties,
    # tax, discounts and deposits are excluded to reduce false positives.
    payment_percentages = []
    payment_line_numbers = []
    for number, line in lines:
        for fragment in re.split(r"[，,；;。！？!?]", line):
            if not any(term in fragment for term in PAYMENT_TERMS):
                continue
            if any(term in fragment for term in PAYMENT_EXCLUSIONS):
                continue
            values = [Decimal(value) for value in PERCENT.findall(fragment)]
            if values:
                payment_percentages.extend(values)
                payment_line_numbers.append(number)
    if len(payment_percentages) >= 2:
        total = sum(payment_percentages, Decimal("0"))
        if total > Decimal("100"):
            add(
                "高", "PAYMENT_PERCENT_TOTAL_OVER_100", "付款比例合计",
                f"可识别的付款阶段比例合计为 {total.normalize()}%，超过 100%",
                "核对各付款阶段是否重复、是否混入税率或其他比例",
                payment_line_numbers,
            )
        elif total < Decimal("100"):
            add(
                "中", "PAYMENT_PERCENT_TOTAL_UNDER_100", "付款比例合计",
                f"可识别的付款阶段比例合计为 {total.normalize()}%，未达到 100%；可能有阶段未被识别",
                "核对是否遗漏尾款、质保金或其他付款阶段；以完整合同约定为准",
                payment_line_numbers,
            )

    # Conflicting repeated dates under the same explicit date label are worth
    # checking, even when each individual date is valid.
    for field, labels in DATE_LABELS.items():
        found = []
        for number, line in lines:
            for label in labels:
                pattern = re.compile(re.escape(label) + r"\\s*[：:]\\s*([^；;。]{1,80})")
                match = pattern.search(line)
                if match:
                    found.extend((number, value) for value in _valid_dates(match.group(1)))
        values = {value for _, value in found}
        if len(values) > 1:
            add(
                "中", f"{field.upper()}_CONFLICT", field,
                f"不同位置的“{field}”日期不一致：" + "、".join(sorted(value.isoformat() for value in values)),
                "对照签署页、补充协议和变更记录确认最终日期",
                [number for number, _ in found],
            )

    effective = []
    expiry = []
    for number, line in lines:
        for label in DATE_LABELS["生效日期"]:
            match = re.search(re.escape(label) + r"\\s*[：:]\\s*([^；;。]{1,80})", line)
            if match:
                effective.extend((number, value) for value in _valid_dates(match.group(1)))
        for label in DATE_LABELS["到期日期"]:
            match = re.search(re.escape(label) + r"\\s*[：:]\\s*([^；;。]{1,80})", line)
            if match:
                expiry.extend((number, value) for value in _valid_dates(match.group(1)))
    if effective and expiry and min(value for _, value in effective) > max(value for _, value in expiry):
        add(
            "高", "CONTRACT_TERM_REVERSED", "合同期限",
            "识别到的生效日期晚于到期日期",
            "核对合同期限及日期标签，避免把签订日期误作生效日期",
            [number for number, _ in effective + expiry],
        )

    deposit_lines = [number for number, line in lines if any(term in line for term in DEPOSIT_TERMS)]
    if deposit_lines and not any(term in full_text for term in REFUND_TERMS):
        add(
            "中", "DEPOSIT_RETURN_NOT_FOUND", "保证金/押金返还",
            "出现保证金、押金或质保金，但全文未检出明确返还/退还表述",
            "核对退还条件、时间、扣除情形和收款主体；不适用时请人工确认",
            deposit_lines,
        )

    penalty_lines = [number for number, line in lines if any(term in line for term in PENALTY_TERMS)]
    penalty_text = "\\n".join(line for number, line in lines if number in penalty_lines)
    if penalty_lines and not PENALTY_QUANTIFIERS.search(penalty_text):
        add(
            "中", "PENALTY_METHOD_NOT_FOUND", "违约责任",
            "检出违约责任表述，但未识别到明确计算方式、金额或上限",
            "核对违约金触发条件、计算基数、比例/金额及上限",
            penalty_lines,
        )

    renew_lines = [number for number, line in lines if any(term in line for term in AUTO_RENEW_TERMS)]
    if renew_lines and not NOTICE_WINDOW.search(full_text):
        add(
            "中", "AUTO_RENEW_NOTICE_WINDOW_NOT_FOUND", "自动续约",
            "检出自动续约/自动续期表述，但未识别到提前通知天数",
            "核对不续约通知期限、通知方式及送达要求",
            renew_lines,
        )

    order = {"高": 0, "中": 1, "低": 2}
    return sorted(findings, key=lambda item: (order[item["等级"]], item["规则编号"], item["检查项"]))
