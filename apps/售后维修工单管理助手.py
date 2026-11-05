"""Offline repair work-order manager for small service shops."""
import csv
import io
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "售后维修工单管理助手"
FIELDS = [
    "工单号", "登记日期", "客户姓名", "联系电话", "设备/商品",
    "故障描述", "处理进度", "预计费用(元)", "实收金额(元)",
    "预约取件日期", "完工日期", "备注",
]
STATUSES = ["待检测", "待报价", "维修中", "待取件", "已完成", "已取消"]
BACKUP_FORMAT = "mainland-repair-work-order-backup"
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


def _money(value, field):
    try:
        amount = Decimal(str(value if value is not None else "0").replace(",", "").replace("，", "").strip() or "0")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field}必须是有效数字") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field}不能为负数或非有限数")
    try:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{field}超出可处理金额范围") from exc
    return format(rounded, "f")


def normalize_order(row):
    if not isinstance(row, dict):
        raise ValueError("工单记录格式错误")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    for field in ("工单号", "登记日期", "客户姓名", "设备/商品", "故障描述"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["登记日期"] = _date(item["登记日期"], "登记日期", required=True)
    item["预约取件日期"] = _date(item["预约取件日期"], "预约取件日期")
    item["完工日期"] = _date(item["完工日期"], "完工日期")
    if item["预约取件日期"] and item["预约取件日期"] < item["登记日期"]:
        raise ValueError("预约取件日期不能早于登记日期")
    if item["完工日期"] and item["完工日期"] < item["登记日期"]:
        raise ValueError("完工日期不能早于登记日期")
    if item["处理进度"] not in STATUSES:
        raise ValueError("处理进度不正确")
    if item["处理进度"] == "已完成" and not item["完工日期"]:
        raise ValueError("已完成工单必须填写完工日期")
    item["预计费用(元)"] = _money(item["预计费用(元)"], "预计费用")
    item["实收金额(元)"] = _money(item["实收金额(元)"], "实收金额")
    return item


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="")
    temp.replace(path)


class WorkOrderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def check_unique(rows):
        ids = [row["工单号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("工单号重复")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("工单数据文件格式错误")
            rows = [normalize_order(row) for row in data]
            self.check_unique(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"工单数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        self.check_unique(self.rows)
        atomic_write(self.path, json.dumps(self.rows, ensure_ascii=False, indent=2))

    def next_id(self, on_date=None):
        day = _date(on_date or date.today().isoformat(), "登记日期", required=True)
        prefix = "WX" + day.replace("-", "") + "-"
        numbers = []
        for row in self.rows:
            value = row["工单号"]
            if value.startswith(prefix):
                suffix = value[len(prefix):]
                if suffix.isdigit():
                    numbers.append(int(suffix))
        return f"{prefix}{max(numbers, default=0) + 1:04d}"

    def add(self, row):
        item = normalize_order(row)
        if any(existing["工单号"] == item["工单号"] for existing in self.rows):
            raise ValueError("工单号已存在")
        previous = self.rows
        self.rows = previous + [item]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise
        return item["工单号"]

    def update(self, old_id, row):
        item = normalize_order(row)
        if any(existing["工单号"] == item["工单号"] and existing["工单号"] != old_id
               for existing in self.rows):
            raise ValueError("工单号已存在")
        index = next((i for i, existing in enumerate(self.rows)
                      if existing["工单号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的工单")
        previous = self.rows[index]
        self.rows[index] = item
        try:
            self.save()
        except Exception:
            self.rows[index] = previous
            raise

    def delete(self, work_order_id):
        previous = self.rows
        self.rows = [row for row in self.rows if row["工单号"] != work_order_id]
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
                    incoming.append(normalize_order(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self.check_unique(incoming)
        existing = {row["工单号"] for row in self.rows}
        duplicates = existing.intersection(row["工单号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在工单号，未导入任何数据：" + "、".join(sorted(duplicates)))
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
            "orders": self.rows,
        }
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        source = payload.get("orders")
        if not isinstance(source, list):
            raise ValueError("备份工单列表格式错误")
        rows = [normalize_order(row) for row in source]
        self.check_unique(rows)
        previous = self.rows
        self.rows = rows
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise


def filter_orders(rows, keyword="", month="", status="全部"):
    query = str(keyword or "").casefold().strip()
    month = str(month or "").strip()
    if month and (len(month) != 7 or month[4] != "-" or not month[:4].isdigit() or not month[5:].isdigit()):
        raise ValueError("月份筛选请使用 YYYY-MM 格式")
    result = []
    for row in rows:
        if month and not row["登记日期"].startswith(month):
            continue
        if status != "全部" and row["处理进度"] != status:
            continue
        if query and query not in " ".join(str(row[field]) for field in FIELDS).casefold():
            continue
        result.append(row)
    return result


def summarize_orders(rows):
    estimated = sum((Decimal(row["预计费用(元)"]) for row in rows), Decimal("0.00"))
    received = sum((Decimal(row["实收金额(元)"]) for row in rows), Decimal("0.00"))
    return {"count": len(rows), "estimated": estimated, "received": received}


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "repair_orders.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("售后维修工单管理助手｜大陆版")
        root.geometry("1450x760")
        self.store = WorkOrderStore(default_data_path())

        toolbar = ttk.Frame(root, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        for label, command in [
            ("新建工单", self.add), ("编辑", self.edit), ("删除", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)

        filters = ttk.Frame(root, padding=(8, 4, 8, 8))
        filters.pack(fill="x")
        self.keyword = tk.StringVar()
        self.month = tk.StringVar()
        self.status = tk.StringVar(value="全部")
        ttk.Label(filters, text="搜索").pack(side="left")
        ttk.Entry(filters, textvariable=self.keyword, width=24).pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="登记月份").pack(side="left")
        ttk.Entry(filters, textvariable=self.month, width=10).pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="进度").pack(side="left")
        ttk.Combobox(filters, textvariable=self.status, values=["全部"] + STATUSES,
                     state="readonly", width=12).pack(side="left", padx=(4, 12))
        ttk.Button(filters, text="清空筛选", command=self.clear_filters).pack(side="left")

        frame = ttk.Frame(root, padding=(8, 0, 8, 0))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=FIELDS, show="headings")
        widths = [145, 95, 90, 120, 140, 210, 85, 105, 105, 110, 100, 150]
        for field, width in zip(FIELDS, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, minwidth=70, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, anchor="w", padding=10).pack(fill="x")
        for variable in (self.keyword, self.month, self.status):
            variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def visible_rows(self):
        return filter_orders(self.store.rows, self.keyword.get(), self.month.get(), self.status.get())

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            rows = self.visible_rows()
        except ValueError as exc:
            self.summary.set(str(exc))
            return
        for row in rows:
            self.tree.insert("", "end", iid=row["工单号"], values=[row[field] for field in FIELDS])
        totals = summarize_orders(rows)
        self.summary.set(
            f"当前筛选：{totals['count']} 张工单    "
            f"预计费用：¥{totals['estimated']:.2f}    "
            f"实收金额：¥{totals['received']:.2f}    "
            f"数据位置：{self.store.path}"
        )

    def clear_filters(self):
        self.keyword.set("")
        self.month.set("")
        self.status.set("全部")

    def form(self, existing=None):
        old_id = existing["工单号"] if existing else ""
        win = tk.Toplevel(self.root)
        win.title("维修工单资料")
        win.transient(self.root)
        win.grab_set()
        initial = dict(existing or {})
        initial.setdefault("工单号", self.store.next_id())
        initial.setdefault("登记日期", date.today().isoformat())
        initial.setdefault("客户姓名", "")
        initial.setdefault("联系电话", "")
        initial.setdefault("设备/商品", "")
        initial.setdefault("故障描述", "")
        initial.setdefault("处理进度", STATUSES[0])
        initial.setdefault("预计费用(元)", "0.00")
        initial.setdefault("实收金额(元)", "0.00")
        initial.setdefault("预约取件日期", "")
        initial.setdefault("完工日期", "")
        initial.setdefault("备注", "")
        variables = {field: tk.StringVar(value=str(initial[field])) for field in FIELDS}
        for index, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=10, pady=5, sticky="e")
            if field == "工单号":
                ttk.Entry(win, textvariable=variables[field], width=42, state="readonly").grid(
                    row=index, column=1, padx=10, pady=5, sticky="w")
            elif field == "处理进度":
                ttk.Combobox(win, textvariable=variables[field], values=STATUSES,
                             state="readonly", width=39).grid(
                    row=index, column=1, padx=10, pady=5, sticky="w")
            else:
                ttk.Entry(win, textvariable=variables[field], width=42).grid(
                    row=index, column=1, padx=10, pady=5, sticky="w")
        ttk.Label(win, text="日期格式 YYYY-MM-DD；金额单位为人民币元。").grid(
            row=len(FIELDS), column=0, columnspan=2, padx=10, pady=5)

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

        ttk.Button(win, text="保存工单", command=save).grid(
            row=len(FIELDS) + 1, column=0, columnspan=2, pady=10)

    def add(self):
        self.form()

    def edit(self):
        selected = self.tree.selection()
        if selected:
            row = next((item for item in self.store.rows if item["工单号"] == selected[0]), None)
            if row:
                self.form(row)

    def delete(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno("确认删除", "删除所选维修工单？"):
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
                messagebox.showinfo("导入完成", f"成功导入 {count} 张工单")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path, self.visible_rows())
                messagebox.showinfo("导出完成", "当前筛选结果已导出为 CSV")
            except (OSError, ValueError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "工单备份已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前全部工单，建议先备份。是否继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "工单数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        store = WorkOrderStore(Path(directory) / "orders.json")
        order_id = store.next_id("2026-01-02")
        store.add({
            "工单号": order_id, "登记日期": "2026-01-02", "客户姓名": "测试客户",
            "联系电话": "13800000000", "设备/商品": "测试设备", "故障描述": "无法开机",
            "处理进度": "待检测", "预计费用(元)": "12.345", "实收金额(元)": "0",
            "预约取件日期": "", "完工日期": "", "备注": "",
        })
        assert WorkOrderStore(store.path).rows[0]["预计费用(元)"] == "12.35"
        backup = Path(directory) / "orders-backup.json"
        store.backup(backup)
        store.restore(backup)
    if sys.stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
