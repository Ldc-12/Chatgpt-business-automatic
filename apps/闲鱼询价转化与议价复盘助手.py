"""Tkinter desktop UI for the offline Xianyu negotiation review ledger."""
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_negotiation import FIELDS, PRODUCT, NegotiationStore, default_data_path, followup_rows, summary_rows, self_test

DISPLAY_COLUMNS = ("商品编号", "订单编号", "商品名称", "SKU", "买家备注", "询价日期", "标价", "买家报价", "卖家回价", "成交价", "结果", "下次跟进日期")


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼询价转化与议价复盘助手｜大陆离线版")
        root.geometry("1500x780")
        self.store = NegotiationStore(default_data_path())
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增询价", self.add), ("编辑记录", self.edit), ("删除记录", self.delete),
            ("导入 CSV", self.import_csv), ("导出明细", self.export_csv),
            ("导出到期跟进", self.export_followups), ("导出商品复盘", self.export_summary),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)
        search = ttk.Frame(root, padding=(8, 0, 8, 6))
        search.pack(fill="x")
        ttk.Label(search, text="搜索商品编号/名称、订单号、SKU 或买家备注：").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.search_var, width=48)
        entry.pack(side="left", padx=6)
        entry.bind("<KeyRelease>", lambda _event: self.refresh())
        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (120, 130, 160, 100, 110, 100, 85, 85, 85, 85, 85, 105)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=70, stretch=False)
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
        query = self.search_var.get().strip().casefold()
        ordered = sorted(self.store.rows, key=lambda row: (row["询价日期"], row["商品编号"], row["SKU"], row["记录编号"]), reverse=True)
        for row in ordered:
            haystack = " ".join(row[field] for field in ("商品编号", "订单编号", "商品名称", "SKU", "买家备注", "内部备注")).casefold()
            if query and query not in haystack:
                continue
            self.tree.insert("", "end", iid=row["记录编号"], values=tuple(row[field] for field in DISPLAY_COLUMNS))
        due = len(followup_rows(self.store.rows))
        reports = summary_rows(self.store.rows)
        sold = sum(1 for row in self.store.rows if row["结果"] == "已成交")
        self.status.set(
            f"询价记录：{len(self.store.rows)}｜商品/SKU 组：{len(reports)}｜已成交：{sold}｜"
            f"今日及逾期待跟进：{due}｜本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({"询价日期": date.today().isoformat(), "标价": "100.00", "结果": "待回复"})
        window = tk.Toplevel(self.root)
        window.title("编辑询价记录" if existing else "新增询价记录")
        window.geometry("840x780")
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        variables = {}
        fields = FIELDS[1:]
        for index, field in enumerate(fields):
            ttk.Label(frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=4)
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            if field == "结果":
                widget = ttk.Combobox(frame, textvariable=variable, values=("待回复", "议价中", "已成交", "未成交", "已取消"), state="readonly", width=54)
            else:
                widget = ttk.Entry(frame, textvariable=variable, width=58)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(
            frame,
            text="成交价仅在结果为“已成交”时填写；估算毛利 = 成交价 - 商品成本 - 平台费用 - 运费成本。低于底价成交会单独计数，不会阻止记录。",
            wraplength=720, foreground="#555",
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in fields}
            try:
                if existing:
                    self.store.update(existing["记录编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(frame, text="保存记录", command=save).grid(row=len(fields) + 1, column=0, columnspan=2, pady=12)

    def add(self):
        self.form()

    def edit(self):
        record_id = self.selected_id()
        if record_id:
            row = next(item for item in self.store.rows if item["记录编号"] == record_id)
            self.form(row)

    def delete(self):
        record_id = self.selected_id()
        if record_id and messagebox.askyesno("确认删除", "删除所选询价记录？"):
            try:
                self.store.delete(record_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条询价记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def _save_csv(self, initial, exporter):
        path = filedialog.asksaveasfilename(initialfile=initial, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = exporter(path)
                messagebox.showinfo("导出完成", f"已导出 {count} 行（UTF-8 BOM，公式安全处理）")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def export_csv(self):
        self._save_csv("闲鱼询价明细.csv", self.store.export_csv)

    def export_followups(self):
        self._save_csv("闲鱼到期跟进清单.csv", self.store.export_followups_csv)

    def export_summary(self):
        self._save_csv("闲鱼商品询价转化复盘.csv", self.store.export_summary_csv)

    def backup(self):
        path = filedialog.asksaveasfilename(initialfile="闲鱼询价台账备份.json", defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "已生成带 SHA256 校验的本地备份")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前本地询价台账，建议先备份。继续？"):
            try:
                count = self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", f"已恢复 {count} 条记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def main():
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
