"""门店收货验收与差异处理助手：本地登记到货数量、验收结果和供应商差异。"""
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.store_receiving import ReceivingStore, LINE_FIELDS, RESOLUTION_STATES, self_test as core_self_test

PRODUCT = "门店收货验收与差异处理助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return base / "MainlandBusinessTools" / "store-receiving.json"


class App(tk.Tk):
    def __init__(self):
        require_license(PRODUCT)
        super().__init__()
        self.store = ReceivingStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1420x780")
        self.minsize(1120, 650)
        self.search_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="")

        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self,
            text="记录采购到货、短缺、超收、破损和拒收；验收金额不自动计入超收数量。",
            foreground="#666",
        ).pack(anchor="w", padx=18, pady=(0, 8))
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=18, pady=(0, 10))

        filters = ttk.Frame(self, padding=(18, 0))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="搜索收货单 / 采购单 / SKU / 供应商").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=32).pack(side="left", padx=6)
        ttk.Button(filters, text="刷新", command=self.refresh).pack(side="left", padx=4)

        actions = ttk.Frame(self, padding=(18, 0))
        actions.pack(fill="x", pady=(0, 8))
        buttons = [
            ("新增收货明细", self.add_line),
            ("修改选中明细", self.edit_line),
            ("导入 CSV", self.import_csv),
            ("导出全部 CSV", self.export_csv),
            ("导出差异报告", self.export_difference_csv),
            ("导出供应商汇总", self.export_supplier_summary_csv),
            ("导出期间供应商汇总", self.export_supplier_summary_period_csv),
            ("导出供应商 SKU 差异分析", self.export_supplier_sku_summary_csv),
            ("备份", self.backup),
            ("恢复", self.restore),
        ]
        for label, command in buttons:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6), pady=4)

        columns = (
            "明细编号", "收货单号", "采购单号", "供应商", "到货日期", "SKU", "商品名称",
            "订购数量", "实收数量", "验收合格数量", "短缺数量", "超收数量",
            "破损数量", "拒收数量", "验收金额", "差异状态", "差异处理",
        )
        table_frame = ttk.Frame(self, padding=(18, 0))
        table_frame.pack(fill="both", expand=True, pady=(0, 12))
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=22)
        widths = {
            "明细编号": 130, "收货单号": 120, "采购单号": 110, "供应商": 120,
            "到货日期": 95, "SKU": 95, "商品名称": 130, "订购数量": 82,
            "实收数量": 82, "验收合格数量": 100, "短缺数量": 82, "超收数量": 82,
            "破损数量": 82, "拒收数量": 82, "验收金额": 95, "差异状态": 82, "差异处理": 82,
        }
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
            raise ValueError("请先在列表中选择一条收货明细")
        return self.table.item(selected[0], "values")[0]

    def refresh(self):
        summary = self.store.summary()
        self.summary_var.set(
            f"收货单：{summary['收货单数']}    明细：{summary['收货明细数']}    "
            f"有差异：{summary['差异明细数']}    待处理：{summary['待处理差异']}    "
            f"短缺：{summary['短缺数量']}    超收：{summary['超收数量']}    "
            f"验收金额：¥{summary['验收金额']}    差异金额：¥{summary['差异金额']}"
        )
        needle = self.search_var.get().strip().casefold()
        report = {row["明细编号"]: row for row in self.store.report_rows()}
        for child in self.table.get_children():
            self.table.delete(child)
        for line in self.store.search_lines(needle):
            row = report[line["明细编号"]]
            self.table.insert("", "end", values=tuple(row.get(column, "") for column in self.table["columns"]))

    def line_dialog(self, existing=None):
        values = dict(existing or {
            "明细编号": "",
            "收货单号": "",
            "采购单号": "",
            "供应商": "",
            "到货日期": date.today().isoformat(),
            "经办人": "",
            "备注": "",
            "SKU": "",
            "商品名称": "",
            "订购数量": "1",
            "实收数量": "1",
            "破损数量": "0",
            "拒收数量": "0",
            "采购单价": "0",
            "差异原因": "",
            "差异处理": "",
            "处理备注": "",
        })
        window = tk.Toplevel(self)
        window.title("修改收货明细" if existing else "新增收货明细")
        window.geometry("640x680")
        window.transient(self)
        window.grab_set()
        variables = {}
        for index, field in enumerate(LINE_FIELDS):
            ttk.Label(window, text=field).grid(row=index, column=0, sticky="e", padx=10, pady=4)
            variable = tk.StringVar(value=str(values.get(field, "")))
            if field == "差异处理":
                widget = ttk.Combobox(window, textvariable=variable, values=("", *RESOLUTION_STATES), state="readonly", width=40)
            else:
                widget = ttk.Entry(window, textvariable=variable, width=43)
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

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 条收货明细")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_csv(path)
            messagebox.showinfo("导出完成", f"已导出 {len(self.store.lines)} 条收货明细")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_difference_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            rows = self.store.difference_rows()
            self.store.export_difference_csv(path)
            messagebox.showinfo("导出完成", f"已导出 {len(rows)} 条差异明细")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_supplier_summary_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            rows = self.store.supplier_summary_rows()
            self.store.export_supplier_summary_csv(path)
            messagebox.showinfo("导出完成", f"已导出 {len(rows)} 家供应商的汇总")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_supplier_summary_period_csv(self):
        default_start = date.today().replace(day=1).isoformat()
        default_end = date.today().isoformat()
        start_date = simpledialog.askstring(
            "供应商汇总开始日期",
            "请输入到货日期起始日（YYYY-MM-DD；留空表示不限）：",
            initialvalue=default_start,
            parent=self,
        )
        if start_date is None:
            return
        end_date = simpledialog.askstring(
            "供应商汇总结束日期",
            "请输入到货日期截止日（YYYY-MM-DD；留空表示不限）：",
            initialvalue=default_end,
            parent=self,
        )
        if end_date is None:
            return
        try:
            rows = self.store.supplier_summary_rows(start_date, end_date)
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv")],
            )
            if not path:
                return
            self.store.export_supplier_summary_period_csv(path, start_date, end_date)
            messagebox.showinfo(
                "导出完成",
                f"统计期间：{start_date.strip() or '不限'} 至 {end_date.strip() or '不限'}\n"
                f"已导出 {len(rows)} 家供应商的汇总",
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_supplier_sku_summary_csv(self):
        default_start = date.today().replace(day=1).isoformat()
        default_end = date.today().isoformat()
        start_date = simpledialog.askstring(
            "供应商 SKU 分析开始日期",
            "请输入到货日期起始日（YYYY-MM-DD；留空表示不限）：",
            initialvalue=default_start,
            parent=self,
        )
        if start_date is None:
            return
        end_date = simpledialog.askstring(
            "供应商 SKU 分析结束日期",
            "请输入到货日期截止日（YYYY-MM-DD；留空表示不限）：",
            initialvalue=default_end,
            parent=self,
        )
        if end_date is None:
            return
        try:
            pending_only = messagebox.askyesno(
                "筛选待处理差异",
                "是否只导出仍处于“待处理”状态的供应商-SKU组合？\n"
                "选择“否”将导出全部组合。",
                parent=self,
            )
            rows = self.store.supplier_sku_summary_rows(
                start_date,
                end_date,
                pending_only=pending_only,
            )
            suggested_name = (
                "供应商SKU差异分析_仅待处理.csv"
                if pending_only else "供应商SKU差异分析_全部.csv"
            )
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                initialfile=suggested_name,
                filetypes=[("CSV 文件", "*.csv")],
            )
            if not path:
                return
            self.store.export_supplier_sku_summary_csv(
                path,
                start_date,
                end_date,
                pending_only=pending_only,
            )
            scope = "仅待处理" if pending_only else "全部"
            messagebox.showinfo(
                "导出完成",
                f"统计期间：{start_date.strip() or '不限'} 至 {end_date.strip() or '不限'}\n"
                f"筛选范围：{scope}\n已导出 {len(rows)} 个供应商-SKU 组合；"
                "已按待处理差异金额优先排序",
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

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
        if not messagebox.askyesno("确认恢复", "恢复会替换当前全部收货明细，是否继续？"):
            return
        try:
            count = self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", f"已恢复 {count} 条收货明细")
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        core_self_test()
        print("SELF_TEST_OK", flush=True)
        os._exit(0)
    App().mainloop()
