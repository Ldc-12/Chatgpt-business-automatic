"""Tkinter desktop UI for the offline Xianyu order profit assistant."""
import os
import sys
import tkinter as tk
from datetime import date
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_profit import (
    FIELDS, STATUSES, OrderStore, break_even_price, calculate_order,
    default_data_path, monthly_summary, self_test, sku_summary,
)

PRODUCT = "闲鱼订单利润与售后成本核算助手"
DISPLAY_COLUMNS = (
    "成交日期", "订单编号", "商品/SKU", "买家实付金额(元)",
    "售后退款(元)", "平台费用(元)", "净利润(元)", "净利率(%)", "订单状态",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼订单利润与售后成本核算助手｜大陆离线版")
        root.geometry("1480x780")
        self.store = OrderStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增订单", self.add), ("编辑订单", self.edit), ("删除订单", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("月度利润汇总", self.summary), ("SKU 汇总", self.sku_report),
            ("保本售价计算", self.break_even), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (105, 145, 210, 125, 110, 110, 110, 95, 90)
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
        ordered = sorted(self.store.rows, key=lambda row: (row["成交日期"], row["订单编号"], row["记录编号"]), reverse=True)
        total_profit = Decimal("0")
        for row in ordered:
            calc = calculate_order(row)
            total_profit += Decimal(calc["净利润(元)"])
            values = [
                row["成交日期"], row["订单编号"], row["商品/SKU"],
                calc["买家实付金额(元)"], calc["售后退款(元)"],
                calc["平台费用(元)"], calc["净利润(元)"],
                calc["净利率(%)"] or "—", row["订单状态"],
            ]
            self.tree.insert("", "end", iid=row["记录编号"], values=values)
        self.status.set(
            f"订单明细：{len(self.store.rows)} 条｜当前累计净利润：¥{total_profit:,.2f}｜"
            f"本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "记录编号": "XY-" + date.today().strftime("%Y%m%d") + "-" + uuid4().hex[:6].upper(),
                "成交日期": date.today().isoformat(),
                "买家实付金额(元)": "0.00", "商品成本(元)": "0.00",
                "平台费率(%)": "0.00", "订单状态": "已完成",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑订单" if existing else "新增订单")
        window.geometry("760x760")
        window.transient(self.root)
        window.grab_set()
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        form_frame = ttk.Frame(canvas)
        form_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        variables = {}
        for index, field in enumerate(FIELDS):
            ttk.Label(form_frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=4)
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            if field == "订单状态":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=STATUSES, state="readonly", width=44)
            else:
                state = "readonly" if existing and field == "记录编号" else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=48, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text="平台费率/固定费用仅用于估算；填写“实际平台费用”后会优先采用实际值。平台费率请按本单实际规则自行填写。",
            wraplength=600,
            foreground="#555",
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

        ttk.Button(form_frame, text="保存订单", command=save).grid(
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
        if record_id and messagebox.askyesno("确认删除", "删除所选订单记录？"):
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
                messagebox.showinfo("导入完成", f"整批导入 {count} 条订单记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("导出完成", "CSV 已保存为 UTF-8 BOM 格式")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def summary(self):
        if not self.store.rows:
            messagebox.showinfo("月度利润汇总", "请先录入订单")
            return
        reports = monthly_summary(self.store.rows)
        lines = []
        for month, item in sorted(reports.items()):
            lines.append(
                f"{month}｜订单 {item['订单数']} 笔｜售后 {item['售后订单数']} 笔\n"
                f"净收入 ¥{item['净收入(元)']}｜成本支出 ¥{item['成本支出(元)']}｜"
                f"售后回收 ¥{item['售后回收(元)']}｜净利润 ¥{item['净利润(元)']}"
            )
        messagebox.showinfo("月度利润汇总", "\n\n".join(lines))

    def sku_report(self):
        if not self.store.rows:
            messagebox.showinfo("SKU 汇总", "请先录入订单")
            return
        reports = sku_summary(self.store.rows)
        lines = [
            f"{sku}｜订单 {item['订单数']} 笔｜净收入 ¥{item['净收入(元)']}｜净利润 ¥{item['净利润(元)']}"
            for sku, item in sorted(reports.items())
        ]
        messagebox.showinfo("SKU 汇总", "\n".join(lines))

    def break_even(self):
        costs = simpledialog.askstring("保本售价", "平台费前总成本（元）：", parent=self.root)
        if costs is None:
            return
        rate = simpledialog.askstring("保本售价", "平台费率（%，按本单规则填写）：", initialvalue="0", parent=self.root)
        if rate is None:
            return
        fixed = simpledialog.askstring("保本售价", "平台固定费用（元，默认 0）：", initialvalue="0", parent=self.root)
        if fixed is None:
            return
        try:
            price = break_even_price(costs, rate, fixed)
            messagebox.showinfo("保本售价", f"建议保本售价：¥{price}\n结果按人民币分向上取整，不含额外风险缓冲。")
        except ValueError as exc:
            messagebox.showerror("计算失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "订单数据备份及 SHA256 校验值已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将整体替换当前订单，请先确认已有备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "订单数据已通过 SHA256 校验并恢复")
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
