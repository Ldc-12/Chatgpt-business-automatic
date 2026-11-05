"""Offline expense reimbursement manager for Mainland Windows users."""
import csv
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "费用报销管理助手"
FIELDS = [
    "报销单号", "发生日期", "报销人", "部门/项目", "费用类别", "费用说明",
    "金额(元)", "支付方式", "发票状态", "报销状态", "付款日期", "备注",
]
CATEGORIES = ["差旅交通", "餐饮招待", "办公用品", "通讯网络", "住宿", "业务采购", "培训会议", "其他"]
PAYMENT_METHODS = ["个人垫付", "公司转账", "现金", "银行卡", "微信/支付宝", "其他"]
INVOICE_STATES = ["有发票", "无发票", "待补票"]
STATUSES = ["待提交", "已提交", "已批准", "已付款", "已驳回"]
BACKUP_FORMAT = "mainland-expense-reimbursement-backup"
BACKUP_VERSION = 1


def _date(value, field, required=False):
    value = str(value or "").strip()
    if not value:
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式")
    return value


def _amount(value):
    try:
        amount = Decimal(str(value).replace(",", "").replace("，", "").strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("金额必须是有效数字") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("金额必须大于 0")
    return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def normalize_record(row):
    if not isinstance(row, dict):
        raise ValueError("报销记录格式错误")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    required = ["报销单号", "发生日期", "报销人", "费用类别", "费用说明"]
    for field in required:
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["发生日期"] = _date(item["发生日期"], "发生日期", required=True)
    item["付款日期"] = _date(item["付款日期"], "付款日期")
    item["金额(元)"] = _amount(item["金额(元)"])
    if item["费用类别"] not in CATEGORIES:
        raise ValueError("费用类别不在支持范围内")
    if item["支付方式"] and item["支付方式"] not in PAYMENT_METHODS:
        raise ValueError("支付方式不在支持范围内")
    if item["发票状态"] not in INVOICE_STATES:
        raise ValueError("发票状态不正确")
    if item["报销状态"] not in STATUSES:
        raise ValueError("报销状态不正确")
    if item["报销状态"] == "已付款" and not item["付款日期"]:
        raise ValueError("已付款记录必须填写付款日期")
    return item


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="")
    temp.replace(path)


class ExpenseStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def check_unique(rows):
        ids = [row["报销单号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("报销单号重复")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("报销数据文件格式错误")
            rows = [normalize_record(row) for row in data]
            self.check_unique(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"报销数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        self.check_unique(self.rows)
        atomic_write(
            self.path,
            json.dumps(self.rows, ensure_ascii=False, indent=2),
        )

    def next_id(self, on_date=None):
        day = on_date or date.today().isoformat()
        day = _date(day, "发生日期", required=True)
        prefix = "BX" + day.replace("-", "") + "-"
        numbers = []
        for row in self.rows:
            value = row["报销单号"]
            if value.startswith(prefix):
                suffix = value[len(prefix):]
                if suffix.isdigit():
                    numbers.append(int(suffix))
        return f"{prefix}{max(numbers, default=0) + 1:04d}"

    def add(self, row):
        item = normalize_record(row)
        if any(existing["报销单号"] == item["报销单号"] for existing in self.rows):
            raise ValueError("报销单号已存在")
        previous = self.rows
        self.rows = previous + [item]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise
        return item["报销单号"]

    def update(self, old_id, row):
        item = normalize_record(row)
        if any(existing["报销单号"] == item["报销单号"] and existing["报销单号"] != old_id
               for existing in self.rows):
            raise ValueError("报销单号已存在")
        index = next((i for i, existing in enumerate(self.rows)
                      if existing["报销单号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的报销记录")
        previous = self.rows[index]
        self.rows[index] = item
        try:
            self.save()
        except Exception:
            self.rows[index] = previous
            raise

    def delete(self, expense_id):
        previous = self.rows
        self.rows = [row for row in self.rows if row["报销单号"] != expense_id]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(FIELDS) or set(headers) != set(FIELDS):
                raise ValueError("CSV 必须且只能包含全部规定字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余列")
                try:
                    incoming.append(normalize_record(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self.check_unique(incoming)
        existing = {row["报销单号"] for row in self.rows}
        duplicates = existing.intersection(row["报销单号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在报销单号，未导入任何数据：" + "、".join(sorted(duplicates)))
        if incoming:
            previous = self.rows
            self.rows = previous + incoming
            try:
                self.save()
            except Exception:
                self.rows = previous
                raise
        return len(incoming)

    def export_csv(self, path, rows=None):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(self.rows if rows is None else rows)
        atomic_write(path, "\ufeff" + output.getvalue())

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "records": self.rows,
        }
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        source = payload.get("records")
        if not isinstance(source, list):
            raise ValueError("备份记录列表格式错误")
        rows = [normalize_record(row) for row in source]
        self.check_unique(rows)
        previous = self.rows
        self.rows = rows
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise


def filter_records(rows, keyword="", month="", status="全部", category="全部"):
    q = str(keyword or "").casefold().strip()
    month = str(month or "").strip()
    result = []
    for row in rows:
        if month and not row["发生日期"].startswith(month):
            continue
        if status != "全部" and row["报销状态"] != status:
            continue
        if category != "全部" and row["费用类别"] != category:
            continue
        if q and q not in " ".join(str(row[field]) for field in FIELDS).casefold():
            continue
        result.append(row)
    return result


def summarize(rows):
    total = sum((Decimal(row["金额(元)"]) for row in rows), Decimal("0.00"))
    pending = sum((Decimal(row["金额(元)"]) for row in rows
                   if row["报销状态"] in ("待提交", "已提交", "已批准")), Decimal("0.00"))
    paid = sum((Decimal(row["金额(元)"]) for row in rows
                if row["报销状态"] == "已付款"), Decimal("0.00"))
    return {"count": len(rows), "total": total, "pending": pending, "paid": paid}


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "reimbursements.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("费用报销管理助手｜大陆版")
        root.geometry("1380x740")
        self.store = ExpenseStore(default_data_path())

        toolbar = ttk.Frame(root, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        actions = [
            ("新增报销", self.add), ("编辑", self.edit), ("删除", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, command in actions:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)

        filters = ttk.Frame(root, padding=(8, 4, 8, 8))
        filters.pack(fill="x")
        self.keyword = tk.StringVar()
        self.month = tk.StringVar()
        self.status = tk.StringVar(value="全部")
        self.category = tk.StringVar(value="全部")
        ttk.Label(filters, text="搜索").pack(side="left")
        search = ttk.Entry(filters, textvariable=self.keyword, width=24)
        search.pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="月份").pack(side="left")
        month_entry = ttk.Entry(filters, textvariable=self.month, width=10)
        month_entry.pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="状态").pack(side="left")
        ttk.Combobox(filters, textvariable=self.status, values=["全部"] + STATUSES,
                     state="readonly", width=10).pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="类别").pack(side="left")
        ttk.Combobox(filters, textvariable=self.category, values=["全部"] + CATEGORIES,
                     state="readonly", width=12).pack(side="left", padx=(4, 12))
        ttk.Button(filters, text="清空筛选", command=self.clear_filters).pack(side="left")

        table_frame = ttk.Frame(root, padding=(8, 0, 8, 0))
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=FIELDS, show="headings")
        widths = [145, 95, 90, 110, 100, 180, 95, 100, 85, 85, 95, 160]
        for field, width in zip(FIELDS, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, minwidth=70, stretch=True)
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, anchor="w", padding=10).pack(fill="x")
        for variable in (self.keyword, self.month, self.status, self.category):
            variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def clear_filters(self):
        self.keyword.set("")
        self.month.set("")
        self.status.set("全部")
        self.category.set("全部")

    def visible_rows(self):
        return filter_records(self.store.rows, self.keyword.get(), self.month.get(),
                              self.status.get(), self.category.get())

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.visible_rows()
        for row in rows:
            self.tree.insert("", "end", iid=row["报销单号"], values=[row[field] for field in FIELDS])
        totals = summarize(rows)
        self.summary.set(
            f"当前筛选：{totals['count']} 笔    "
            f"报销总额：¥{totals['total']:.2f}    "
            f"待处理金额：¥{totals['pending']:.2f}    "
            f"已付款金额：¥{totals['paid']:.2f}    "
            f"数据位置：{self.store.path}"
        )

    def form(self, existing=None):
        old_id = existing["报销单号"] if existing else ""
        win = tk.Toplevel(self.root)
        win.title("报销记录")
        win.transient(self.root)
        win.grab_set()
        initial = dict(existing or {})
        initial.setdefault("报销单号", self.store.next_id())
        initial.setdefault("发生日期", date.today().isoformat())
        initial.setdefault("报销人", "")
        initial.setdefault("部门/项目", "")
        initial.setdefault("费用类别", CATEGORIES[0])
        initial.setdefault("费用说明", "")
        initial.setdefault("金额(元)", "")
        initial.setdefault("支付方式", PAYMENT_METHODS[0])
        initial.setdefault("发票状态", INVOICE_STATES[0])
        initial.setdefault("报销状态", STATUSES[0])
        initial.setdefault("付款日期", "")
        initial.setdefault("备注", "")
        variables = {field: tk.StringVar(value=str(initial[field])) for field in FIELDS}

        for index, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=10, pady=5, sticky="e")
            if field == "报销单号":
                entry = ttk.Entry(win, textvariable=variables[field], width=38, state="readonly")
                entry.grid(row=index, column=1, padx=10, pady=5, sticky="w")
            elif field == "费用类别":
                ttk.Combobox(win, textvariable=variables[field], values=CATEGORIES,
                             state="readonly", width=35).grid(row=index, column=1, padx=10, pady=5, sticky="w")
            elif field == "支付方式":
                ttk.Combobox(win, textvariable=variables[field], values=PAYMENT_METHODS,
                             state="readonly", width=35).grid(row=index, column=1, padx=10, pady=5, sticky="w")
            elif field == "发票状态":
                ttk.Combobox(win, textvariable=variables[field], values=INVOICE_STATES,
                             state="readonly", width=35).grid(row=index, column=1, padx=10, pady=5, sticky="w")
            elif field == "报销状态":
                ttk.Combobox(win, textvariable=variables[field], values=STATUSES,
                             state="readonly", width=35).grid(row=index, column=1, padx=10, pady=5, sticky="w")
            else:
                ttk.Entry(win, textvariable=variables[field], width=38).grid(
                    row=index, column=1, padx=10, pady=5, sticky="w")

        ttk.Label(win, text="日期格式：YYYY-MM-DD；金额填写人民币元。").grid(
            row=len(FIELDS), column=0, columnspan=2, padx=10, pady=4)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update(old_id, row)
                else:
                    self.store.add(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(win, text="保存记录", command=save).grid(
            row=len(FIELDS) + 1, column=0, columnspan=2, pady=10)

    def add(self):
        self.form()

    def edit(self):
        selected = self.tree.selection()
        if selected:
            row = next((item for item in self.store.rows if item["报销单号"] == selected[0]), None)
            if row:
                self.form(row)

    def delete(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno("确认删除", "删除选中的报销记录？"):
            try:
                self.store.delete(selected[0])
                self.refresh()
            except OSError as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 笔报销记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path, self.visible_rows())
                messagebox.showinfo("导出完成", "当前筛选记录已导出为 UTF-8 CSV")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "完整报销数据已备份")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换本机全部报销记录，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.clear_filters()
                self.refresh()
                messagebox.showinfo("恢复完成", "报销数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    with tempfile.TemporaryDirectory() as folder:
        store = ExpenseStore(Path(folder) / "expenses.json")
        record = {
            "报销单号": store.next_id("2026-01-02"),
            "发生日期": "2026-01-02",
            "报销人": "测试用户",
            "部门/项目": "测试项目",
            "费用类别": "办公用品",
            "费用说明": "测试打印纸",
            "金额(元)": "12.345",
            "支付方式": "个人垫付",
            "发票状态": "有发票",
            "报销状态": "待提交",
            "付款日期": "",
            "备注": "",
        }
        store.add(record)
        assert store.rows[0]["金额(元)"] == "12.35"
        backup = Path(folder) / "backup.json"
        store.backup(backup)
        store.export_csv(Path(folder) / "expenses.csv")
        assert len(ExpenseStore(Path(folder) / "expenses.json").rows) == 1
        store.restore(backup)
        assert summarize(store.rows)["total"] == Decimal("12.35")
    if sys.stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
