"""门店条码与价签批量打印助手：本地维护商品目录并生成 Code128 价签 PDF。"""
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.barcode_labels import BarcodeLabelStore, LINE_FIELDS, export_labels_pdf, self_test as core_self_test

PRODUCT = "门店条码与价签批量打印助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA") or str(Path.home()))
    return base / "MainlandBusinessTools" / "barcode-labels.json"


class App(tk.Tk):
    def __init__(self):
        require_license(PRODUCT)
        super().__init__()
        self.store = BarcodeLabelStore(default_data_path())
        self.current_sku = None
        self.title(PRODUCT)
        self.geometry("1180x760")
        self.minsize(980, 650)

        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self,
            text="本地商品目录 · Code128 条码 · A4 多联价签 PDF；不连接收银系统或云服务",
            foreground="#666",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        form = ttk.LabelFrame(self, text="商品信息", padding=10)
        form.pack(fill="x", padx=18, pady=5)
        self.vars = {field: tk.StringVar() for field in LINE_FIELDS}
        self.vars["打印数量"].set("1")
        fields = [
            ("SKU", 0, 0), ("商品名称", 0, 2), ("规格", 0, 4),
            ("价格", 1, 0), ("条码", 1, 2), ("打印数量", 1, 4),
        ]
        for label, row, column in fields:
            ttk.Label(form, text=label).grid(row=row, column=column, padx=5, pady=6, sticky="e")
            width = 24 if label in ("商品名称", "规格") else 18
            ttk.Entry(form, textvariable=self.vars[label], width=width).grid(
                row=row, column=column + 1, padx=5, pady=6, sticky="w"
            )

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=18, pady=6)
        actions = [
            ("新增 / 保存", self.save_item),
            ("清空表单", self.clear_form),
            ("删除选中", self.delete_selected),
            ("导入 CSV", self.import_csv),
            ("导出 CSV", self.export_csv),
            ("备份", self.backup),
            ("恢复备份", self.restore),
            ("生成价签 PDF", self.export_pdf),
        ]
        for label, command in actions:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 5))

        search_bar = ttk.Frame(self)
        search_bar.pack(fill="x", padx=18, pady=(5, 3))
        ttk.Label(search_bar, text="搜索 SKU / 商品名称 / 条码：").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(search_bar, textvariable=self.search_var, width=34)
        search.pack(side="left", padx=5)
        search.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(search_bar, text="搜索", command=self.refresh).pack(side="left")
        self.count_var = tk.StringVar()
        ttk.Label(search_bar, textvariable=self.count_var, foreground="#555").pack(side="right")

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        self.tree = ttk.Treeview(table_frame, columns=LINE_FIELDS, show="headings", height=18)
        widths = {"SKU": 100, "商品名称": 190, "规格": 130, "价格": 90, "条码": 150, "打印数量": 85}
        for field in LINE_FIELDS:
            self.tree.heading(field, text=field)
            self.tree.column(field, width=widths.get(field, 110), anchor="center")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.load_selected)
        self.refresh()

    def refresh(self):
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        rows = self.store.search_items(self.search_var.get())
        for item in rows:
            self.tree.insert("", "end", values=[item[field] for field in LINE_FIELDS])
        self.count_var.set(f"共 {len(self.store.items)} 条商品，当前显示 {len(rows)} 条")

    def clear_form(self):
        self.current_sku = None
        for variable in self.vars.values():
            variable.set("")
        self.vars["打印数量"].set("1")

    def load_selected(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        item = dict(zip(LINE_FIELDS, values))
        self.current_sku = item["SKU"]
        for field, variable in self.vars.items():
            variable.set(item[field])

    def save_item(self):
        row = {field: variable.get() for field, variable in self.vars.items()}
        try:
            if self.current_sku:
                self.store.update_item(self.current_sku, row)
                message = "商品已更新"
            else:
                self.store.add_item(row)
                message = "商品已保存"
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.clear_form()
        self.refresh()
        messagebox.showinfo("完成", message)

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一条商品记录")
            return
        sku = self.tree.item(selected[0], "values")[0]
        if not messagebox.askyesno("确认删除", f"确定删除 SKU：{sku}？"):
            return
        try:
            self.store.delete_item(sku)
        except (OSError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.clear_form()
        self.refresh()

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self.refresh()
        messagebox.showinfo("导入完成", f"成功导入 {count} 条商品记录")

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")],
            initialfile="商品价签目录.csv",
        )
        if not path:
            return
        try:
            self.store.export_csv(path)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        messagebox.showinfo("导出完成", f"CSV 已保存：\n{path}")

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")],
            initialfile="商品价签备份.json",
        )
        if not path:
            return
        try:
            self.store.backup(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("备份失败", str(exc))
            return
        messagebox.showinfo("备份完成", f"备份已保存并附带 SHA256 校验：\n{path}")

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        if not messagebox.askyesno("确认恢复", "恢复会替换当前商品目录，建议先备份当前数据。是否继续？"):
            return
        try:
            count = self.store.restore(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        self.clear_form()
        self.refresh()
        messagebox.showinfo("恢复完成", f"已恢复 {count} 条商品记录")

    def export_pdf(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")],
            initialfile="商品条码与价签.pdf",
        )
        if not path:
            return
        try:
            count = export_labels_pdf(self.store.items, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("生成失败", str(exc))
            return
        messagebox.showinfo(
            "生成完成",
            f"已生成 {count} 张价签：\n{path}\n\n请先用一张普通纸测试尺寸，再装入对应标签纸打印。",
        )


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        core_self_test()
        print("SELF_TEST_OK", flush=True)
        os._exit(0)
    App().mainloop()
