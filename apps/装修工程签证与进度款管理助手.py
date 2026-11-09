"""Offline construction variation, evidence and progress-payment assistant."""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.construction_project import (
    ConstructionStore, PROJECT_FIELDS, CHANGE_FIELDS, CLAIM_FIELDS,
    PROJECT_STATUSES, CHANGE_TYPES, MEASUREMENT_TYPES, CHANGE_STATUSES,
    CLAIM_STATUSES, calculate_change_amount, calculate_progress_payment,
    default_data_path, self_test,
)

PRODUCT = "装修工程签证与进度款管理助手"
TABLES = {
    "projects": {
        "title": "项目合同",
        "columns": ["项目编号", "项目名称", "甲方/客户", "合同金额(元)", "已签认变更净额(元)",
                    "调整后合同额(元)", "进度款支付比例(%)", "质保金比例(%)", "状态",
                    "开工日期", "合同竣工日期"],
        "fields": PROJECT_FIELDS,
        "key": "项目编号",
    },
    "changes": {
        "title": "现场签证",
        "columns": ["签证编号", "项目编号", "发生日期", "变更类型", "项目/工序",
                    "计量方式", "金额(元)", "状态", "签认日期", "证据文件"],
        "fields": [f for f in CHANGE_FIELDS if f not in ("金额(元)", "证据SHA256")],
        "key": "签证编号",
    },
    "claims": {
        "title": "进度款申报",
        "columns": ["期次编号", "项目编号", "申报日期", "累计完成产值(元)",
                    "累计已付款(元)", "本期应付金额(元)", "状态", "付款日期"],
        "fields": [f for f in CLAIM_FIELDS if f not in (
            "累计支付比例(%)", "累计质保金比例(%)", "本期应付金额(元)")],
        "key": "期次编号",
    },
}
CHOICES = {
    "状态": PROJECT_STATUSES,
    "变更类型": CHANGE_TYPES,
    "计量方式": MEASUREMENT_TYPES,
    "进度款状态": CLAIM_STATUSES,
}
DEFAULTS = {
    "projects": {
        "项目编号": "", "项目名称": "", "甲方/客户": "", "施工方/乙方": "",
        "合同金额(元)": "0.00", "开工日期": "", "合同竣工日期": "",
        "进度款支付比例(%)": "90", "质保金比例(%)": "5", "状态": "施工中", "备注": "",
    },
    "changes": {
        "签证编号": "", "项目编号": "", "发生日期": "", "变更类型": "增项",
        "项目/工序": "", "计量方式": "数量×单价", "数量": "1", "长度(m)": "0",
        "宽度(m)": "0", "高度(m)": "0", "单位": "项", "综合单价(元)": "0",
        "状态": "待签认", "签认日期": "", "证据文件": "", "备注": "",
    },
    "claims": {
        "期次编号": "", "项目编号": "", "申报日期": "",
        "累计完成产值(元)": "0", "累计已付款(元)": "0",
        "本期预付款抵扣(元)": "0", "本期其他扣款(元)": "0",
        "状态": "草稿", "付款日期": "", "备注": "",
    },
}


class App:
    def __init__(self, root):
        self.root = root
        root.title("装修工程签证与进度款管理助手｜大陆离线版")
        root.geometry("1380x780")
        self.store = ConstructionStore(default_data_path())
        self.trees = {}
        self.summaries = {}
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(8, 4))
        for kind, config in TABLES.items():
            self._build_tab(kind, config)
        bottom = ttk.Frame(root, padding=(10, 4, 10, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="风险检查", command=self.risk_report).pack(side="left", padx=3)
        ttk.Button(bottom, text="完整备份", command=self.backup).pack(side="left", padx=3)
        ttk.Button(bottom, text="恢复备份", command=self.restore).pack(side="left", padx=3)
        ttk.Label(
            bottom,
            text=f"本地数据：{self.store.path}｜不上传合同和现场资料",
            foreground="#555",
        ).pack(side="right")
        self.refresh()

    def _build_tab(self, kind, config):
        frame = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(frame, text=config["title"])
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 8))
        for label, action in [
            ("新增", lambda k=kind: self.form(k)),
            ("编辑", lambda k=kind: self.edit(k)),
            ("删除", lambda k=kind: self.delete(k)),
            ("导入 CSV", lambda k=kind: self.import_csv(k)),
            ("导出 CSV", lambda k=kind: self.export_csv(k)),
        ]:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=3)
        area = ttk.Frame(frame)
        area.pack(fill="both", expand=True)
        tree = ttk.Treeview(area, columns=config["columns"], show="headings", height=20)
        for column in config["columns"]:
            tree.heading(column, text=column)
            tree.column(column, width=135, minwidth=85, stretch=True)
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
        if kind == "projects":
            rows = []
            for project in self.store.projects:
                summary = self.store.project_summary(project["项目编号"])
                rows.append({**project, **summary})
            return rows
        if kind == "changes":
            return self.store.changes
        return self.store.claims

    def refresh(self):
        for kind, config in TABLES.items():
            tree = self.trees[kind]
            tree.delete(*tree.get_children())
            rows = self._rows(kind)
            for row in rows:
                tree.insert("", "end", iid=row[config["key"]],
                            values=[row.get(column, "") for column in config["columns"]])
            self.summaries[kind].set(f"共 {len(rows)} 条｜双击记录后点击“编辑”可维护")

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
        win.geometry("650x720")
        values = dict(DEFAULTS[kind])
        if existing:
            values.update(existing)
        if kind in ("changes", "claims") and not existing and self.store.projects:
            values["项目编号"] = self.store.projects[0]["项目编号"]
        variables = {}
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
        project_ids = [x["项目编号"] for x in self.store.projects]
        fields = config["fields"]
        for index, field in enumerate(fields):
            ttk.Label(form_frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=5)
            variable = tk.StringVar(value=str(values.get(field, "")))
            variables[field] = variable
            if field == "项目编号" and kind in ("changes", "claims"):
                widget = ttk.Combobox(form_frame, textvariable=variable, values=project_ids,
                                      state="readonly", width=42)
            elif field == "状态":
                choices = PROJECT_STATUSES if kind == "projects" else (
                    CHANGE_STATUSES if kind == "changes" else CLAIM_STATUSES)
                widget = ttk.Combobox(form_frame, textvariable=variable, values=choices,
                                      state="readonly", width=42)
            elif field == "变更类型":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=CHANGE_TYPES,
                                      state="readonly", width=42)
            elif field == "计量方式":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=MEASUREMENT_TYPES,
                                      state="readonly", width=42)
            else:
                state = "readonly" if existing and field == config["key"] else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=45, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=5)
            if field == "证据文件":
                ttk.Button(form_frame, text="选择文件",
                           command=lambda v=variable: self._choose_evidence(v)).grid(
                    row=index, column=2, padx=4, pady=5)
        preview = tk.StringVar(value="")
        ttk.Label(form_frame, textvariable=preview, foreground="#245b87",
                  wraplength=520).grid(row=len(fields), column=0, columnspan=3,
                                      sticky="w", padx=8, pady=8)

        def update_preview(*_):
            try:
                if kind == "changes":
                    amount = calculate_change_amount({field: variable.get()
                                                       for field, variable in variables.items()})
                    preview.set(f"按当前计量规则计算：¥{amount}（减项显示为负数；工期签证为 0）")
                elif kind == "claims":
                    project = next((x for x in self.store.projects
                                    if x["项目编号"] == variables["项目编号"].get()), None)
                    if project:
                        result = calculate_progress_payment(
                            variables["累计完成产值(元)"].get(),
                            variables["累计已付款(元)"].get(),
                            variables["本期预付款抵扣(元)"].get(),
                            variables["本期其他扣款(元)"].get(),
                            project["进度款支付比例(%)"], project["质保金比例(%)"],
                        )
                        preview.set(
                            f"按项目合同参数估算本期应付：¥{result['本期应付金额(元)']}；"
                            f"累计支付上限：¥{result['累计支付上限(元)']}；"
                            f"本次质保金累计扣留：¥{result['本次质保金累计扣留(元)']}"
                        )
                    else:
                        preview.set("请先选择项目")
                else:
                    preview.set("项目合同金额、工期和支付比例将用于后续签证与进度款核对。")
            except (ValueError, KeyError) as exc:
                preview.set("计算预览：" + str(exc))

        for variable in variables.values():
            variable.trace_add("write", update_preview)
        update_preview()

        def save():
            row = {field: variable.get() for field, variable in variables.items()}
            if kind == "changes" and existing:
                row["证据SHA256"] = existing.get("证据SHA256", "")
            try:
                if existing:
                    if kind == "projects":
                        self.store.update_project(old_id, row)
                    elif kind == "changes":
                        self.store.update_change(old_id, row)
                    else:
                        self.store.update_claim(old_id, row)
                else:
                    if kind == "projects":
                        self.store.add_project(row)
                    elif kind == "changes":
                        self.store.add_change(row)
                    else:
                        self.store.add_claim(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(form_frame, text="保存", command=save).grid(
            row=len(fields) + 1, column=0, columnspan=3, pady=12)

    def _choose_evidence(self, variable):
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("现场证据文件", "*.jpg *.jpeg *.png *.pdf *.doc *.docx *.xlsx *.txt"),
                       ("所有文件", "*.*")],
        )
        if path:
            variable.set(path)

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
            if kind == "projects":
                self.store.delete_project(record_id)
            elif kind == "changes":
                self.store.delete_change(record_id)
            else:
                self.store.delete_claim(record_id)
            self.refresh()
        except (ValueError, OSError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

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
                messagebox.showinfo("备份完成", "项目、签证、进度款和操作记录已备份。证据原件仍保存在原路径，请另行备份原件。")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc), parent=self.root)

    def restore(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno(
            "确认恢复", "恢复会替换当前项目、签证、进度款和操作记录，建议先备份。是否继续？",
            parent=self.root,
        ):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "数据已恢复。请检查签证证据路径是否仍可访问。")
            except (ValueError, OSError, TypeError) as exc:
                messagebox.showerror("恢复失败", str(exc), parent=self.root)

    def risk_report(self):
        findings = self.store.risk_findings()
        if not findings:
            messagebox.showinfo("风险检查", "当前没有触发内置规则的异常。仍需人工核对合同原件和现场事实。")
            return
        lines = [
            f"[{item['等级']}] {item['规则编号']}｜{item['编号']}：{item['说明']}"
            for item in findings[:80]
        ]
        if len(findings) > 80:
            lines.append(f"另有 {len(findings) - 80} 条未显示。")
        messagebox.showwarning("风险检查结果", "\n".join(lines), parent=self.root)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()
