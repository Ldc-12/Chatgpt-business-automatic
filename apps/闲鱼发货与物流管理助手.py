"""Tkinter desktop UI for the offline Xianyu shipping ledger."""
import os
import sys
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_shipping import (
    CARRIERS, FIELDS, STATUSES, ShippingStore, default_data_path,
    self_test, shipping_risk, shipping_summary,
)

PRODUCT = "闲鱼发货与物流管理助手"
DISPLAY_COLUMNS = (
    "订单编号", "商品/SKU", "承运商", "运单号",
    "承诺发货日期", "预计送达日期", "物流状态", "提醒",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼发货与物流管理助手｜大陆离线版")
        root.geometry("1380x760")
        self.store = ShippingStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增发货", self.add), ("编辑记录", self.edit), ("删除记录", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("物流汇总", self.summary), ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=2)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (170, 190, 110, 170, 120, 120, 100, 180)
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
            key=lambda row: (row["承诺发货日期"], row["物流状态"], row["订单编号"]),
        )
        for row in ordered:
            risk = shipping_risk(row, as_of=today)
            self.tree.insert(
                "", "end", iid=row["发货编号"],
                values=(
                    row["订单编号"], row["商品/SKU"], row["承运商"],
                    row["运单号"], row["承诺发货日期"], row["预计送达日期"],
                    row["物流状态"], risk["提醒"] or "—",
                ),
            )
        report = shipping_summary(self.store.rows, as_of=today)
        self.status.set(
            f"发货：{report['发货总数']} 单｜发货逾期：{report['发货逾期数量']}｜"
            f"等待揽收：{report['等待揽收数量']}｜送达逾期：{report['送达逾期数量']}｜"
            f"物流异常：{report['异常件数量']}｜规则版本：XY-SHIPPING-2026.11｜"
            f"本地数据：{self.store.path}"
        )

    def selected_id(self):
        selected = self.tree.selection()
        return selected[0] if selected else None

    def form(self, existing=None):
        today = date.today()
        values = {field: (existing or {}).get(field, "") for field in FIELDS}
        if not existing:
            values.update({
                "发货编号": "XY-S-" + today.strftime("%Y%m%d") + "-" + os.urandom(3).hex().upper(),
                "下单日期": today.isoformat(),
                "承诺发货日期": (today + timedelta(days=2)).isoformat(),
                "物流状态": "待打包",
                "包裹重量(kg)": "0.5",
                "运费(元)": "0.00",
            })
        window = tk.Toplevel(self.root)
        window.title("编辑发货记录" if existing else "新增发货记录")
        window.geometry("900x760")
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
            if field == "物流状态":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=STATUSES,
                    state="readonly", width=54,
                )
            elif field == "承运商":
                widget = ttk.Combobox(
                    form_frame, textvariable=variable, values=CARRIERS,
                    state="normal", width=54,
                )
            else:
                state = "readonly" if existing and field == "发货编号" else "normal"
                widget = ttk.Entry(form_frame, textvariable=variable, width=57, state=state)
            widget.grid(row=index, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text="物流状态由卖家根据实际物流信息手工更新；本工具不连接快递公司、不查询运单、不自动通知买家。异常状态必须填写异常说明。",
            wraplength=720, foreground="#555",
        ).grid(row=len(FIELDS), column=0, columnspan=2, sticky="w", padx=8, pady=10)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update(existing["发货编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(form_frame, text="保存记录", command=save).grid(
            row=len(FIELDS) + 1, column=0, columnspan=2, pady=12
        )

    def add(self):
        self.form()

    def edit(self):
        shipment_id = self.selected_id()
        if shipment_id:
            row = next(item for item in self.store.rows if item["发货编号"] == shipment_id)
            self.form(row)

    def delete(self):
        shipment_id = self.selected_id()
        if shipment_id and messagebox.askyesno("确认删除", "删除所选发货记录？"):
            try:
                self.store.delete(shipment_id)
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"整批导入 {count} 条发货记录")
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

    def summary(self):
        report = shipping_summary(self.store.rows)
        counts = "｜".join(
            f"{name}：{count}" for name, count in report["状态数量"].items()
        )
        sections = []
        for title, key in (
            ("发货逾期", "发货逾期清单"),
            ("等待揽收", "等待揽收清单"),
            ("送达逾期", "送达逾期清单"),
            ("物流异常", "异常件清单"),
        ):
            rows = report[key][:8]
            sections.append(title + "：" + (
                "、".join(f"{row['订单编号']}（{row['商品/SKU']}）" for row in rows)
                if rows else "无"
            ))
        messagebox.showinfo(
            "物流汇总",
            f"发货总数：{report['发货总数']}\n累计运费：¥{report['累计运费(元)']}\n"
            f"{counts}\n\n" + "\n".join(sections),
        )

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")]
        )
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "发货台账备份及 SHA256 校验值已保存")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno(
            "确认恢复", "恢复将整体替换当前发货台账，请先确认已有备份。继续？"
        ):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "发货台账已通过 SHA256 校验并恢复")
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
