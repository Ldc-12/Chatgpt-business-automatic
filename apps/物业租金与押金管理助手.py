"""Offline rental lease, rent collection and deposit management assistant."""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.rental_ledger import (
    RentalStore, LEASE_FIELDS, PAYMENT_FIELDS, DEPOSIT_FIELDS,
    LEASE_STATUSES, DEPOSIT_TYPES, default_data_path, self_test,
)

PRODUCT = "物业租金与押金管理助手"
TABLES = {
    "leases": {
        "title": "租约台账",
        "columns": ["租约编号", "房产/房间", "租客", "联系电话", "起租日期",
                    "退租日期", "月租金(元)", "每月缴租日", "应收押金(元)", "状态"],
        "fields": LEASE_FIELDS,
        "key": "租约编号",
    },
    "charges": {
        "title": "租金账单",
        "columns": ["账单编号", "租约编号", "账期(月)", "应收日期",
                    "应收金额(元)", "已收金额(元)", "未收金额(元)", "状态"],
        "fields": [],
        "key": "账单编号",
    },
    "payments": {
        "title": "租金收款",
        "columns": ["收款编号", "账单编号", "收款日期", "金额(元)", "方式", "流水号"],
        "fields": PAYMENT_FIELDS,
        "key": "收款编号",
    },
    "deposits": {
        "title": "押金流水",
        "columns": ["押金流水号", "租约编号", "日期", "类型", "金额(元)", "说明"],
        "fields": DEPOSIT_FIELDS,
        "key": "押金流水号",
    },
}
DEFAULTS = {
    "leases": {
        "租约编号": "", "房产/房间": "", "租客": "", "联系电话": "",
        "起租日期": "", "退租日期": "", "月租金(元)": "0",
        "每月缴租日": "5", "应收押金(元)": "0", "状态": "有效", "备注": "",
    },
    "payments": {
        "收款编号": "", "账单编号": "", "收款日期": "",
        "金额(元)": "0", "方式": "银行转账", "流水号": "", "备注": "",
    },
    "deposits": {
        "押金流水号": "", "租约编号": "", "日期": "",
        "类型": "收取", "金额(元)": "0", "说明": "",
    },
}


class App:
    def __init__(self, root):
        self.root = root
        root.title("物业租金与押金管理助手｜大陆离线版")
        root.geometry("1320x760")
        self.store = RentalStore(default_data_path())
        self.trees = {}
        self.summaries = {}
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(8, 4))
        for kind, config in TABLES.items():
            self._build_tab(kind, config)
        bottom = ttk.Frame(root, padding=(10, 4, 10, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="租金/押金风险检查", command=self.risk_report).pack(side="left", padx=3)
        ttk.Button(bottom, text="完整备份", command=self.backup).pack(side="left", padx=3)
        ttk.Button(bottom, text="恢复备份", command=self.restore).pack(side="left", padx=3)
        ttk.Label(
            bottom,
            text=f"本地数据：{self.store.path}｜不上传租客资料",
            foreground="#555",
        ).pack(side="right")
        self.refresh()

    def _build_tab(self, kind, config):
        frame = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(frame, text=config["title"])
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 8))
        if kind != "charges":
            ttk.Button(toolbar, text="新增", command=lambda k=kind: self.form(k)).pack(side="left", padx=3)
            ttk.Button(toolbar, text="编辑", command=lambda k=kind: self.edit(k)).pack(side="left", padx=3)
        else:
            ttk.Button(toolbar, text="生成租金账单", command=self.generate_charges).pack(side="left", padx=3)
        ttk.Button(toolbar, text="删除", command=lambda k=kind: self.delete(k)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="导入 CSV", command=lambda k=kind: self.import_csv(k)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="导出 CSV", command=lambda k=kind: self.export_csv(k)).pack(side="left", padx=3)
        area = ttk.Frame(frame)
        area.pack(fill="both", expand=True)
        tree = ttk.Treeview(area, columns=config["columns"], show="headings", height=20)
        for column in config["columns"]:
            tree.heading(column, text=column)
            tree.column(column, width=145, minwidth=85, stretch=True)
        yscroll = ttk.Scrollbar(area, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(area, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        summary = tk.StringVar()
        ttk.Label(frame, textvariable=summary, anchor="w", padding=(4, 8)).pack(fill="x")
        self.trees[kind] = tree
        self.summaries[kind] = summary

    def _rows(self, kind):
        if kind == "leases":
            return self.store.leases
        if kind == "charges":
            return self.store.rent_rows()
        if kind == "payments":
            return self.store.payments
        return self.store.deposits

    def refresh(self):
        for kind, config in TABLES.items():
            tree = self.trees[kind]
            tree.delete(*tree.get_children())
            rows = self._rows(kind)
            for row in rows:
                tree.insert("", "end", iid=row[config["key"]],
                            values=[row.get(column, "") for column in config["columns"]])
            self.summaries[kind].set(f"共 {len(rows)} 条｜租金账单按租约日期和缴租日自动生成")

    def _selected(self, kind):
        selected = self.trees[kind].selection()
        return selected[0] if selected else None

    def form(self, kind, existing=None):
        config = TABLES[kind]
        old_id = existing[config["key"]] if existing else ""
        win = tk.Toplevel(self.root)
        win.title(("编辑" if existing else "新增") + config["title"])
        win.transient(self.root)
        win.grab_set()
        win.geometry("620x680")
        values = dict(DEFAULTS[kind])
        if existing:
            values.update(existing)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        form_frame = ttk.Frame(canvas)
        form_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        variables = {}
        fields = config["fields"]
        lease_ids = [x["租约编号"] for x in self.store.leases]
        charge_ids = [x["账单编号"] for x in self.store.charges]
        for index, field in enumerate(fields):
            ttk.Label(form_frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=5)
            variable = tk.StringVar(value=str(values.get(field, "")))
            variables[field] = variable
            if field == "租约编号" and kind == "deposits":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=lease_ids,
                                      state="readonly", width=42)
            elif field == "账单编号" and kind == "payments":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=charge_ids,
                                      state="readonly", width=42)
            elif field == "状态" and kind == "leases":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=LEASE_STATUSES,
                                      state="readonly", width=42)
            elif field == "类型" and kind == "deposits":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=DEPOSIT_TYPES,
                                      state="readonly", width=42)
            else:
                state = "readonly" if existing and field == config["key"] else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=45, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=5)

        def save():
            row = {field: variable.get() for field, variable in variables.items()}
            try:
                if existing:
                    if kind == "leases":
                        self.store.update_lease(old_id, row)
                    elif kind == "payments":
                        self.store.update_payment(old_id, row)
                    else:
                        self.store.update_deposit(old_id, row)
                else:
                    if kind == "leases":
                        self.store.add_lease(row)
                    elif kind == "payments":
                        self.store.add_payment(row)
                    else:
                        self.store.add_deposit(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(form_frame, text="保存", command=save).grid(
            row=len(fields) + 1, column=0, columnspan=2, pady=12)

    def edit(self, kind):
        record_id = self._selected(kind)
        if not record_id:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        key = TABLES[kind]["key"]
        row = next((x for x in self._rows(kind) if x[key] == record_id), None)
        if row:
            self.form(kind, row)

    def delete(self, kind):
        record_id = self._selected(kind)
        if not record_id:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if not messagebox.askyesno("确认删除", f"确定删除记录 {record_id}？", parent=self.root):
            return
        try:
            if kind == "leases":
                self.store.delete_lease(record_id)
            elif kind == "charges":
                self.store.delete_charge(record_id)
            elif kind == "payments":
                self.store.delete_payment(record_id)
            else:
                self.store.delete_deposit(record_id)
            self.refresh()
        except (ValueError, OSError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def generate_charges(self):
        selected = self._selected("leases")
        lease_id = simpledialog.askstring(
            "生成租金账单", "输入租约编号（可先在租约台账选中租约）：",
            initialvalue=selected or "",
            parent=self.root,
        )
        if not lease_id:
            return
        through = simpledialog.askstring(
            "生成租金账单", "生成截至月份（YYYY-MM，例如 2026-11）：",
            parent=self.root,
        )
        if not through:
            return
        try:
            count = self.store.generate_charges(lease_id.strip(), through.strip())
            self.refresh()
            messagebox.showinfo("生成完成", f"新增 {count} 期账单；已存在的账期不会重复生成。", parent=self.root)
        except (ValueError, OSError) as exc:
            messagebox.showerror("生成失败", str(exc), parent=self.root)

    def import_csv(self, kind):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(kind, path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功追加 {count} 条记录", parent=self.root)
        except (ValueError, OSError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def export_csv(self, kind):
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_csv(kind, path)
            messagebox.showinfo("导出完成", "当前类别的全部记录已导出", parent=self.root)
        except (ValueError, OSError) as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)

    def backup(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "租约、账单、收款、押金和操作记录已备份。")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc), parent=self.root)

    def restore(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno(
            "确认恢复", "恢复会替换当前租赁数据，建议先备份。是否继续？", parent=self.root
        ):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "租赁数据已恢复。")
            except (ValueError, OSError, TypeError) as exc:
                messagebox.showerror("恢复失败", str(exc), parent=self.root)

    def risk_report(self):
        findings = self.store.risk_findings()
        if not findings:
            messagebox.showinfo("风险检查", "当前没有触发内置规则的异常。仍需核对租约、收款凭证和押金约定。")
            return
        lines = [
            f"[{item['等级']}] {item['规则编号']}｜{item['编号']}：{item['说明']}"
            for item in findings[:80]
        ]
        if len(findings) > 80:
            lines.append(f"另有 {len(findings) - 80} 条未显示。")
        messagebox.showwarning("租金/押金风险检查", "\n".join(lines), parent=self.root)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()
