"""Tkinter desktop UI for the offline Xianyu return/refund follow-up ledger."""
import os
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_returns import (
    CASE_TYPES, FIELDS, FREIGHT_PAYER, RESPONSIBILITIES, STATUSES,
    ReturnFollowupStore, after_sales_summary, case_risk, default_data_path,
    self_test,
)

PRODUCT = "闲鱼退货退款跟进助手"
DISPLAY_COLUMNS = (
    "订单编号", "商品/SKU", "售后类型", "处理状态",
    "处理截止日期", "下次跟进日期", "实际退款金额(元)", "提醒事项", "提醒",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("闲鱼退货退款跟进助手｜大陆离线版")
        root.geometry("1420x760")
        self.store = ReturnFollowupStore(default_data_path())

        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        actions = [
            ("新增案件", self.add),
            ("编辑案件", self.edit),
            ("删除案件", self.delete),
            ("导入 CSV", self.import_csv),
            ("导出全部 CSV", self.export_csv),
            ("售后汇总", self.summary),
            ("导出 3 日内跟进", self.export_actions),
            ("备份", self.backup),
            ("恢复备份", self.restore),
        ]
        for label, action in actions:
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=3)

        area = ttk.Frame(root, padding=(8, 0, 8, 4))
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=DISPLAY_COLUMNS, show="headings")
        widths = (160, 190, 105, 105, 120, 120, 130, 100, 120)
        for column, width in zip(DISPLAY_COLUMNS, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=90, stretch=True)
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

        def sort_key(row):
            risk = case_risk(row, as_of=today)
            return (
                row["处理状态"] in {"已完成", "已关闭"},
                not risk["需要跟进"],
                risk["提醒日期"] or "9999-12-31",
                row["订单编号"],
            )

        ordered = sorted(self.store.rows, key=sort_key)
        for row in ordered:
            risk = case_risk(row, as_of=today)
            reminder = risk["待处理类型"]
            if risk["逾期天数"]:
                reminder += f" {risk['逾期天数']} 天"
            self.tree.insert(
                "", "end", iid=row["记录编号"],
                values=(
                    row["订单编号"], row["商品/SKU"], row["售后类型"],
                    row["处理状态"], row["处理截止日期"], row["下次跟进日期"],
                    row["实际退款金额(元)"], risk["提醒事项"], reminder,
                ),
            )
        report = after_sales_summary(self.store.rows, as_of=today)
        self.status.set(
            f"共 {report['案件总数']} 案｜未结 {report['未结案件数']}｜"
            f"逾期 {report['逾期案件数']}｜待退款 {report['待退款案件数']}｜"
            f"已登记售后支出 ¥{report['已登记售后支出(元)']}｜"
            "数据保存在本机 %LOCALAPPDATA%/MainlandBusinessTools"
        )

    def selected_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条售后案件。")
            return None
        return selected[0]

    def dialog(self, title, original=None):
        editing = original is not None
        today = date.today().isoformat()
        defaults = {
            "记录编号": "XY-R-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
            "订单编号": "",
            "商品/SKU": "",
            "售后类型": "退货退款",
            "申请日期": today,
            "订单成交金额(元)": "0.00",
            "申请金额(元)": "0.00",
            "实际退款金额(元)": "0.00",
            "补偿金额(元)": "0.00",
            "退货运费(元)": "0.00",
            "运费承担方": "待确认",
            "责任归属": "待核实",
            "处理状态": "待沟通",
            "处理截止日期": "",
            "下次跟进日期": "",
            "下一步动作": "",
            "买家寄回运单号": "",
            "买家寄回日期": "",
            "卖家收货日期": "",
            "退款完成日期": "",
            "本地证据目录": "",
            "处理摘要": "",
            "备注": "",
        }
        values = dict(defaults)
        if editing:
            values.update(original)

        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("940x720")
        window.transient(self.root)
        window.grab_set()
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        widgets = {}

        choices = {
            "售后类型": CASE_TYPES,
            "运费承担方": FREIGHT_PAYER,
            "责任归属": RESPONSIBILITIES,
            "处理状态": STATUSES,
        }
        for index, field in enumerate(FIELDS):
            row_index = index // 2
            column = (index % 2) * 2
            ttk.Label(body, text=field).grid(
                row=row_index, column=column, sticky="e", padx=6, pady=5
            )
            if field in choices:
                widget = ttk.Combobox(
                    body, values=choices[field], state="readonly", width=34
                )
                widget.set(values.get(field, ""))
            else:
                widget = ttk.Entry(body, width=38)
                widget.insert(0, values.get(field, ""))
                if field == "记录编号" and editing:
                    widget.configure(state="readonly")
            widget.grid(row=row_index, column=column + 1, sticky="ew", padx=6, pady=5)
            widgets[field] = widget

        body.columnconfigure(1, weight=1)
        body.columnconfigure(3, weight=1)
        note = (
            "日期使用 YYYY-MM-DD；金额使用人民币元。处理截止日期是需完成处理的期限，"
            "下次跟进日期是你计划再次检查/联系的日期；两项分别提醒，未填写下次跟进日期时"
            "仍按处理截止日期提醒。提醒只按本机日期计算，不代表平台官方时限。"
        )
        ttk.Label(body, text=note, foreground="#666", wraplength=880).grid(
            row=(len(FIELDS) + 1) // 2, column=0, columnspan=4,
            sticky="w", padx=6, pady=(12, 8),
        )

        def save():
            candidate = {}
            for field, widget in widgets.items():
                candidate[field] = widget.get().strip()
            try:
                if editing:
                    self.store.update(original["记录编号"], candidate)
                else:
                    self.store.add(candidate)
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)
                return
            window.destroy()
            self.refresh()

        buttons = ttk.Frame(body)
        buttons.grid(
            row=(len(FIELDS) + 1) // 2 + 1,
            column=0, columnspan=4, sticky="e", pady=10,
        )
        ttk.Button(buttons, text="取消", command=window.destroy).pack(side="right", padx=5)
        ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=5)
        window.wait_window()

    def add(self):
        self.dialog("新增售后案件")

    def edit(self):
        case_id = self.selected_id()
        if not case_id:
            return
        row = next(item for item in self.store.rows if item["记录编号"] == case_id)
        self.dialog("编辑售后案件", row)

    def delete(self):
        case_id = self.selected_id()
        if not case_id:
            return
        if not messagebox.askyesno("确认删除", "删除后无法从当前台账恢复，建议先备份。"):
            return
        try:
            self.store.delete(case_id)
        except (OSError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.refresh()

    def import_csv(self):
        path = filedialog.askopenfilename(
            title="选择售后案件 CSV",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            count = self.store.import_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self.refresh()
        messagebox.showinfo("导入完成", f"成功导入 {count} 条记录。")

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            title="导出全部售后案件",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not path:
            return
        try:
            self.store.export_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        messagebox.showinfo("导出完成", f"已导出 {len(self.store.rows)} 条记录。")

    def export_actions(self):
        path = filedialog.asksaveasfilename(
            title="导出 3 日内需跟进案件",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not path:
            return
        try:
            count = self.store.export_action_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        messagebox.showinfo("导出完成", f"已导出 {count} 条需跟进案件。")

    def summary(self):
        report = after_sales_summary(self.store.rows)
        counts = "\n".join(
            f"{status}：{count}" for status, count in report["状态数量"].items()
        )
        messagebox.showinfo(
            "售后汇总",
            f"案件总数：{report['案件总数']}\n"
            f"未结案件：{report['未结案件数']}\n"
            f"逾期案件：{report['逾期案件数']}\n"
            f"待退款：{report['待退款案件数']}\n"
            f"待退货/验收：{report['待退货或验收案件数']}\n"
            f"平台处理中：{report['平台处理中案件数']}\n"
            f"实际退款：¥{report['实际退款合计(元)']}\n"
            f"补偿：¥{report['补偿合计(元)']}\n"
            f"卖家承担退货运费：¥{report['卖家承担退货运费(元)']}\n"
            f"已登记售后支出：¥{report['已登记售后支出(元)']}\n\n{counts}",
        )

    def backup(self):
        path = filedialog.asksaveasfilename(
            title="备份售后台账",
            defaultextension=".json",
            filetypes=[("JSON 备份", "*.json")],
        )
        if not path:
            return
        try:
            self.store.backup(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("备份失败", str(exc))
            return
        messagebox.showinfo("备份完成", "已生成 SHA256 校验备份。")

    def restore(self):
        path = filedialog.askopenfilename(
            title="选择售后台账备份",
            filetypes=[("JSON 备份", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno("确认恢复", "恢复会替换当前售后台账，建议先备份当前数据。"):
            return
        try:
            self.store.restore(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        self.refresh()
        messagebox.showinfo("恢复完成", "备份已通过 SHA256 校验并恢复。")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.getenv("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()
