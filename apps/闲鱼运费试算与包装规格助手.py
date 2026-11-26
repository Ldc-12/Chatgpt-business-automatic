"""Tkinter desktop UI for the offline Xianyu freight estimator."""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_freight_calc import (
    CARRIERS, QUOTE_FIELDS, RATE_FIELDS, FreightStore, default_data_path,
    freight_summary, self_test,
)

PRODUCT = "闲鱼运费试算与包装规格助手"
DISPLAY_COLUMNS = (
    "订单编号", "商品/SKU", "承运商", "目的地区", "实重(kg)", "体积重(kg)",
    "计费重量(kg)", "预估运费(元)", "实际运费(元)", "运费差额(元)",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼运费试算与包装规格助手｜大陆离线版")
        root.geometry("1320x720")
        self.store = FreightStore(default_data_path())
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增运费试算", self.add_quote), ("录入实际运费", self.update_actual),
            ("删除试算", self.delete_quote), ("费率规则", self.manage_rates),
            ("导入报价 CSV", self.import_quotes), ("导出报价 CSV", self.export_quotes),
            ("导入费率 CSV", self.import_rates), ("导出费率 CSV", self.export_rates),
            ("运费汇总", self.show_summary), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)
        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (135, 150, 100, 150, 85, 85, 95, 110, 110, 105)
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
        for row in sorted(self.store.rows, key=lambda item: (item["试算日期"], item["订单编号"])):
            self.tree.insert("", "end", iid=row["试算编号"], values=tuple(row[field] for field in DISPLAY_COLUMNS))
        report = freight_summary(self.store.rows)
        self.status.set(
            f"试算：{report['试算总数']} 单｜已录实际运费：{report['已录实际运费单数']} 单｜"
            f"预估合计：¥{report['累计预估运费(元)']}｜实际合计：¥{report['累计实际运费(元)']}｜"
            f"费率规则：{len(self.store.rates)} 条｜本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def add_quote(self):
        window = tk.Toplevel(self.root)
        window.title("新增运费试算")
        window.geometry("680x540")
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        defaults = {
            "订单编号": "", "商品/SKU": "", "承运商": CARRIERS[0],
            "目的地区": "", "实重(kg)": "0.5", "长(cm)": "20",
            "宽(cm)": "15", "高(cm)": "10", "备注": "",
        }
        variables = {}
        fields = tuple(defaults)
        for index, field in enumerate(fields):
            ttk.Label(frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=6)
            variable = tk.StringVar(value=defaults[field])
            variables[field] = variable
            if field == "承运商":
                widget = ttk.Combobox(frame, textvariable=variable, values=CARRIERS, state="readonly", width=42)
            else:
                widget = ttk.Entry(frame, textvariable=variable, width=46)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=6)
        note = (
            "系统按实重与体积重取较大值，再按费率规则的首重/续重单位向上计费。\n"
            "费率必须先由卖家依据自己的快递合同或价目表录入；软件不会联网查询快递报价。"
        )
        ttk.Label(frame, text=note, wraplength=590, foreground="#555").grid(row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=12)

        def save():
            try:
                row = self.store.quote({field: variables[field].get() for field in fields})
                self.refresh()
                messagebox.showinfo(
                    "试算完成",
                    f"匹配规则：{row['费率规则编号']}\n体积重：{row['体积重(kg)']} kg\n"
                    f"计费重量：{row['计费重量(kg)']} kg\n预估运费：¥{row['预估运费(元)']}",
                    parent=window,
                )
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("试算失败", str(exc), parent=window)

        ttk.Button(frame, text="计算并保存", command=save).grid(row=len(fields) + 1, column=0, columnspan=2, pady=12)

    def update_actual(self):
        quote_id = self.selected_id()
        if not quote_id:
            messagebox.showinfo("请先选择", "请先选择一条试算记录")
            return
        row = next(item for item in self.store.rows if item["试算编号"] == quote_id)
        value = simpledialog.askstring(
            "录入实际运费", "请输入快递账单中的实际运费（元）：",
            initialvalue=row["实际运费(元)"], parent=self.root,
        )
        if value is not None:
            try:
                self.store.update_actual(quote_id, value)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("更新失败", str(exc))

    def delete_quote(self):
        quote_id = self.selected_id()
        if not quote_id:
            return
        if messagebox.askyesno("确认删除", "删除所选运费试算记录？"):
            try:
                self.store.delete_quote(quote_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def manage_rates(self):
        window = tk.Toplevel(self.root)
        window.title("快递费率规则（手工维护）")
        window.geometry("1120x580")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        columns = ("规则编号", "承运商", "目的地区关键词", "抛重系数(cm³/kg)", "首重(kg)", "首费(元)", "续重单位(kg)", "续费(元)", "附加费(元)", "有效起始日期", "有效结束日期")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=105, minwidth=85, stretch=True)
        tree.pack(fill="both", expand=True)

        def refresh_rates():
            tree.delete(*tree.get_children())
            for rate in self.store.rates:
                tree.insert("", "end", iid=rate["规则编号"], values=tuple(rate[field] for field in columns))

        def edit_rate(existing=None):
            dialog = tk.Toplevel(window)
            dialog.title("编辑费率规则" if existing else "新增费率规则")
            dialog.geometry("620x600")
            dialog.transient(window)
            dialog.grab_set()
            body = ttk.Frame(dialog, padding=12)
            body.pack(fill="both", expand=True)
            defaults = {field: (existing or {}).get(field, "") for field in RATE_FIELDS}
            defaults.update({
                "承运商": defaults["承运商"] or CARRIERS[0],
                "目的地区关键词": defaults["目的地区关键词"] or "全国",
                "抛重系数(cm³/kg)": defaults["抛重系数(cm³/kg)"] or "6000",
                "首重(kg)": defaults["首重(kg)"] or "1",
                "首费(元)": defaults["首费(元)"] or "",
                "续重单位(kg)": defaults["续重单位(kg)"] or "0.5",
                "续费(元)": defaults["续费(元)"] or "",
                "附加费(元)": defaults["附加费(元)"] or "0",
            })
            variables = {}
            for index, field in enumerate(RATE_FIELDS):
                ttk.Label(body, text=field).grid(row=index, column=0, sticky="e", padx=6, pady=4)
                variable = tk.StringVar(value=defaults[field])
                variables[field] = variable
                if field == "承运商":
                    widget = ttk.Combobox(body, textvariable=variable, values=(*CARRIERS, "全部承运商"), state="readonly", width=42)
                else:
                    widget = ttk.Entry(body, textvariable=variable, width=45)
                widget.grid(row=index, column=1, sticky="w", padx=6, pady=4)
            ttk.Label(body, text="全国规则请填写“全国”；同一承运商、同一有效日期内，不要设置同样长度的重复地区关键词。", wraplength=560, foreground="#555").grid(row=len(RATE_FIELDS), column=0, columnspan=2, sticky="w", padx=6, pady=8)

            def save():
                values = {field: variables[field].get() for field in RATE_FIELDS}
                try:
                    if existing:
                        self.store.update_rate(existing["规则编号"], values)
                    else:
                        self.store.add_rate(values)
                    refresh_rates()
                    self.refresh()
                    dialog.destroy()
                except (ValueError, OSError) as exc:
                    messagebox.showerror("保存失败", str(exc), parent=dialog)

            ttk.Button(body, text="保存规则", command=save).grid(row=len(RATE_FIELDS) + 1, column=0, columnspan=2, pady=10)

        def add_rate():
            edit_rate()

        def edit_selected():
            rule_id = tree.focus()
            if rule_id:
                existing = next(item for item in self.store.rates if item["规则编号"] == rule_id)
                edit_rate(existing)

        def delete_selected():
            rule_id = tree.focus()
            if rule_id and messagebox.askyesno("确认删除", f"删除费率规则 {rule_id}？", parent=window):
                try:
                    self.store.delete_rate(rule_id)
                    refresh_rates()
                    self.refresh()
                except (ValueError, OSError) as exc:
                    messagebox.showerror("删除失败", str(exc), parent=window)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="新增规则", command=add_rate).pack(side="left", padx=4)
        ttk.Button(buttons, text="编辑规则", command=edit_selected).pack(side="left", padx=4)
        ttk.Button(buttons, text="删除规则", command=delete_selected).pack(side="left", padx=4)
        refresh_rates()

    def _choose_csv(self, save=False, initial=""):
        if save:
            return filedialog.asksaveasfilename(initialfile=initial, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        return filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])

    def import_quotes(self):
        path = self._choose_csv()
        if path:
            try:
                count = self.store.import_csv(Path(path))
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条试算记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_quotes(self):
        path = self._choose_csv(True, "闲鱼运费试算.csv")
        if path:
            try:
                count = self.store.export_csv(Path(path))
                messagebox.showinfo("导出完成", f"已导出 {count} 条记录（UTF-8 BOM）")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def import_rates(self):
        path = self._choose_csv()
        if path:
            try:
                count = self.store.import_rate_csv(Path(path))
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条费率规则")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_rates(self):
        path = self._choose_csv(True, "快递费率规则模板.csv")
        if path:
            try:
                count = self.store.export_rate_csv(Path(path))
                messagebox.showinfo("导出完成", f"已导出 {count} 条费率规则；可在表格中补充后重新导入")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def show_summary(self):
        report = freight_summary(self.store.rows)
        lines = [
            f"试算总数：{report['试算总数']}",
            f"已录实际运费：{report['已录实际运费单数']} 单",
            f"累计预估运费：¥{report['累计预估运费(元)']}",
            f"累计实际运费：¥{report['累计实际运费(元)']}",
            "",
        ]
        for item in report["承运商汇总"]:
            lines.append(f"{item['承运商']}：{item['试算单数']} 单，预估 ¥{item['预估运费(元)']}，实际 ¥{item['实际运费(元)']}")
        messagebox.showinfo("运费汇总", "\n".join(lines))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(Path(path))
                messagebox.showinfo("备份完成", "费率规则和运费试算记录已生成 SHA256 校验备份")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会整体替换当前费率规则和试算记录，是否继续？"):
            try:
                count = self.store.restore(Path(path))
                self.refresh()
                messagebox.showinfo("恢复完成", f"已恢复 {count} 条试算记录和 {len(self.store.rates)} 条费率规则")
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
