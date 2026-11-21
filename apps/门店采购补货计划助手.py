"""门店采购补货与安全库存计划助手：离线记录销量并生成透明补货建议。"""
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.store_replenishment import ReplenishmentStore, ITEM_FIELDS, self_test as core_self_test

PRODUCT = "门店采购补货与安全库存计划助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return base / "MainlandBusinessTools" / "store-replenishment.json"


class App(tk.Tk):
    def __init__(self):
        require_license(PRODUCT)
        super().__init__()
        self.store = ReplenishmentStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1240x760")
        self.minsize(1080, 640)
        self.lookback_var = tk.StringVar(value="30")
        self.search_var = tk.StringVar(value="")

        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self,
            text="按本地销量、可用库存、采购提前期和安全库存天数计算补货建议；不连接供应商或电商平台。",
            foreground="#666",
        ).pack(anchor="w", padx=18, pady=(0, 10))
        self.summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=18, pady=(0, 8))

        filters = ttk.Frame(self, padding=(18, 0))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="统计天数").pack(side="left")
        ttk.Entry(filters, textvariable=self.lookback_var, width=6).pack(side="left", padx=(6, 14))
        ttk.Label(filters, text="搜索 SKU / 商品 / 供应商").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=28).pack(side="left", padx=6)
        ttk.Button(filters, text="刷新", command=self.refresh).pack(side="left", padx=6)

        actions = ttk.Frame(self, padding=(18, 0))
        actions.pack(fill="x", pady=(0, 8))
        buttons = [
            ("新增商品", self.add_item), ("修改商品", self.edit_item), ("录入销量", self.record_sale),
            ("导入商品 CSV", self.import_items), ("导入销量 CSV", self.import_sales),
            ("导出商品 CSV", self.export_items), ("导出销量 CSV", self.export_sales),
            ("导出补货计划", self.export_plan), ("备份", self.backup), ("恢复", self.restore),
        ]
        for label, command in buttons:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 5), pady=4)

        columns = ("sku", "name", "available", "average", "trigger", "target", "order", "budget", "status", "supplier")
        self.table = ttk.Treeview(self, columns=columns, show="headings", height=22)
        headings = {
            "sku": ("SKU", 110), "name": ("商品名称", 150), "available": ("可用库存", 80),
            "average": ("日均销量", 80), "trigger": ("补货触发库存", 95), "target": ("目标库存", 80),
            "order": ("建议采购量", 90), "budget": ("预计采购金额", 100), "status": ("建议状态", 100),
            "supplier": ("供应商", 120),
        }
        for key, (label, width) in headings.items():
            self.table.heading(key, text=label)
            self.table.column(key, width=width, anchor="center")
        self.table.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.refresh()

    def lookback_days(self):
        try:
            value = int(self.lookback_var.get().strip())
        except ValueError:
            raise ValueError("统计天数必须是 1 至 365 的整数") from None
        if not 1 <= value <= 365:
            raise ValueError("统计天数必须是 1 至 365 的整数")
        return value

    def selected_sku(self):
        selection = self.table.selection()
        if not selection:
            raise ValueError("请先在列表中选择一个商品")
        return self.table.item(selection[0], "values")[0]

    def refresh(self):
        try:
            days = self.lookback_days()
            rows = self.store.plan(days)
            summary = self.store.summary(days)
            self.summary_var.set(
                f"商品 SKU：{summary['商品 SKU']}    建议补货：{summary['建议补货 SKU']}    "
                f"缺少销量数据：{summary['缺少销量数据 SKU']}    预计采购金额：¥{summary['预计采购金额']}"
            )
            needle = self.search_var.get().strip().casefold()
            for child in self.table.get_children():
                self.table.delete(child)
            for row in rows:
                searchable = " ".join((row["SKU"], row["商品名称"], row["供应商"])).casefold()
                if needle and needle not in searchable:
                    continue
                self.table.insert("", "end", values=(
                    row["SKU"], row["商品名称"], row["可用库存"], row["日均销量"],
                    row["补货触发库存"], row["目标库存"], row["建议采购量"],
                    row["预计采购金额"], row["建议状态"], row["供应商"],
                ))
        except Exception as exc:
            messagebox.showerror("无法刷新", str(exc))

    def item_dialog(self, existing=None):
        values = dict(existing or {
            "SKU": "", "商品名称": "", "当前库存": "0", "已预留": "0",
            "采购提前期天数": "3", "安全库存天数": "3", "目标覆盖天数": "7",
            "整箱数量": "1", "最低起订量": "0", "采购单价": "0",
            "供应商": "", "备注": "",
        })
        window = tk.Toplevel(self)
        window.title("修改商品" if existing else "新增商品")
        window.transient(self)
        window.grab_set()
        variables = {}
        for index, field in enumerate(ITEM_FIELDS):
            ttk.Label(window, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=4)
            variable = tk.StringVar(value=str(values.get(field, "")))
            entry = ttk.Entry(window, textvariable=variable, width=38)
            if existing and field == "SKU":
                entry.configure(state="readonly")
            entry.grid(row=index, column=1, sticky="ew", padx=8, pady=4)
            variables[field] = variable

        def save():
            try:
                row = {field: variable.get() for field, variable in variables.items()}
                if existing:
                    self.store.update_item(existing["SKU"], row)
                else:
                    self.store.add_item(row)
                window.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(window, text="保存", command=save).grid(row=len(ITEM_FIELDS), column=1, sticky="e", padx=8, pady=10)
        window.columnconfigure(1, weight=1)

    def add_item(self):
        self.item_dialog()

    def edit_item(self):
        try:
            sku = self.selected_sku()
            item = next(value for value in self.store.items if value["SKU"] == sku)
            self.item_dialog(item)
        except Exception as exc:
            messagebox.showwarning("无法修改", str(exc))

    def record_sale(self):
        try:
            sku = simpledialog.askstring("录入销量", "SKU：", parent=self)
            if sku is None:
                return
            quantity = simpledialog.askstring("录入销量", "销量（允许 0，表示该日无销售）：", parent=self)
            if quantity is None:
                return
            from datetime import date as date_type
            sale_day = simpledialog.askstring("录入销量", "日期（YYYY-MM-DD）：", initialvalue=date_type.today().isoformat(), parent=self)
            if sale_day is None:
                return
            note = simpledialog.askstring("录入销量", "备注（可留空）：", parent=self) or ""
            self.store.record_sale({"SKU": sku, "销量": quantity, "日期": sale_day, "备注": note})
            self.refresh()
        except Exception as exc:
            messagebox.showerror("录入失败", str(exc))

    def import_items(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_items_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 个商品")
            except Exception as exc:
                messagebox.showerror("导入失败", str(exc))

    def import_sales(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_sales_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 条销量记录")
            except Exception as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_items(self):
        self.export_with(lambda path: self.store.export_items_csv(path), "商品 CSV")

    def export_sales(self):
        self.export_with(lambda path: self.store.export_sales_csv(path), "销量 CSV")

    def export_plan(self):
        self.export_with(lambda path: self.store.export_plan_csv(path, self.lookback_days()), "补货计划 CSV")

    def export_with(self, callback, title):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")], title=f"导出{title}")
        if path:
            try:
                callback(path)
                messagebox.showinfo("导出完成", f"已保存：{path}")
            except Exception as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                digest = self.store.backup(path)
                messagebox.showinfo("备份完成", f"SHA256：{digest}")
            except Exception as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        if not messagebox.askyesno("确认恢复", "恢复会替换当前商品和销量数据。请先确认已有备份。"):
            return
        try:
            items, sales = self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", f"已恢复 {items} 个商品、{sales} 条销量记录")
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        core_self_test()
        os._exit(0)
    App().mainloop()
