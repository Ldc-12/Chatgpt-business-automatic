"""Tkinter desktop UI for the offline Xianyu used-goods pricing assistant."""
import os
import sys
import tkinter as tk
from datetime import date
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_pricing import (
    CATEGORIES, CONDITIONS, FIELDS, STATUSES, PriceStore,
    calculate_price, category_summary, default_data_path, generate_listing_text,
    self_test,
)

PRODUCT = "闲鱼二手商品定价与议价助手"
DISPLAY_COLUMNS = (
    "商品名称", "品类", "成色", "建议标价(元)",
    "最低接受价(元)", "标价预计净利润(元)", "上架状态",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼二手商品定价与议价助手｜大陆离线版")
        root.geometry("1320x760")
        self.store = PriceStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增商品", self.add), ("编辑商品", self.edit), ("删除商品", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("导出分析 CSV", self.export_analysis_csv),
            ("定价分析", self.analyze), ("复制上架文案", self.copy_listing),
            ("品类汇总", self.summary), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (230, 110, 110, 130, 130, 150, 100)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=90, stretch=False)
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
        ordered = sorted(self.store.rows, key=lambda row: (row["上架状态"], row["品类"], row["商品名称"]))
        total_listing = Decimal('0')
        for row in ordered:
            calc = calculate_price(row)
            total_listing += Decimal(calc["建议标价(元)"])
            values = [
                row["商品名称"], row["品类"], row["成色"],
                calc["建议标价(元)"], calc["最低接受价(元)"],
                calc["标价预计净利润(元)"], row["上架状态"],
            ]
            self.tree.insert("", "end", iid=row["商品编号"], values=values)
        self.status.set(
            f"商品记录：{len(self.store.rows)} 条｜建议标价合计：¥{total_listing:,.2f}｜"
            f"规则版本：XY-USED-PRICE-2026.11｜本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "商品编号": "XY-P-" + date.today().strftime("%Y%m%d") + "-" + os.urandom(3).hex().upper(),
                "购入日期": date.today().isoformat(),
                "品类": "手机数码", "原价(元)": "0.00", "购入成本(元)": "0.00",
                "成色": "9成新", "平台费率(%)": "0.00", "平台固定费用(元)": "0.00",
                "目标利润(元)": "0.00", "议价空间(%)": "8.00", "上架状态": "待上架",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑商品" if existing else "新增商品")
        window.geometry("820x780")
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
            if field == "品类":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=CATEGORIES, state="readonly", width=48)
            elif field == "成色":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=CONDITIONS, state="readonly", width=48)
            elif field == "上架状态":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=STATUSES, state="readonly", width=48)
            else:
                state = "readonly" if existing and field == "商品编号" else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=52, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text="同类成交中位价由你手工录入；留空时只使用版本化折旧规则。平台费率不是闲鱼官方费率，请按实际账单填写。",
            wraplength=650,
            foreground="#555",
        ).grid(row=len(FIELDS), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update(existing["商品编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(form_frame, text="保存商品", command=save).grid(
            row=len(FIELDS) + 1, column=0, columnspan=2, pady=12
        )

    def add(self):
        self.form()

    def edit(self):
        item_id = self.selected_id()
        if item_id:
            row = next(item for item in self.store.rows if item["商品编号"] == item_id)
            self.form(row)

    def delete(self):
        item_id = self.selected_id()
        if item_id and messagebox.askyesno("确认删除", "删除所选商品记录？"):
            try:
                self.store.delete(item_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条商品记录")
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

    def export_analysis_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("定价分析 CSV", "*.csv")],
        )
        if path:
            try:
                self.store.export_analysis_csv(path)
                messagebox.showinfo(
                    "导出完成",
                    f"已导出 {len(self.store.rows)} 条定价分析。报告包含最低接受价和利润底线，请勿直接发给买家。",
                )
            except (ValueError, OSError) as exc:
                messagebox.showerror("分析导出失败", str(exc))

    def analyze(self):
        item_id = self.selected_id()
        if not item_id:
            messagebox.showinfo("定价分析", "请先选择一件商品")
            return
        row = next(item for item in self.store.rows if item["商品编号"] == item_id)
        result = calculate_price(row)
        messagebox.showinfo(
            "定价分析",
            f"规则版本：{result['规则版本']}\n"
            f"购入后月数：{result['使用月数']}\n"
            f"折旧系数：{result['折旧系数']}｜成色系数：{result['成色系数']}\n"
            f"折旧模型估值：¥{result['折旧模型估值(元)']}\n"
            f"估值基准：¥{result['估值基准(元)']}\n"
            f"估值口径：{result['估值口径']}\n\n"
            f"建议标价：¥{result['建议标价(元)']}\n"
            f"最低接受价：¥{result['最低接受价(元)']}\n"
            f"标价预计净利润：¥{result['标价预计净利润(元)']}\n"
            f"最低价预计净利润：¥{result['最低价预计净利润(元)']}\n"
            f"标价预计净利率：{result['标价预计净利率(%)']}%",
        )

    def copy_listing(self):
        item_id = self.selected_id()
        if not item_id:
            messagebox.showinfo("上架文案", "请先选择一件商品")
            return
        row = next(item for item in self.store.rows if item["商品编号"] == item_id)
        text = generate_listing_text(row)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("已复制", "基础上架文案已复制。请补充真实配件、瑕疵、保修和发货信息。")

    def summary(self):
        if not self.store.rows:
            messagebox.showinfo("品类汇总", "请先录入商品")
            return
        reports = category_summary(self.store.rows)
        lines = [
            f"{name}｜{item['商品数']} 件｜建议标价合计 ¥{item['建议标价合计(元)']}｜"
            f"最低接受价合计 ¥{item['最低接受价合计(元)']}"
            for name, item in sorted(reports.items())
        ]
        messagebox.showinfo("品类汇总", "\n".join(lines))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "商品台账备份及 SHA256 校验值已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将整体替换当前商品台账，请先确认已有备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "商品台账已通过 SHA256 校验并恢复")
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
