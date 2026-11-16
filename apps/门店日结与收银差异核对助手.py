"""Offline store shift cash-close and reconciliation assistant."""
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "门店日结与收银差异核对助手"
FORMAT = "mainland-store-cash-close"
VERSION = 1
MAX_ROWS = 50000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
CENT = Decimal("0.01")
SHIFTS = {"早班", "中班", "晚班", "全天"}
STATUSES = {"待复核", "已复核", "已封账"}
AMOUNT_FIELDS = (
    "备用金期初", "现金销售", "微信收款", "支付宝收款", "银行卡收款",
    "其他收款", "现金退款", "电子退款", "现金支出", "实际现金盘点",
)
OPTIONAL_POS_FIELDS = ("POS销售合计", "POS退款合计")
FIELDS = [
    "记录编号", "营业日期", "门店编号", "门店名称", "班次", "收银台编号", "收银员",
    *AMOUNT_FIELDS, *OPTIONAL_POS_FIELDS, "复核人", "差异处理说明", "备注", "状态", "封账时间",
]
DERIVED_FIELDS = ["应有现金", "现金差异", "渠道净收", "POS净收", "POS差异"]
EXPORT_FIELDS = FIELDS + DERIVED_FIELDS


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decimal_value(value, field, allow_blank=False):
    text = "" if value is None else str(value).strip().replace(",", "").replace("，", "").replace("￥", "")
    if allow_blank and not text:
        return ""
    try:
        number = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效数字") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field}必须是非负有限数字")
    return format(number.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


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


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("日结记录必须是对象")
    record_id = str(row.get("记录编号", "")).strip() or uuid.uuid4().hex.upper()
    try:
        business_date = date.fromisoformat(str(row.get("营业日期", "")).strip()).isoformat()
    except (TypeError, ValueError):
        raise ValueError("营业日期必须使用 YYYY-MM-DD 格式") from None
    store_code = str(row.get("门店编号", "")).strip()
    store_name = str(row.get("门店名称", "")).strip()
    shift = str(row.get("班次", "")).strip()
    register = str(row.get("收银台编号", "")).strip()
    cashier = str(row.get("收银员", "")).strip()
    if not store_code or len(store_code) > 40:
        raise ValueError("门店编号不能为空且不能超过 40 个字符")
    if not store_name or len(store_name) > 100:
        raise ValueError("门店名称不能为空且不能超过 100 个字符")
    if shift not in SHIFTS:
        raise ValueError("班次必须是早班、中班、晚班或全天")
    if not register or len(register) > 40:
        raise ValueError("收银台编号不能为空且不能超过 40 个字符")
    if not cashier or len(cashier) > 80:
        raise ValueError("收银员不能为空且不能超过 80 个字符")
    amounts = {field: decimal_value(row.get(field, "0"), field) for field in AMOUNT_FIELDS}
    pos = {field: decimal_value(row.get(field, ""), field, allow_blank=True) for field in OPTIONAL_POS_FIELDS}
    if bool(pos[OPTIONAL_POS_FIELDS[0]]) != bool(pos[OPTIONAL_POS_FIELDS[1]]):
        raise ValueError("POS 销售合计和 POS 退款合计必须同时填写或同时留空")
    status = str(row.get("状态", "待复核") or "待复核").strip()
    if status not in STATUSES:
        raise ValueError("日结状态不受支持")
    reviewer = str(row.get("复核人", "") or "").strip()
    resolution = str(row.get("差异处理说明", "") or "").strip()
    closed_at = str(row.get("封账时间", "") or "").strip()
    if status in {"已复核", "已封账"} and not reviewer:
        raise ValueError("已复核或已封账记录必须填写复核人")
    if status == "已封账" and not closed_at:
        raise ValueError("已封账记录必须保留封账时间")
    calculated = calculate({**amounts, **pos})
    if status in {"已复核", "已封账"} and has_variance(calculated) and not resolution:
        raise ValueError("存在收银差异时，复核/封账前必须填写差异处理说明")
    return {
        "记录编号": record_id,
        "营业日期": business_date,
        "门店编号": store_code,
        "门店名称": store_name,
        "班次": shift,
        "收银台编号": register,
        "收银员": cashier,
        **amounts,
        **pos,
        "复核人": reviewer,
        "差异处理说明": resolution,
        "备注": str(row.get("备注", "") or "").strip(),
        "状态": status,
        "封账时间": closed_at,
    }


def calculate(row):
    opening = Decimal(row.get("备用金期初", "0") or "0")
    cash_sales = Decimal(row.get("现金销售", "0") or "0")
    cash_refund = Decimal(row.get("现金退款", "0") or "0")
    cash_expense = Decimal(row.get("现金支出", "0") or "0")
    counted = Decimal(row.get("实际现金盘点", "0") or "0")
    channel_net = (
        cash_sales
        + Decimal(row.get("微信收款", "0") or "0")
        + Decimal(row.get("支付宝收款", "0") or "0")
        + Decimal(row.get("银行卡收款", "0") or "0")
        + Decimal(row.get("其他收款", "0") or "0")
        - cash_refund
        - Decimal(row.get("电子退款", "0") or "0")
    )
    expected_cash = opening + cash_sales - cash_refund - cash_expense
    pos_sales = row.get("POS销售合计", "")
    pos_refunds = row.get("POS退款合计", "")
    pos_net = Decimal(pos_sales) - Decimal(pos_refunds) if pos_sales != "" and pos_refunds != "" else None
    pos_variance = channel_net - pos_net if pos_net is not None else None
    return {
        "应有现金": format(expected_cash.quantize(CENT), "f"),
        "现金差异": format((counted - expected_cash).quantize(CENT), "f"),
        "渠道净收": format(channel_net.quantize(CENT), "f"),
        "POS净收": format(pos_net.quantize(CENT), "f") if pos_net is not None else "",
        "POS差异": format(pos_variance.quantize(CENT), "f") if pos_variance is not None else "",
    }


def has_variance(values):
    return Decimal(values["现金差异"]) != 0 or (
        values["POS差异"] != "" and Decimal(values["POS差异"]) != 0
    )


def business_key(row):
    return (row["营业日期"], row["门店编号"], row["班次"], row["收银台编号"])


def append_event(events, action, record_id="", actor="本机用户", reason=""):
    previous = events[-1]["hash"] if events else ""
    body = {
        "seq": len(events) + 1,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "action": action,
        "record_id": record_id,
        "actor": str(actor or "本机用户").strip(),
        "reason": str(reason or "").strip(),
        "previous_hash": previous,
    }
    return events + [{**body, "hash": hashlib.sha256(canonical(body)).hexdigest()}]


def verify_audit(events):
    previous = ""
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != index or event.get("previous_hash") != previous:
            raise ValueError("日结操作日志顺序或前序摘要无效")
        body = {key: value for key, value in event.items() if key != "hash"}
        digest = hashlib.sha256(canonical(body)).hexdigest()
        if event.get("hash") != digest:
            raise ValueError("日结操作日志 SHA256 校验失败")
        previous = digest
    return True


class CashCloseStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.events = []
        self.load()

    @staticmethod
    def _payload(rows, events):
        body = {"格式": FORMAT, "版本": VERSION, "记录": rows, "操作日志": events}
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("日结文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("日结文件 SHA256 校验失败")
        raw_rows = body.get("记录")
        events = body.get("操作日志")
        if not isinstance(raw_rows, list) or len(raw_rows) > MAX_ROWS:
            raise ValueError("日结记录缺失或超过 50000 条安全上限")
        if not isinstance(events, list) or len(events) > MAX_ROWS * 10:
            raise ValueError("操作日志格式无效或超过安全上限")
        rows = [normalize(item) for item in raw_rows]
        ids = [row["记录编号"] for row in rows]
        keys = [business_key(row) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("日结记录编号重复")
        if len(keys) != len(set(keys)):
            raise ValueError("同一营业日期、门店、班次和收银台不能重复日结")
        verify_audit(events)
        return rows, events

    def load(self):
        if not self.path.exists():
            self.rows, self.events = [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("本地日结数据超过 100 MiB，已拒绝加载且原文件未修改")
        try:
            self.rows, self.events = self.decode(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"本地日结数据无法读取，原文件未修改：{exc}") from exc

    def _commit(self, rows, events):
        normalized = [normalize(row) for row in rows]
        if len(normalized) > MAX_ROWS:
            raise ValueError("日结记录超过 50000 条安全上限")
        ids = [row["记录编号"] for row in normalized]
        keys = [business_key(row) for row in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("日结记录编号重复")
        if len(keys) != len(set(keys)):
            raise ValueError("同一营业日期、门店、班次和收银台不能重复日结")
        verify_audit(events)
        data = json.dumps(self._payload(normalized, events), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("日结数据超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.rows, self.events = normalized, events

    def add(self, row, actor="本机用户"):
        normalized = normalize(row)
        if any(item["记录编号"] == normalized["记录编号"] for item in self.rows):
            raise ValueError("日结记录编号已存在")
        if any(business_key(item) == business_key(normalized) for item in self.rows):
            raise ValueError("同一营业日期、门店、班次和收银台已存在日结记录")
        events = append_event(self.events, "新增", normalized["记录编号"], actor)
        self._commit(self.rows + [normalized], events)
        return normalized["记录编号"]

    def update(self, record_id, row, actor="本机用户"):
        existing = next((item for item in self.rows if item["记录编号"] == record_id), None)
        if existing is None:
            raise ValueError("要编辑的日结记录不存在")
        if existing["状态"] == "已封账":
            raise ValueError("已封账记录不能直接编辑，请先填写原因重新开账")
        values = dict(row)
        values["记录编号"] = record_id
        values["状态"] = "待复核"
        values["复核人"] = ""
        values["差异处理说明"] = ""
        values["封账时间"] = ""
        normalized = normalize(values)
        candidate = [normalized if item["记录编号"] == record_id else item for item in self.rows]
        events = append_event(self.events, "编辑", record_id, actor)
        self._commit(candidate, events)
        return record_id

    def delete(self, record_id, actor="本机用户"):
        existing = next((item for item in self.rows if item["记录编号"] == record_id), None)
        if existing is None:
            raise ValueError("要删除的日结记录不存在")
        if existing["状态"] == "已封账":
            raise ValueError("已封账记录不能删除，请先填写原因重新开账")
        events = append_event(self.events, "删除", record_id, actor)
        self._commit([item for item in self.rows if item["记录编号"] != record_id], events)

    def review(self, record_id, reviewer, resolution_note=""):
        existing = next((item for item in self.rows if item["记录编号"] == record_id), None)
        if existing is None:
            raise ValueError("要复核的日结记录不存在")
        if existing["状态"] == "已封账":
            raise ValueError("已封账记录不能再次复核，请先重新开账")
        reviewer = str(reviewer or "").strip()
        if not reviewer:
            raise ValueError("复核人不能为空")
        derived = calculate(existing)
        if has_variance(derived) and not str(resolution_note or "").strip():
            raise ValueError("存在现金或 POS 差异，请填写差异处理说明后再复核")
        values = dict(existing)
        values["复核人"] = reviewer
        values["差异处理说明"] = str(resolution_note or "").strip()
        values["状态"] = "已复核"
        candidate = [normalize(values) if item["记录编号"] == record_id else item for item in self.rows]
        events = append_event(self.events, "复核", record_id, reviewer, values["差异处理说明"])
        self._commit(candidate, events)

    def close(self, record_id):
        existing = next((item for item in self.rows if item["记录编号"] == record_id), None)
        if existing is None:
            raise ValueError("要封账的日结记录不存在")
        if existing["状态"] != "已复核":
            raise ValueError("封账前必须先完成复核")
        values = dict(existing)
        values["状态"] = "已封账"
        values["封账时间"] = datetime.now().astimezone().isoformat(timespec="seconds")
        candidate = [normalize(values) if item["记录编号"] == record_id else item for item in self.rows]
        events = append_event(self.events, "封账", record_id, existing["复核人"])
        self._commit(candidate, events)

    def reopen(self, record_id, reason, actor="本机用户"):
        existing = next((item for item in self.rows if item["记录编号"] == record_id), None)
        if existing is None:
            raise ValueError("要重新开账的记录不存在")
        if existing["状态"] != "已封账":
            raise ValueError("只有已封账记录才能重新开账")
        reason = str(reason or "").strip()
        if len(reason) < 4:
            raise ValueError("重新开账必须填写至少 4 个字符的原因")
        values = dict(existing)
        values["状态"] = "待复核"
        values["复核人"] = ""
        values["差异处理说明"] = ""
        values["封账时间"] = ""
        candidate = [normalize(values) if item["记录编号"] == record_id else item for item in self.rows]
        events = append_event(self.events, "重新开账", record_id, actor, reason)
        self._commit(candidate, events)

    def import_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("CSV 超过 25 MiB 安全上限")
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames not in (FIELDS, EXPORT_FIELDS):
                raise ValueError("CSV 表头与本软件模板不一致")
            incoming = []
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"CSV 第 {line} 行列数不正确")
                normalized = normalize(row)
                if normalized["状态"] != "待复核" or normalized["封账时间"]:
                    raise ValueError(f"CSV 第 {line} 行包含已复核/封账记录，不能作为新日结导入")
                if reader.fieldnames == EXPORT_FIELDS:
                    derived = calculate(normalized)
                    for field in DERIVED_FIELDS:
                        if str(row.get(field, "")) != derived[field]:
                            raise ValueError(f"CSV 第 {line} 行的计算字段 {field} 与原始数据不一致")
                incoming.append(normalized)
                if len(incoming) > MAX_ROWS:
                    raise ValueError("CSV 超过 50000 条记录上限")
        ids = [row["记录编号"] for row in incoming]
        keys = [business_key(row) for row in incoming]
        existing_ids = {row["记录编号"] for row in self.rows}
        existing_keys = {business_key(row) for row in self.rows}
        if len(ids) != len(set(ids)) or existing_ids.intersection(ids):
            raise ValueError("CSV 包含重复日结记录编号，未导入任何数据")
        if len(keys) != len(set(keys)) or existing_keys.intersection(keys):
            raise ValueError("CSV 包含重复门店班次日结，未导入任何数据")
        if len(self.rows) + len(incoming) > MAX_ROWS:
            raise ValueError("导入后日结记录超过 50000 条安全上限")
        events = append_event(self.events, "CSV批量导入", "", "本机用户", f"导入 {len(incoming)} 条")
        self._commit(self.rows + incoming, events)
        return len(incoming)

    def export_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({**{field: csv_safe(row.get(field, "")) for field in FIELDS}, **calculate(row)})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def summary_by_store(self, business_date=None):
        groups = {}
        for row in self.rows:
            if business_date and row["营业日期"] != business_date:
                continue
            key = (row["营业日期"], row["门店编号"], row["门店名称"])
            item = groups.setdefault(key, {
                "营业日期": key[0], "门店编号": key[1], "门店名称": key[2],
                "班次数": 0, "渠道净收": Decimal("0"), "现金差异": Decimal("0"),
                "POS差异": Decimal("0"), "待复核数": 0, "已封账数": 0,
            })
            derived = calculate(row)
            item["班次数"] += 1
            item["渠道净收"] += Decimal(derived["渠道净收"])
            item["现金差异"] += Decimal(derived["现金差异"])
            if derived["POS差异"] != "":
                item["POS差异"] += Decimal(derived["POS差异"])
            item["待复核数"] += row["状态"] == "待复核"
            item["已封账数"] += row["状态"] == "已封账"
        output = []
        for item in sorted(groups.values(), key=lambda value: (value["营业日期"], value["门店编号"])):
            output.append({
                **item,
                "渠道净收": format(item["渠道净收"].quantize(CENT), "f"),
                "现金差异": format(item["现金差异"].quantize(CENT), "f"),
                "POS差异": format(item["POS差异"].quantize(CENT), "f"),
            })
        return output

    def export_summary_csv(self, path, business_date=None):
        fields = ["营业日期", "门店编号", "门店名称", "班次数", "渠道净收", "现金差异", "POS差异", "待复核数", "已封账数"]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in self.summary_by_store(business_date):
            writer.writerow({field: csv_safe(row[field]) for field in fields})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def backup(self, path):
        data = json.dumps(self._payload(self.rows, self.events), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        rows, events = self.decode(payload)
        events = append_event(events, "恢复", "", "本机用户", "从备份恢复")
        self._commit(rows, events)


def default_data_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "MainlandBusinessTools" / "store_cash_close.json"


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        store = CashCloseStore(Path(folder) / "data.json")
        row = {
            "营业日期": "2026-11-16", "门店编号": "S001", "门店名称": "测试门店",
            "班次": "早班", "收银台编号": "POS01", "收银员": "张三",
            "备用金期初": "200", "现金销售": "1000", "微信收款": "500",
            "支付宝收款": "300", "银行卡收款": "200", "现金退款": "50",
            "电子退款": "20", "现金支出": "30", "实际现金盘点": "1120",
            "POS销售合计": "1980", "POS退款合计": "70",
        }
        record_id = store.add(row)
        assert calculate(store.rows[0])["现金差异"] == "0.00"
        store.review(record_id, "店长", "POS 对账差异已核实")
        store.close(record_id)
        assert store.rows[0]["状态"] == "已封账"
        store.reopen(record_id, "补录一张退款凭证", "店长")
        assert store.rows[0]["状态"] == "待复核"
        assert verify_audit(store.events)
    print("SELF_TEST_OK")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        require_license(PRODUCT)
        self.store = CashCloseStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1380x760")
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        actions = (
            ("新增日结", self.add_record), ("编辑", self.edit_record), ("删除", self.delete_record),
            ("复核", self.review_record), ("封账", self.close_record), ("重新开账", self.reopen_record),
            ("导入 CSV", self.import_csv), ("导出明细", self.export_csv),
            ("门店汇总", self.show_summary), ("备份", self.backup), ("恢复", self.restore),
        )
        for label, command in actions:
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=2)
        self.search = tk.StringVar()
        ttk.Label(bar, text="搜索").pack(side="left", padx=(12, 3))
        search = ttk.Entry(bar, textvariable=self.search, width=22)
        search.pack(side="left")
        self.search.trace_add("write", lambda *_: self.refresh())
        columns = ("营业日期", "门店名称", "班次", "收银台编号", "收银员", "渠道净收", "现金差异", "POS差异", "状态")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        widths = (100, 150, 75, 90, 90, 105, 95, 95, 85)
        for field, width in zip(columns, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().lower()
        for row in self.store.rows:
            haystack = " ".join(str(row.get(field, "")) for field in FIELDS).lower()
            if query and query not in haystack:
                continue
            derived = calculate(row)
            self.tree.insert(
                "", "end", iid=row["记录编号"],
                values=[
                    row["营业日期"], row["门店名称"], row["班次"], row["收银台编号"],
                    row["收银员"], derived["渠道净收"], derived["现金差异"],
                    derived["POS差异"] or "未提供 POS", row["状态"],
                ],
            )

    def _record_dialog(self, title, existing=None):
        window = tk.Toplevel(self)
        window.title(title)
        window.transient(self)
        window.grab_set()
        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        basic = ttk.Frame(notebook, padding=12)
        amounts = ttk.Frame(notebook, padding=12)
        notebook.add(basic, text="门店与班次")
        notebook.add(amounts, text="收款与盘点")
        defaults = {
            "营业日期": date.today().isoformat(), "门店编号": "", "门店名称": "",
            "班次": "全天", "收银台编号": "POS01", "收银员": "",
            **{field: "0.00" for field in AMOUNT_FIELDS},
            "POS销售合计": "", "POS退款合计": "", "备注": "",
        }
        values = {field: tk.StringVar(value=str((existing or {}).get(field, default))) for field, default in defaults.items()}
        basic_fields = ("营业日期", "门店编号", "门店名称", "班次", "收银台编号", "收银员")
        amount_fields = (
            "备用金期初", "现金销售", "微信收款", "支付宝收款", "银行卡收款", "其他收款",
            "现金退款", "电子退款", "现金支出", "实际现金盘点", "POS销售合计", "POS退款合计", "备注",
        )
        for index, field in enumerate(basic_fields):
            ttk.Label(basic, text=field).grid(row=index, column=0, sticky="w", padx=6, pady=5)
            if field == "班次":
                widget = ttk.Combobox(basic, textvariable=values[field], values=sorted(SHIFTS), state="readonly", width=32)
            else:
                widget = ttk.Entry(basic, textvariable=values[field], width=36)
            widget.grid(row=index, column=1, padx=6, pady=5)
        for index, field in enumerate(amount_fields):
            ttk.Label(amounts, text=field).grid(row=index, column=0, sticky="w", padx=6, pady=4)
            ttk.Entry(amounts, textvariable=values[field], width=36).grid(row=index, column=1, padx=6, pady=4)

        def save():
            data = {field: variable.get().strip() for field, variable in values.items()}
            try:
                if existing is None:
                    self.store.add(data)
                else:
                    self.store.update(existing["记录编号"], data)
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)
                return
            self.refresh()
            window.destroy()

        buttons = ttk.Frame(window, padding=8)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=4)
        ttk.Button(buttons, text="取消", command=window.destroy).pack(side="right", padx=4)
        window.wait_window()

    def _selected(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def add_record(self):
        self._record_dialog("新增门店日结")

    def edit_record(self):
        record_id = self._selected()
        if not record_id:
            messagebox.showinfo("编辑日结", "请先选择一条日结记录。")
            return
        row = next((item for item in self.store.rows if item["记录编号"] == record_id), None)
        if row is None:
            messagebox.showerror("编辑失败", "所选日结已不存在。")
            return
        if row["状态"] == "已封账":
            messagebox.showwarning("不能编辑", "已封账记录必须先填写原因重新开账。")
            return
        self._record_dialog("编辑门店日结", row)

    def delete_record(self):
        record_id = self._selected()
        if not record_id:
            messagebox.showinfo("删除日结", "请先选择一条日结记录。")
            return
        if not messagebox.askyesno("确认删除", "删除后无法自动撤销，确定删除所选日结记录吗？", parent=self):
            return
        try:
            self.store.delete(record_id)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc))

    def review_record(self):
        record_id = self._selected()
        if not record_id:
            messagebox.showinfo("复核日结", "请先选择一条日结记录。")
            return
        reviewer = tk.simpledialog.askstring("复核日结", "复核人：", parent=self)
        if reviewer is None:
            return
        note = tk.simpledialog.askstring("差异处理说明", "如存在差异，请说明核对结果；无差异可留空：", parent=self) or ""
        try:
            self.store.review(record_id, reviewer, note)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("复核失败", str(exc))

    def close_record(self):
        record_id = self._selected()
        if not record_id:
            messagebox.showinfo("封账", "请先选择一条日结记录。")
            return
        if not messagebox.askyesno("确认封账", "封账后不能直接修改或删除，后续修改必须填写重新开账原因。确定封账吗？", parent=self):
            return
        try:
            self.store.close(record_id)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("封账失败", str(exc))

    def reopen_record(self):
        record_id = self._selected()
        if not record_id:
            messagebox.showinfo("重新开账", "请先选择一条日结记录。")
            return
        reason = tk.simpledialog.askstring("重新开账", "请输入重新开账原因（至少 4 个字符）：", parent=self)
        if reason is None:
            return
        actor = tk.simpledialog.askstring("操作人", "操作人：", parent=self) or "本机用户"
        try:
            self.store.reopen(record_id, reason, actor)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("重新开账失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 条待复核日结")
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc))

    def show_summary(self):
        day = tk.simpledialog.askstring("门店日结汇总", "营业日期（YYYY-MM-DD），留空汇总全部日期：", parent=self) or ""
        try:
            if day:
                date.fromisoformat(day)
            rows = self.store.summary_by_store(day or None)
            if not rows:
                messagebox.showinfo("门店日结汇总", "没有符合条件的记录。")
                return
            lines = [
                f"{row['营业日期']}｜{row['门店名称']}：班次 {row['班次数']}，"
                f"净收 {row['渠道净收']} 元，现金差异 {row['现金差异']} 元，"
                f"POS差异 {row['POS差异']} 元，待复核 {row['待复核数']} 条"
                for row in rows
            ]
            messagebox.showinfo("门店日结汇总", "\n".join(lines[:30]))
        except ValueError as exc:
            messagebox.showerror("汇总失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
            except (OSError, ValueError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前门店日结数据，建议先备份。是否继续？", parent=self):
            try:
                self.store.restore(path)
                self.refresh()
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    App().mainloop()
