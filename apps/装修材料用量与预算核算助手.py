"""Tkinter desktop UI for the offline renovation material takeoff assistant."""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from uuid import uuid4
from datetime import date
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.renovation_materials import (
    CATEGORIES, UNITS, FIELDS, MaterialStore, calculate_material,
    calculate_tile_quantity, calculate_paint_liters, project_summary,
    default_data_path, self_test,
)

PRODUCT = "装修材料用量与预算核算助手"
DISPLAY_COLUMNS = (
    "项目编号", "房间/区域", "材料名称", "材料类别", "计量单位",
    "净用量", "计划用量(含损耗)", "建议采购包装数", "建议采购量",
    "预算金额(元)", "实际金额(元)", "实际与预算差额(元)",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("装修材料用量与预算核算助手｜大陆离线版")
        root.geometry("1420x760")
        self.store = MaterialStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增材料", self.add), ("编辑材料", self.edit), ("删除材料", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("项目预算汇总", self.summary), ("瓷砖用量计算", self.tile_calculator),
            ("乳胶漆用量计算", self.paint_calculator), ("备份", self.backup),
            ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        for column in DISPLAY_COLUMNS:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=118, minwidth=88, stretch=False)
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
            key=lambda row: (row["项目编号"], row["房间/区域"], row["材料编码"], row["记录编号"]),
        )
        for row in ordered:
            calc = calculate_material(row)
            values = [
                row["项目编号"], row["房间/区域"], row["材料名称"], row["材料类别"],
                row["计量单位"], calc["净用量"], calc["计划用量(含损耗)"],
                calc["建议采购包装数"], calc["建议采购量"], calc["预算金额(元)"],
                calc["实际金额(元)"], calc["实际与预算差额(元)"],
            ]
            self.tree.insert("", "end", iid=row["记录编号"], values=values)
        total = sum((Decimal(calculate_material(row)["预算金额(元)"]) for row in self.store.rows), Decimal("0"))
        self.status.set(
            f"材料记录：{len(self.store.rows)} 条｜预算合计：¥{total:,.2f}｜"
            f"数据保存在本机：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        old_id = existing["记录编号"] if existing else ""
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "记录编号": "RM-" + date.today().strftime("%Y%m%d") + "-" + uuid4().hex[:6].upper(),
                "损耗率(%)": "5", "包装规格": "1", "单价(元/单位)": "0",
                "材料类别": "其他", "计量单位": "m²",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑材料记录" if existing else "新增材料记录")
        window.geometry("720x700")
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
            ttk.Label(form_frame, text=field).grid(row=index, column=0, sticky="e", padx=8, pady=5)
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            if field == "材料类别":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=CATEGORIES, state="readonly", width=42)
            elif field == "计量单位":
                widget = ttk.Combobox(form_frame, textvariable=variable, values=UNITS, state="readonly", width=42)
            else:
                state = "readonly" if existing and field == "记录编号" else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=45, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(
            form_frame,
            text="预算规则：净用量 × (1 + 损耗率) → 向上取整到整包装 → 乘以单价。包装规格和单价须使用同一计量单位。",
            wraplength=560,
            foreground="#555",
        ).grid(row=len(FIELDS), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update(old_id, row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(form_frame, text="保存材料", command=save).grid(
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
        if record_id and messagebox.askyesno("确认删除", "删除所选材料记录？"):
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
                messagebox.showinfo("导入完成", f"整批导入 {count} 条材料记录")
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
            messagebox.showinfo("项目预算汇总", "请先录入材料记录")
            return
        summaries = project_summary(self.store.rows)
        lines = []
        for key, item in sorted(summaries.items()):
            lines.append(
                f"{key}｜{item['项目名称']}\n材料行数：{item['材料行数']}\n"
                f"预算：¥{item['预算金额(元)']}｜已录实际：¥{item['实际金额(元)']}｜"
                f"差额：¥{item['实际与预算差额(元)']}"
            )
        messagebox.showinfo("项目预算汇总", "\n\n".join(lines))

    def tile_calculator(self):
        area = simpledialog.askstring("瓷砖用量", "铺贴净面积（m²）：", parent=self.root)
        if area is None:
            return
        length = simpledialog.askstring("瓷砖用量", "瓷砖长度（mm）：", parent=self.root)
        if length is None:
            return
        width = simpledialog.askstring("瓷砖用量", "瓷砖宽度（mm）：", parent=self.root)
        if width is None:
            return
        waste = simpledialog.askstring("瓷砖用量", "损耗率（%，默认 8）：", initialvalue="8", parent=self.root)
        if waste is None:
            return
        per_box = simpledialog.askstring("瓷砖用量", "每箱片数（默认 4）：", initialvalue="4", parent=self.root)
        if per_box is None:
            return
        try:
            result = calculate_tile_quantity(area, length, width, waste, per_box)
            messagebox.showinfo(
                "瓷砖采购建议",
                f"理论所需：{result['理论所需片数']} 片\n"
                f"建议购买：{result['建议整箱数']} 箱（{result['建议采购片数']} 片）\n"
                f"采购覆盖面积：{result['采购覆盖面积(m²)']} m²",
            )
        except ValueError as exc:
            messagebox.showerror("计算失败", str(exc))

    def paint_calculator(self):
        area = simpledialog.askstring("乳胶漆用量", "涂刷面积（m²）：", parent=self.root)
        if area is None:
            return
        coats = simpledialog.askstring("乳胶漆用量", "涂刷遍数（默认 2）：", initialvalue="2", parent=self.root)
        if coats is None:
            return
        coverage = simpledialog.askstring("乳胶漆用量", "每升理论涂刷面积（m²/L）：", parent=self.root)
        if coverage is None:
            return
        waste = simpledialog.askstring("乳胶漆用量", "损耗率（%，默认 10）：", initialvalue="10", parent=self.root)
        if waste is None:
            return
        try:
            liters = calculate_paint_liters(area, coats, coverage, waste)
            messagebox.showinfo("乳胶漆采购建议", f"建议准备约 {liters} L（按 0.1 L 向上取整）")
        except ValueError as exc:
            messagebox.showerror("计算失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "备份已保存，包含 SHA256 完整性校验")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前全部材料记录，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "备份校验通过，材料记录已恢复")
            except (ValueError, OSError) as exc:
                messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
