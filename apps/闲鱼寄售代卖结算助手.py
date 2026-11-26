"""Tkinter UI for the offline Xianyu consignment settlement ledger."""
import os
import sys
import tkinter as tk
from datetime import date
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_consignment import (
    FIELDS, STATUSES, ConsignmentStore, calculate_item,
    default_data_path, owner_summary, self_test,
)

PRODUCT = "闲鱼寄售代卖结算助手"
DISPLAY_COLUMNS = (
    "货主名称", "商品编号/SKU", "商品名称", "商品状态", "结算状态",
    "实际成交金额(元)", "待结算金额(元)", "卖家毛利(元)", "结算期限",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼寄售代卖结算助手｜大陆离线版")
        root.geometry("1420x760")
        self.store = ConsignmentStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增寄售", self.add), ("编辑记录", self.edit), ("删除记录", self.delete),
            ("货主结算汇总", self.summary), ("导入 CSV", self.import_csv),
            ("导出 CSV", self.export_csv), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=3)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (130, 130, 220, 90, 100, 130, 120, 120, 110)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=80, stretch=False)
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
        ordered = sorted(
            self.store.rows,
            key=lambda row: (row["收货日期"], row["货主编号"], row["记录编号"]),
            reverse=True,
        )
        due_total = Decimal("0")
        margin_total = Decimal("0")
        for row in ordered:
            calc = calculate_item(row)
            due_total += Decimal(calc["待结算金额(元)"])
            margin_total += Decimal(calc["卖家毛利(元)"])
            values = [
                row["货主名称"], row["商品编号/SKU"], row["商品名称"],
                row["商品状态"], calc["结算状态"], row["实际成交金额(元)"],
                calc["待结算金额(元)"], calc["卖家毛利(元)"], row["结算期限"],
            ]
            self.tree.insert("", "end", iid=row["记录编号"], values=values)
        self.status.set(
            f"寄售记录：{len(self.store.rows)} 条｜待结算合计：¥{due_total:,.2f}｜"
            f"已售记录卖家毛利：¥{margin_total:,.2f}｜本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "记录编号": "CY-" + date.today().strftime("%Y%m%d") + "-" + uuid4().hex[:6].upper(),
                "收货日期": date.today().isoformat(),
                "约定上架价(元)": "0.00",
                "货主约定结算额(元)": "0.00",
                "当前标价(元)": "0.00",
                "商品状态": "待上架",
                "实际成交金额(元)": "0.00",
                "平台实际费用(元)": "0.00",
                "发货运费(元)": "0.00",
                "包装整备成本(元)": "0.00",
                "已结算金额(元)": "0.00",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑寄售记录" if existing else "新增寄售记录")
        window.geometry("780x760")
        window.transient(self.root)
        window.grab_set()
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        form_frame = ttk.Frame(canvas)
        form_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        variables = {}
        for index, field in enumerate(FIELDS):
            ttk.Label(form_frame, text=field).grid(
                row=index, column=0, sticky="e", padx=8, pady=4
            )
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            if field == "商品状态":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=STATUSES,
                    state="readonly", width=46,
                )
            else:
                state = "readonly" if existing and field == "记录编号" else "normal"
                widget = ttk.Entry(
                    form_frame, textvariable=variable, width=50, state=state
                )
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text=(
                "先登记货主和收货信息；售出后再填写成交金额、费用和结算记录。"
                "货主约定结算额是双方约定的应付金额，不会由软件自动改写。"
            ),
            wraplength=620, foreground="#555",
        ).grid(row=len(FIELDS), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update(existing["记录编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(form_frame, text="保存寄售记录", command=save).grid(
            row=len(FIELDS) + 1, column=0, columnspan=2, pady=12
        )

    def add(self):
        self.form()

    def edit(self):
        record_id = self.selected_id()
        if record_id:
            row = next(item for item in self.store.rows if item["记录编号"] == record_id)
            self.form(row)

    def delete(self):
        record_id = self.selected_id()
        if record_id and messagebox.askyesno("确认删除", "删除所选寄售记录？"):
            try:
                self.store.delete(record_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def summary(self):
        if not self.store.rows:
            messagebox.showinfo("货主结算汇总", "请先录入寄售记录")
            return
        reports = owner_summary(self.store.rows)
        lines = []
        for owner_id, item in sorted(reports.items()):
            lines.append(
                f"{item['货主名称']}（{owner_id}）｜商品 {item['商品数']} 件｜"
                f"已售 {item['已售数']} 件｜已退回 {item['已退回数']} 件\n"
                f"应结算 ¥{item['应结算金额(元)']}｜已结算 ¥{item['已结算金额(元)']}｜"
                f"待结算 ¥{item['待结算金额(元)']}｜逾期 {item['逾期待结算数']} 笔｜"
                f"卖家毛利 ¥{item['卖家毛利(元)']}"
            )
        messagebox.showinfo("货主结算汇总", "\n\n".join(lines))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条寄售记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")]
        )
        if path:
            try:
                count = self.store.export_csv(path)
                messagebox.showinfo("导出完成", f"已导出 {count} 条寄售记录（UTF-8 BOM）")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")]
        )
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "寄售数据备份及 SHA256 校验值已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno(
            "确认恢复", "恢复将整体替换当前寄售记录，请先确认已有备份。继续？"
        ):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "寄售数据已通过 SHA256 校验并恢复")
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
