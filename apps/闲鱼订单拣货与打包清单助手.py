"""Tkinter desktop UI for the offline Xianyu picking and packing checklist."""
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_pick_pack import FIELDS, PRODUCT, PickPackStore, default_data_path, line_status, packing_progress, self_test

DISPLAY_COLUMNS = ("订单编号", "商品名称", "SKU", "规格/成色", "数量", "已拣数量", "已打包数量", "包裹编号", "处理状态")


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼订单拣货与打包清单助手｜大陆离线版")
        root.geometry("1380x760")
        self.store = PickPackStore(default_data_path())
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增明细", self.add), ("编辑进度", self.edit), ("删除明细", self.delete),
            ("导入 CSV", self.import_csv), ("导出明细", self.export_csv),
            ("导出拣货汇总", self.export_picking), ("导出打包清单", self.export_packing),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)
        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (145, 180, 125, 110, 70, 85, 90, 130, 90)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=75, stretch=False)
        yscroll = ttk.Scrollbar(area, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(area, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=8).pack(fill="x")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        ordered = sorted(self.store.rows, key=lambda row: (row["订单日期"], row["订单编号"], row["SKU"], row["规格/成色"]))
        for row in ordered:
            self.tree.insert("", "end", iid=row["明细编号"], values=(
                row["订单编号"], row["商品名称"], row["SKU"], row["规格/成色"],
                row["数量"], row["已拣数量"], row["已打包数量"], row["包裹编号"], line_status(row),
            ))
        report = packing_progress(self.store.rows)
        self.status.set(
            f"订单：{report['订单数']}｜明细：{report['明细行数']}｜需求：{report['需求数量']} 件｜"
            f"已拣：{report['已拣数量']}｜已打包：{report['已打包数量']}｜待拣：{report['待拣数量']}｜"
            f"待打包：{report['待打包数量']}｜本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({"数量": "1", "订单日期": date.today().isoformat()})
        window = tk.Toplevel(self.root)
        window.title("编辑拣货明细" if existing else "新增拣货明细")
        window.geometry("720x610")
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        variables = {}
        fields = FIELDS[1:]
        for index, field in enumerate(fields):
            ttk.Label(frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=5)
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            ttk.Entry(frame, textvariable=variable, width=58).grid(row=index, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(frame, text="同一 SKU/规格会合并到拣货汇总。已打包数量不得超过已拣数量，已拣数量不得超过订单数量。", wraplength=620, foreground="#555").grid(row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in fields}
            try:
                if existing:
                    self.store.update(existing["明细编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(frame, text="保存明细", command=save).grid(row=len(fields) + 1, column=0, columnspan=2, pady=12)

    def add(self):
        self.form()

    def edit(self):
        line_id = self.selected_id()
        if line_id:
            row = next(item for item in self.store.rows if item["明细编号"] == line_id)
            self.form(row)

    def delete(self):
        line_id = self.selected_id()
        if line_id and messagebox.askyesno("确认删除", "删除所选订单商品明细？"):
            try:
                self.store.delete(line_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条明细")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(initialfile="闲鱼订单明细.csv", defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.export_csv(path)
                messagebox.showinfo("导出完成", f"已导出 {count} 条明细（UTF-8 BOM）")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def export_picking(self):
        path = filedialog.asksaveasfilename(initialfile="SKU拣货汇总.csv", defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.export_picking_list_csv(path)
                messagebox.showinfo("导出完成", f"已导出 {count} 个 SKU/规格组")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def export_packing(self):
        path = filedialog.asksaveasfilename(initialfile="订单打包清单.csv", defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.export_packing_list_csv(path)
                messagebox.showinfo("导出完成", f"已导出 {count} 条打包明细")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "订单拣货台账和 SHA256 校验值已保存")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将整体替换当前拣货台账，是否继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "拣货台账已通过 SHA256 校验并恢复")
            except (ValueError, OSError) as exc:
                messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()
