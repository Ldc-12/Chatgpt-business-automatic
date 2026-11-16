"""Offline supplier statement reconciliation and accounts-payable aging assistant."""
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "供应商对账与应付账龄管理助手"
FORMAT = "mainland-supplier-ap"
VERSION = 1
MAX_ROWS = 50000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")
INVOICE_FIELDS = ["单据编号", "供应商编号", "供应商名称", "发票号", "单据日期", "到期日期", "金额", "备注"]
PAYMENT_FIELDS = ["付款编号", "单据编号", "付款日期", "金额", "付款凭证号", "备注"]
STATEMENT_FIELDS = ["供应商编号", "供应商名称", "发票号", "单据日期", "金额"]
AGING_FIELDS = ["供应商编号", "供应商名称", "发票号", "单据日期", "到期日期", "金额", "已付金额", "未付金额", "逾期天数", "账龄区间"]
RECON_FIELDS = ["供应商编号", "供应商名称", "发票号", "单据日期", "对账单金额", "本地金额", "差异类型"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decimal_value(value, field, allow_blank=False):
    text = "" if value is None else str(value).strip().replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    if allow_blank and not text:
        return ""
    if len(text) > 32:
        raise ValueError(f"{field}超出可接受长度")
    try:
        number = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效数字") from None
    if not number.is_finite() or number <= 0 or number > MAX_AMOUNT:
        raise ValueError(f"{field}必须大于 0 且不超过 999999999999.99")
    try:
        rounded = number.quantize(CENT, rounding=ROUND_HALF_UP)
        if rounded <= 0:
            raise ValueError(f"{field}四舍五入到分后必须大于 0")
        return format(rounded, "f")
    except InvalidOperation:
        raise ValueError(f"{field}精度超出可接受范围") from None


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value or "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


def atomic_write(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def normalize_invoice(row):
    if not isinstance(row, dict):
        raise ValueError("应付单据必须是对象")
    invoice_id = str(row.get("单据编号", "")).strip() or uuid.uuid4().hex.upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", invoice_id):
        raise ValueError("单据编号只能包含 1–64 位字母、数字、下划线或连字符")
    supplier_code = str(row.get("供应商编号", "")).strip()
    supplier_name = str(row.get("供应商名称", "")).strip()
    invoice_no = str(row.get("发票号", "")).strip()
    invoice_date = parse_date(row.get("单据日期"), "单据日期")
    due_date = parse_date(row.get("到期日期"), "到期日期")
    if due_date < invoice_date:
        raise ValueError("到期日期不能早于单据日期")
    if not supplier_code or len(supplier_code) > 40:
        raise ValueError("供应商编号不能为空且不能超过 40 个字符")
    if not supplier_name or len(supplier_name) > 100:
        raise ValueError("供应商名称不能为空且不能超过 100 个字符")
    if not invoice_no or len(invoice_no) > 100:
        raise ValueError("发票号不能为空且不能超过 100 个字符")
    note = str(row.get("备注", "") or "").strip()
    if len(note) > 2000:
        raise ValueError("备注最多 2000 个字符")
    return {
        "单据编号": invoice_id,
        "供应商编号": supplier_code,
        "供应商名称": supplier_name,
        "发票号": invoice_no,
        "单据日期": invoice_date.isoformat(),
        "到期日期": due_date.isoformat(),
        "金额": decimal_value(row.get("金额", ""), "金额"),
        "备注": note,
    }


def normalize_payment(row, invoices_by_id):
    if not isinstance(row, dict):
        raise ValueError("付款记录必须是对象")
    payment_id = str(row.get("付款编号", "")).strip() or uuid.uuid4().hex.upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", payment_id):
        raise ValueError("付款编号只能包含 1–64 位字母、数字、下划线或连字符")
    invoice_id = str(row.get("单据编号", "")).strip()
    invoice = invoices_by_id.get(invoice_id)
    if invoice is None:
        raise ValueError("付款记录关联的应付单据不存在")
    payment_date = parse_date(row.get("付款日期"), "付款日期")
    if payment_date < date.fromisoformat(invoice["单据日期"]):
        raise ValueError("付款日期不能早于单据日期")
    reference = str(row.get("付款凭证号", "") or "").strip()
    note = str(row.get("备注", "") or "").strip()
    if len(reference) > 100 or len(note) > 1000:
        raise ValueError("付款凭证号最多 100 个字符，备注最多 1000 个字符")
    return {
        "付款编号": payment_id,
        "单据编号": invoice_id,
        "付款日期": payment_date.isoformat(),
        "金额": decimal_value(row.get("金额", ""), "付款金额"),
        "付款凭证号": reference,
        "备注": note,
    }


def invoice_key(row):
    return (row["供应商编号"], row["发票号"])


def aging_bucket(days_overdue):
    if days_overdue <= 0:
        return "未到期"
    if days_overdue <= 30:
        return "逾期1-30天"
    if days_overdue <= 60:
        return "逾期31-60天"
    if days_overdue <= 90:
        return "逾期61-90天"
    return "逾期90天以上"


class SupplierAPStore:
    def __init__(self, path):
        self.path = Path(path)
        self.invoices = []
        self.payments = []
        self.load()

    @staticmethod
    def _payload(invoices, payments):
        body = {"格式": FORMAT, "版本": VERSION, "应付单据": invoices, "付款记录": payments}
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def _validate(invoices, payments):
        normalized_invoices = [normalize_invoice(row) for row in invoices]
        if len(normalized_invoices) > MAX_ROWS:
            raise ValueError("应付单据超过 50000 条安全上限")
        invoice_ids = [row["单据编号"] for row in normalized_invoices]
        keys = [invoice_key(row) for row in normalized_invoices]
        if len(invoice_ids) != len(set(invoice_ids)):
            raise ValueError("单据编号重复")
        if len(keys) != len(set(keys)):
            raise ValueError("同一供应商的发票号不能重复")
        invoices_by_id = {row["单据编号"]: row for row in normalized_invoices}
        normalized_payments = [normalize_payment(row, invoices_by_id) for row in payments]
        if len(normalized_payments) > MAX_ROWS * 5:
            raise ValueError("付款记录超过 250000 条安全上限")
        payment_ids = [row["付款编号"] for row in normalized_payments]
        if len(payment_ids) != len(set(payment_ids)):
            raise ValueError("付款编号重复")
        paid = {}
        for payment in normalized_payments:
            paid[payment["单据编号"]] = paid.get(payment["单据编号"], Decimal("0")) + Decimal(payment["金额"])
        for invoice in normalized_invoices:
            if paid.get(invoice["单据编号"], Decimal("0")) > Decimal(invoice["金额"]):
                raise ValueError(f"单据 {invoice['发票号']} 的累计付款超过应付金额")
        return normalized_invoices, normalized_payments

    @classmethod
    def decode(cls, payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("应付账龄备份格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("应付账龄文件 SHA256 校验失败")
        invoices = body.get("应付单据")
        payments = body.get("付款记录")
        if not isinstance(invoices, list) or not isinstance(payments, list):
            raise ValueError("应付单据或付款记录格式无效")
        if len(invoices) > MAX_ROWS or len(payments) > MAX_ROWS * 5:
            raise ValueError("备份记录数量超过安全上限")
        return cls._validate(invoices, payments)

    def load(self):
        if not self.path.exists():
            self.invoices, self.payments = [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("本地应付账龄数据超过 100 MiB，已拒绝加载且原文件未修改")
        try:
            self.invoices, self.payments = self.decode(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"本地应付账龄数据无法读取，原文件未修改：{exc}") from exc

    def _commit(self, invoices, payments):
        normalized_invoices, normalized_payments = self._validate(invoices, payments)
        data = json.dumps(self._payload(normalized_invoices, normalized_payments), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("应付账龄数据超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.invoices, self.payments = normalized_invoices, normalized_payments

    def add_invoice(self, row):
        normalized = normalize_invoice(row)
        if any(item["单据编号"] == normalized["单据编号"] for item in self.invoices):
            raise ValueError("单据编号已存在")
        if any(invoice_key(item) == invoice_key(normalized) for item in self.invoices):
            raise ValueError("同一供应商的发票号已存在")
        self._commit(self.invoices + [normalized], self.payments)
        return normalized["单据编号"]

    def add_payment(self, invoice_id, amount, payment_date, reference="", note=""):
        invoice = next((item for item in self.invoices if item["单据编号"] == invoice_id), None)
        if invoice is None:
            raise ValueError("要付款的应付单据不存在")
        paid = sum((Decimal(item["金额"]) for item in self.payments if item["单据编号"] == invoice_id), Decimal("0"))
        value = Decimal(decimal_value(amount, "付款金额"))
        outstanding = Decimal(invoice["金额"]) - paid
        if value > outstanding:
            raise ValueError(f"付款金额超过未付余额 {outstanding.quantize(CENT)} 元")
        payment = normalize_payment({
            "单据编号": invoice_id, "付款日期": payment_date, "金额": format(value, "f"),
            "付款凭证号": reference, "备注": note,
        }, {item["单据编号"]: item for item in self.invoices})
        self._commit(self.invoices, self.payments + [payment])
        return payment["付款编号"]

    def delete_invoice(self, invoice_id):
        if not any(item["单据编号"] == invoice_id for item in self.invoices):
            raise ValueError("要删除的应付单据不存在")
        if any(item["单据编号"] == invoice_id for item in self.payments):
            raise ValueError("已有付款记录的单据不能删除，请先核对付款记录")
        self._commit([item for item in self.invoices if item["单据编号"] != invoice_id], self.payments)

    def payments_for_invoice(self, invoice_id):
        return sorted(
            [dict(item) for item in self.payments if item["单据编号"] == invoice_id],
            key=lambda item: (item["付款日期"], item["付款编号"]),
        )

    def invoice_rows(self, as_of_date=None):
        as_of = parse_date(as_of_date or date.today().isoformat(), "统计日期")
        paid_by_invoice = {}
        for payment in self.payments:
            paid_by_invoice[payment["单据编号"]] = paid_by_invoice.get(payment["单据编号"], Decimal("0")) + Decimal(payment["金额"])
        output = []
        for invoice in self.invoices:
            paid = paid_by_invoice.get(invoice["单据编号"], Decimal("0"))
            amount = Decimal(invoice["金额"])
            outstanding = amount - paid
            due = date.fromisoformat(invoice["到期日期"])
            days = max(0, (as_of - due).days) if outstanding > 0 else 0
            output.append({
                **invoice,
                "已付金额": format(paid.quantize(CENT), "f"),
                "未付金额": format(outstanding.quantize(CENT), "f"),
                "逾期天数": days,
                "账龄区间": aging_bucket(days) if outstanding > 0 else "已结清",
            })
        return sorted(output, key=lambda row: (row["到期日期"], row["供应商编号"], row["发票号"]))

    def aging_report(self, as_of_date=None):
        return [row for row in self.invoice_rows(as_of_date) if Decimal(row["未付金额"]) > 0]

    def aging_summary(self, as_of_date=None):
        groups = {}
        for row in self.aging_report(as_of_date):
            key = (row["供应商编号"], row["供应商名称"])
            item = groups.setdefault(key, {
                "供应商编号": key[0], "供应商名称": key[1], "单据数": 0,
                "未到期": Decimal("0"), "逾期1-30天": Decimal("0"),
                "逾期31-60天": Decimal("0"), "逾期61-90天": Decimal("0"),
                "逾期90天以上": Decimal("0"), "未付合计": Decimal("0"),
            })
            balance = Decimal(row["未付金额"])
            item["单据数"] += 1
            item[row["账龄区间"]] += balance
            item["未付合计"] += balance
        fields = ("未到期", "逾期1-30天", "逾期31-60天", "逾期61-90天", "逾期90天以上", "未付合计")
        output = []
        for item in sorted(groups.values(), key=lambda row: (row["供应商编号"], row["供应商名称"])):
            output.append({
                **item,
                **{field: format(item[field].quantize(CENT), "f") for field in fields},
            })
        return output

    def due_list(self, as_of_date=None, horizon_days=30):
        if not isinstance(horizon_days, int) or horizon_days < 0 or horizon_days > 365:
            raise ValueError("提醒天数必须在 0 至 365 之间")
        as_of = parse_date(as_of_date or date.today().isoformat(), "统计日期")
        cutoff = as_of + timedelta(days=horizon_days)
        return [
            row for row in self.aging_report(as_of.isoformat())
            if date.fromisoformat(row["到期日期"]) <= cutoff
        ]

    def import_invoices_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("CSV 超过 25 MiB 安全上限")
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != INVOICE_FIELDS:
                raise ValueError("CSV 表头与本软件应付单据模板不一致")
            incoming = []
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"CSV 第 {line} 行列数不正确")
                incoming.append(normalize_invoice(row))
                if len(incoming) > MAX_ROWS:
                    raise ValueError("CSV 超过 50000 条记录上限")
        ids = [row["单据编号"] for row in incoming]
        keys = [invoice_key(row) for row in incoming]
        existing_ids = {row["单据编号"] for row in self.invoices}
        existing_keys = {invoice_key(row) for row in self.invoices}
        if len(ids) != len(set(ids)) or existing_ids.intersection(ids):
            raise ValueError("CSV 包含重复单据编号，未导入任何数据")
        if len(keys) != len(set(keys)) or existing_keys.intersection(keys):
            raise ValueError("CSV 包含重复供应商发票号，未导入任何数据")
        if len(self.invoices) + len(incoming) > MAX_ROWS:
            raise ValueError("导入后应付单据超过 50000 条安全上限")
        self._commit(self.invoices + incoming, self.payments)
        return len(incoming)

    def export_invoices_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=INVOICE_FIELDS)
        writer.writeheader()
        for row in self.invoices:
            writer.writerow({field: csv_safe(row[field]) if field not in {"金额"} else row[field] for field in INVOICE_FIELDS})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def export_aging_csv(self, path, as_of_date=None):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=AGING_FIELDS)
        writer.writeheader()
        for row in self.aging_report(as_of_date):
            writer.writerow({field: csv_safe(row[field]) if field in {"供应商编号", "供应商名称", "发票号", "单据日期", "到期日期", "账龄区间"} else row[field] for field in AGING_FIELDS})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def reconcile_statement_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("供应商对账单 CSV 超过 25 MiB 安全上限")
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != STATEMENT_FIELDS:
                raise ValueError("对账单 CSV 表头必须为：供应商编号、供应商名称、发票号、单据日期、金额")
            statement = []
            seen = set()
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"对账单第 {line} 行列数不正确")
                code = str(row["供应商编号"] or "").strip()
                name = str(row["供应商名称"] or "").strip()
                number = str(row["发票号"] or "").strip()
                doc_date = parse_date(row["单据日期"], f"第 {line} 行单据日期").isoformat()
                amount = decimal_value(row["金额"], f"第 {line} 行金额")
                if not code or len(code) > 40 or not name or len(name) > 100 or not number or len(number) > 100:
                    raise ValueError(f"对账单第 {line} 行供应商或发票信息无效")
                key = (code, number)
                if key in seen:
                    raise ValueError(f"对账单第 {line} 行出现重复供应商发票号")
                seen.add(key)
                statement.append({"供应商编号": code, "供应商名称": name, "发票号": number, "单据日期": doc_date, "金额": amount})
                if len(statement) > MAX_ROWS:
                    raise ValueError("对账单超过 50000 条记录上限")
        if not statement:
            raise ValueError("对账单没有数据，未执行核对")
        local = {invoice_key(row): row for row in self.invoices}
        issues = []
        statement_keys = set()
        supplier_codes = {row["供应商编号"] for row in statement}
        if statement:
            start = min(row["单据日期"] for row in statement)
            end = max(row["单据日期"] for row in statement)
        else:
            start = end = ""
        for row in statement:
            key = (row["供应商编号"], row["发票号"])
            statement_keys.add(key)
            invoice = local.get(key)
            if invoice is None:
                issues.append({**row, "本地金额": "", "差异类型": "本地缺少单据"})
                continue
            differences = []
            if invoice["供应商名称"] != row["供应商名称"]:
                differences.append("供应商名称不一致")
            if invoice["单据日期"] != row["单据日期"]:
                differences.append("单据日期不一致")
            if Decimal(invoice["金额"]) != Decimal(row["金额"]):
                differences.append("金额不一致")
            if differences:
                issues.append({
                    **row, "本地金额": invoice["金额"], "差异类型": "、".join(differences),
                })
        if statement:
            for invoice in self.invoices:
                key = invoice_key(invoice)
                if invoice["供应商编号"] in supplier_codes and start <= invoice["单据日期"] <= end and key not in statement_keys:
                    issues.append({
                        "供应商编号": invoice["供应商编号"], "供应商名称": invoice["供应商名称"],
                        "发票号": invoice["发票号"], "单据日期": invoice["单据日期"],
                        "金额": "", "本地金额": invoice["金额"], "差异类型": "对账单缺少本地单据",
                    })
        return [
            {
                "供应商编号": row["供应商编号"], "供应商名称": row["供应商名称"],
                "发票号": row["发票号"], "单据日期": row["单据日期"],
                "对账单金额": row.get("金额", ""), "本地金额": row.get("本地金额", ""),
                "差异类型": row["差异类型"],
            }
            for row in issues
        ]

    def export_reconciliation_csv(self, path, issues):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=RECON_FIELDS)
        writer.writeheader()
        for row in issues:
            writer.writerow({field: csv_safe(row[field]) for field in RECON_FIELDS})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def backup(self, path):
        data = json.dumps(self._payload(self.invoices, self.payments), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        invoices, payments = self.decode(payload)
        self._commit(invoices, payments)


def default_data_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "MainlandBusinessTools" / "supplier_ap.json"


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        store = SupplierAPStore(Path(folder) / "data.json")
        invoice_id = store.add_invoice({
            "供应商编号": "V001", "供应商名称": "测试供应商", "发票号": "INV-001",
            "单据日期": "2026-11-01", "到期日期": "2026-11-30", "金额": "1000",
        })
        store.add_payment(invoice_id, "250", "2026-11-10", "PAY-001")
        report = store.aging_report("2026-12-15")
        assert report[0]["未付金额"] == "750.00"
        assert report[0]["账龄区间"] == "逾期1-30天"
        backup = Path(folder) / "backup.json"
        store.backup(backup)
        restored = SupplierAPStore(Path(folder) / "restored.json")
        restored.restore(backup)
        assert restored.invoice_rows("2026-12-15")[0]["未付金额"] == "750.00"
    print("SELF_TEST_OK")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        require_license(PRODUCT)
        self.store = SupplierAPStore(default_data_path())
        self.last_reconciliation = None
        self.title(PRODUCT)
        self.geometry("1320x720")
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        actions = (
            ("新增应付单据", self.add_invoice), ("记录付款", self.record_payment),
            ("付款记录", self.show_payments), ("删除单据", self.delete_invoice),
            ("导入单据 CSV", self.import_invoices), ("导出单据", self.export_invoices),
            ("账龄报表", self.export_aging), ("供应商汇总", self.show_summary),
            ("对账单核对", self.reconcile_statement), ("导出差异", self.export_reconciliation),
            ("备份", self.backup), ("恢复", self.restore),
        )
        for label, command in actions:
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=2)
        self.search = tk.StringVar()
        ttk.Label(bar, text="搜索").pack(side="left", padx=(10, 3))
        search = ttk.Entry(bar, textvariable=self.search, width=22)
        search.pack(side="left")
        self.search.trace_add("write", lambda *_: self.refresh())
        columns = ("供应商名称", "发票号", "单据日期", "到期日期", "金额", "已付金额", "未付金额", "账龄区间")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        widths = (150, 120, 100, 100, 100, 100, 100, 110)
        for field, width in zip(columns, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().lower()
        for row in self.store.invoice_rows():
            text = " ".join(str(row.get(field, "")) for field in INVOICE_FIELDS + ["已付金额", "未付金额", "账龄区间"]).lower()
            if query and query not in text:
                continue
            self.tree.insert("", "end", iid=row["单据编号"], values=[
                row["供应商名称"], row["发票号"], row["单据日期"], row["到期日期"],
                row["金额"], row["已付金额"], row["未付金额"], row["账龄区间"],
            ])

    def _selected(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def add_invoice(self):
        window = tk.Toplevel(self)
        window.title("新增应付单据")
        window.transient(self)
        window.grab_set()
        fields = {
            "供应商编号": "", "供应商名称": "", "发票号": "",
            "单据日期": date.today().isoformat(), "到期日期": (date.today() + timedelta(days=30)).isoformat(),
            "金额": "", "备注": "",
        }
        values = {key: tk.StringVar(value=value) for key, value in fields.items()}
        for index, (field, value) in enumerate(values.items()):
            ttk.Label(window, text=field).grid(row=index, column=0, sticky="w", padx=8, pady=5)
            ttk.Entry(window, textvariable=value, width=38).grid(row=index, column=1, padx=8, pady=5)
        def save():
            try:
                self.store.add_invoice({field: value.get().strip() for field, value in values.items()})
                self.refresh()
                window.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)
        buttons = ttk.Frame(window, padding=8)
        buttons.grid(row=len(values), column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=4)
        ttk.Button(buttons, text="取消", command=window.destroy).pack(side="right", padx=4)

    def record_payment(self):
        invoice_id = self._selected()
        if not invoice_id:
            messagebox.showinfo("记录付款", "请先选择一张应付单据。")
            return
        amount = simpledialog.askstring("记录付款", "本次付款金额：", parent=self)
        if amount is None:
            return
        payment_date = simpledialog.askstring("付款日期", "付款日期（YYYY-MM-DD）：", initialvalue=date.today().isoformat(), parent=self)
        if payment_date is None:
            return
        reference = simpledialog.askstring("付款凭证", "付款凭证号（可留空）：", parent=self) or ""
        note = simpledialog.askstring("付款备注", "付款备注（可留空）：", parent=self) or ""
        try:
            self.store.add_payment(invoice_id, amount, payment_date, reference, note)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("付款失败", str(exc), parent=self)

    def show_payments(self):
        invoice_id = self._selected()
        if not invoice_id:
            messagebox.showinfo("付款记录", "请先选择一张应付单据。")
            return
        payments = self.store.payments_for_invoice(invoice_id)
        if not payments:
            messagebox.showinfo("付款记录", "该单据尚无付款记录。", parent=self)
            return
        lines = [
            f"{row['付款日期']}｜{row['金额']} 元｜凭证 {row['付款凭证号'] or '未填写'}"
            for row in payments
        ]
        messagebox.showinfo("付款记录", "\n".join(lines[:50]), parent=self)

    def delete_invoice(self):
        invoice_id = self._selected()
        if not invoice_id:
            messagebox.showinfo("删除单据", "请先选择一张应付单据。")
            return
        if not messagebox.askyesno("确认删除", "删除后无法自动撤销，确定删除所选单据吗？", parent=self):
            return
        try:
            self.store.delete_invoice(invoice_id)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=self)

    def import_invoices(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_invoices_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 张应付单据。", parent=self)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def export_invoices(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_invoices_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

    def export_aging(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        day = simpledialog.askstring("账龄报表", "统计日期（YYYY-MM-DD）：", initialvalue=date.today().isoformat(), parent=self)
        if day is None:
            return
        try:
            self.store.export_aging_csv(path, day)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出账龄失败", str(exc), parent=self)

    def show_summary(self):
        day = simpledialog.askstring("供应商应付账龄", "统计日期（YYYY-MM-DD）：", initialvalue=date.today().isoformat(), parent=self)
        if day is None:
            return
        try:
            rows = self.store.aging_summary(day)
            if not rows:
                messagebox.showinfo("供应商汇总", "没有未结清的应付单据。", parent=self)
                return
            lines = [
                f"{row['供应商名称']}｜未付 {row['未付合计']} 元｜未到期 {row['未到期']}｜"
                f"逾期1-30天 {row['逾期1-30天']}｜31-60天 {row['逾期31-60天']}｜"
                f"61-90天 {row['逾期61-90天']}｜90天以上 {row['逾期90天以上']}"
                for row in rows
            ]
            messagebox.showinfo("供应商汇总", "\n".join(lines[:30]), parent=self)
        except ValueError as exc:
            messagebox.showerror("汇总失败", str(exc), parent=self)

    def reconcile_statement(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 对账单", "*.csv")])
        if not path:
            return
        try:
            self.last_reconciliation = self.store.reconcile_statement_csv(path)
            if not self.last_reconciliation:
                messagebox.showinfo("对账结果", "未发现差异。", parent=self)
            else:
                lines = [
                    f"{row['供应商名称']}｜{row['发票号']}｜{row['差异类型']}"
                    for row in self.last_reconciliation
                ]
                messagebox.showwarning("发现对账差异", "\n".join(lines[:30]), parent=self)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("对账失败", str(exc), parent=self)

    def export_reconciliation(self):
        if self.last_reconciliation is None:
            messagebox.showinfo("导出差异", "请先执行一次供应商对账单核对。", parent=self)
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_reconciliation_csv(path, self.last_reconciliation)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出差异失败", str(exc), parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
            except (OSError, ValueError) as exc:
                messagebox.showerror("备份失败", str(exc), parent=self)

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前应付单据和付款记录，建议先备份。是否继续？", parent=self):
            try:
                self.store.restore(path)
                self.refresh()
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc), parent=self)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    App().mainloop()
