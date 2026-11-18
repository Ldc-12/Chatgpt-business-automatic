"""Tkinter desktop UI for the offline Xianyu listing lifecycle manager."""
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_listing import (
    CATEGORIES, CONDITIONS, FIELDS, STATUSES, ListingStore,
    default_data_path, generate_listing_text, listing_summary,
    refresh_due_info, self_test,
)

PRODUCT = "闲鱼商品发布管理助手"
DISPLAY_COLUMNS = (
    "商品名称", "品类", "成色", "标价(元)",
    "最低接受价(元)", "库存数量", "上架状态", "刷新提醒",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼商品发布管理助手｜大陆离线版")
        root.geometry("1320x760")
        self.store = ListingStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增商品", self.add), ("编辑商品", self.edit), ("删除商品", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("复制发布文案", self.copy_listing), ("记录刷新", self.mark_refreshed),
            ("台账汇总", self.summary), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (230, 110, 100, 120, 130, 90, 100, 120)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=85, stretch=False)
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
        today = date.today()
        ordered = sorted(
            self.store.rows,
            key=lambda row: (row["上架状态"], row["计划上架日期"], row["商品名称"]),
        )
        for row in ordered:
            info = refresh_due_info(row, as_of=today)
            reminder = (
                "待刷新" if info["due"]
                else (info["next_refresh_date"] or "未设置日期")
            )
            self.tree.insert(
                "", "end", iid=row["商品编号"],
                values=(
                    row["商品名称"], row["品类"], row["成色"],
                    row["标价(元)"], row["最低接受价(元)"],
                    row["库存数量"], row["上架状态"], reminder,
                ),
            )
        report = listing_summary(self.store.rows, as_of=today)
        self.status.set(
            f"商品：{report['商品总数']} 条｜库存：{report['库存总量']} 件｜"
            f"待刷新：{report['待刷新数量']} 条｜规则版本：XY-LISTING-2026.11｜"
            f"本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "商品编号": "XY-L-" + date.today().strftime("%Y%m%d") + "-" + os.urandom(3).hex().upper(),
                "品类": "手机数码", "成色": "9成新", "标价(元)": "0.00",
                "最低接受价(元)": "0.00", "库存数量": "1", "上架状态": "草稿",
                "计划上架日期": date.today().isoformat(), "刷新间隔(天)": "7",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑商品" if existing else "新增商品")
        window.geometry("820x760")
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
            ttk.Label(form_frame, text=field).grid(
                row=index, column=0, sticky="e", padx=8, pady=4
            )
            variable = tk.StringVar(value=str(values[field]))
            variables[field] = variable
            if field == "品类":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=CATEGORIES,
                    state="readonly", width=48,
                )
            elif field == "成色":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=CONDITIONS,
                    state="readonly", width=48,
                )
            elif field == "上架状态":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=STATUSES,
                    state="readonly", width=48,
                )
            else:
                state = "readonly" if existing and field == "商品编号" else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=52, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text="刷新日期只用于本地提醒；最低接受价和备注属于卖家内部信息，不会出现在复制的发布文案中。商品链接仅保存文本，不会自动访问。",
            wraplength=650, foreground="#555",
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
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")]
        )
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("导出完成", "CSV 已保存为 UTF-8 BOM 格式")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def copy_listing(self):
        item_id = self.selected_id()
        if not item_id:
            messagebox.showinfo("发布文案", "请先选择一件商品")
            return
        row = next(item for item in self.store.rows if item["商品编号"] == item_id)
        self.root.clipboard_clear()
        self.root.clipboard_append(generate_listing_text(row))
        messagebox.showinfo(
            "已复制", "发布文案已复制。最低接受价、商品链接和内部备注不会写入文案。"
        )

    def mark_refreshed(self):
        item_id = self.selected_id()
        if not item_id:
            messagebox.showinfo("记录刷新", "请先选择一件商品")
            return
        try:
            self.store.mark_refreshed(item_id)
            self.refresh()
            messagebox.showinfo("记录完成", "已记录今天的刷新日期")
        except (ValueError, OSError) as exc:
            messagebox.showerror("记录失败", str(exc))

    def summary(self):
        report = listing_summary(self.store.rows)
        counts = "｜".join(
            f"{name}：{count}" for name, count in report["状态数量"].items()
        )
        due = "\n".join(
            f"{row['商品名称']}｜下次刷新 {row['下次刷新日期']}"
            for row in report["待刷新商品"][:20]
        ) or "暂无待刷新商品"
        messagebox.showinfo(
            "台账汇总",
            f"商品总数：{report['商品总数']}\n库存总量：{report['库存总量']}\n"
            f"待刷新：{report['待刷新数量']}\n在售标价库存额：¥{report['在售标价库存额(元)']}\n\n"
            f"{counts}\n\n待刷新清单：\n{due}",
        )

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")]
        )
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "台账备份及 SHA256 校验值已保存")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno(
            "确认恢复", "恢复将整体替换当前发布台账，请先确认已有备份。继续？"
        ):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "发布台账已通过 SHA256 校验并恢复")
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
