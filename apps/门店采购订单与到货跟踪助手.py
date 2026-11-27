"""门店采购订单与到货跟踪助手：本地跟踪采购明细、分批到货和逾期缺口。"""
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.store_purchase_orders import PurchaseOrderStore, LINE_FIELDS, RECEIPT_FIELDS, self_test as core_self_test

PRODUCT = "门店采购订单与到货跟踪助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return base / "MainlandBusinessTools" / "store-purchase-orders.json"


class App(tk.Tk):
    def __init__(self):
        require_license(PRODUCT)
        super().__init__()
        self.store = PurchaseOrderStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1500x800")
        self.minsize(1180, 650)
        self.search_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        ttk.Label(self, text="跟踪采购下单、分批到货、破损/拒收和逾期未齐；不自动生成付款或会计凭证。", foreground="#666").pack(anchor="w", padx=18, pady=(0, 8))
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=18, pady=(0, 10))
        filters = ttk.Frame(self, padding=(18, 0))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="搜索采购单 / 供应商 / SKU").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=32).pack(side="left", padx=6)
        ttk.Button(filters, text="刷新", command=self.refresh).pack(side="left", padx=4)
        actions = ttk.Frame(self, padding=(18, 0))
        actions.pack(fill="x", pady=(0, 8))
        buttons = [
            ("新增采购明细", self.add_line), ("修改选中明细", self.edit_line),
            ("登记分批到货", self.record_receipt), ("导入采购明细 CSV", self.import_lines_csv),
            ("导入到货记录 CSV", self.import_receipts_csv), ("导出采购明细", self.export_lines_csv),
            ("导出到货记录", self.export_receipts_csv), ("导出到货状态报告", self.export_report_csv),
            ("导出供应商汇总", self.export_supplier_summary_csv), ("备份", self.backup), ("恢复", self.restore),
        ]
        for label, command in buttons:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6), pady=4)
        columns = ("采购单号", "供应商", "预计到货日期", "SKU", "商品名称", "订购数量", "合格到货", "破损数量", "拒收数量", "剩余待到货", "待到货金额", "状态")
        table_frame = ttk.Frame(self, padding=(18, 0))
        table_frame.pack(fill="both", expand=True, pady=(0, 12))
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=22)
        widths = {"采购单号": 115, "供应商": 120, "预计到货日期": 105, "SKU": 95, "商品名称": 140, "订购数量": 82, "合格到货": 82, "破损数量": 82, "拒收数量": 82, "剩余待到货": 95, "待到货金额": 100, "状态": 110}
        for column in columns:
            self.table.heading(column, text=column)
            self.table.column(column, width=widths[column], anchor="center", stretch=False)
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.refresh()

    def selected_line_id(self):
        selected = self.table.selection()
        if not selected:
            raise ValueError("请先在列表中选择一条采购明细")
        return selected[0]

    def refresh(self):
        summary = self.store.summary()
        self.summary_var.set(
            f"采购单：{summary['采购单数']}    明细：{summary['采购明细数']}    "
            f"逾期未齐：{summary['逾期未齐明细']}    部分到货：{summary['部分到货明细']}    "
            f"待到货：{summary['待到货数量']}    待到货金额：¥{summary['待到货金额']}"
        )
        report = {row["明细编号"]: row for row in self.store.report_rows()}
        for child in self.table.get_children():
            self.table.delete(child)
        for line in self.store.search_lines(self.search_var.get().strip()):
            row = report[line["明细编号"]]
            values = (row["采购单号"], row["供应商"], row["预计到货日期"], row["SKU"], row["商品名称"], row["订购数量"], row["合格到货"], row["破损数量"], row["拒收数量"], row["剩余待到货"], row["待到货金额"], row["状态"])
            self.table.insert("", "end", iid=line["明细编号"], values=values)

    def line_dialog(self, existing=None):
        values = dict(existing or {
            "明细编号": "", "采购单号": "", "供应商": "",
            "下单日期": date.today().isoformat(), "预计到货日期": date.today().isoformat(),
            "采购员": "", "SKU": "", "商品名称": "", "订购数量": "1", "采购单价": "0", "备注": "",
        })
        window = tk.Toplevel(self)
        window.title("修改采购明细" if existing else "新增采购明细")
        window.geometry("650x520")
        window.transient(self)
        window.grab_set()
        variables = {}
        for index, field in enumerate(LINE_FIELDS):
            ttk.Label(window, text=field).grid(row=index, column=0, sticky="e", padx=10, pady=4)
            variable = tk.StringVar(value=str(values.get(field, "")))
            widget = ttk.Entry(window, textvariable=variable, width=48)
            if existing and field == "明细编号":
                widget.configure(state="readonly")
            widget.grid(row=index, column=1, sticky="ew", padx=10, pady=4)
            variables[field] = variable
        def save():
            row = {field: variable.get() for field, variable in variables.items()}
            try:
                if existing:
                    self.store.update_line(existing["明细编号"], row)
                else:
                    self.store.add_line(row)
                window.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)
        ttk.Button(window, text="保存", command=save).grid(row=len(LINE_FIELDS), column=1, sticky="e", padx=10, pady=12)
        window.columnconfigure(1, weight=1)

    def add_line(self):
        self.line_dialog()

    def edit_line(self):
        try:
            line_id = self.selected_line_id()
            existing = next(row for row in self.store.lines if row["明细编号"] == line_id)
            self.line_dialog(existing)
        except Exception as exc:
            messagebox.showwarning("无法修改", str(exc))

    def record_receipt(self):
        try:
            line_id = self.selected_line_id()
            line = next(row for row in self.store.lines if row["明细编号"] == line_id)
        except Exception as exc:
            messagebox.showwarning("无法登记到货", str(exc))
            return
        values = {"到货记录编号": "", "明细编号": line_id, "到货日期": date.today().isoformat(), "合格数量": "0", "破损数量": "0", "拒收数量": "0", "处理备注": ""}
        window = tk.Toplevel(self)
        window.title(f"登记到货｜{line['采购单号']}｜{line['SKU']}")
        window.geometry("560x360")
        window.transient(self)
        window.grab_set()
        variables = {}
        for index, field in enumerate(RECEIPT_FIELDS):
            ttk.Label(window, text=field).grid(row=index, column=0, sticky="e", padx=10, pady=5)
            variable = tk.StringVar(value=values[field])
            widget = ttk.Entry(window, textvariable=variable, width=42)
            if field == "明细编号":
                widget.configure(state="readonly")
            widget.grid(row=index, column=1, sticky="ew", padx=10, pady=5)
            variables[field] = variable
        def save():
            row = {field: variable.get() for field, variable in variables.items()}
            try:
                self.store.record_receipt(row)
                window.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("登记失败", str(exc), parent=window)
        ttk.Button(window, text="保存到货记录", command=save).grid(row=len(RECEIPT_FIELDS), column=1, sticky="e", padx=10, pady=12)
        window.columnconfigure(1, weight=1)

    def _import_csv(self, title, importer):
        path = filedialog.askopenfilename(title=title, filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = importer(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 条记录")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def import_lines_csv(self):
        self._import_csv("导入采购明细 CSV", self.store.import_lines_csv)

    def import_receipts_csv(self):
        self._import_csv("导入到货记录 CSV", self.store.import_receipts_csv)

    def _export_csv(self, title, exporter, count):
        path = filedialog.asksaveasfilename(title=title, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            exporter(path)
            messagebox.showinfo("导出完成", f"已导出 {count} 条记录")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_lines_csv(self):
        self._export_csv("导出采购明细", self.store.export_lines_csv, len(self.store.lines))

    def export_receipts_csv(self):
        self._export_csv("导出到货记录", self.store.export_receipts_csv, len(self.store.receipts))

    def export_report_csv(self):
        self._export_csv("导出到货状态报告", self.store.export_report_csv, len(self.store.lines))

    def export_supplier_summary_csv(self):
        self._export_csv("导出供应商汇总", self.store.export_supplier_summary_csv, len(self.store.supplier_summary_rows()))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        try:
            digest = self.store.backup(path)
            messagebox.showinfo("备份完成", f"SHA256：{digest}")
        except Exception as exc:
            messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        if not messagebox.askyesno("确认恢复", "恢复会替换当前全部采购明细和到货记录，是否继续？"):
            return
        try:
            lines, receipts = self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", f"已恢复采购明细 {lines} 条、到货记录 {receipts} 条")
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        core_self_test()
        print("SELF_TEST_OK", flush=True)
        os._exit(0)
    App().mainloop()
