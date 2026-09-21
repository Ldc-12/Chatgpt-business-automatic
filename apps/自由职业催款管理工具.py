import csv
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

FIELDS = ["客户", "账单编号", "金额", "币种", "到期日", "状态", "上次跟进", "下次跟进", "备注"]

def parse_amount(value):
    s = str(value).strip().replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").replace(" ", "")
    if not s:
        return 0.0
    return float(s)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自由职业催款管理工具｜大陆版")
        self.geometry("1100x650")
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=10)
        actions = [
            ("导入 CSV", self.import_csv), ("新增", self.add_row),
            ("删除选中", self.delete_row), ("导出 CSV", self.export_csv),
            ("逾期统计", self.stats)
        ]
        for label, cmd in actions:
            ttk.Button(bar, text=label, command=cmd).pack(side="left", padx=4)

        self.tree = ttk.Treeview(self, columns=FIELDS, show="headings")
        widths = [130, 110, 100, 70, 105, 90, 105, 105, 230]
        for f, w in zip(FIELDS, widths):
            self.tree.heading(f, text=f)
            self.tree.column(f, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=5)
        ttk.Label(
            self,
            text="适用于 WPS/Excel 导出的 CSV；金额支持 1,200 / ￥1200 等常见写法。",
            anchor="w"
        ).pack(fill="x", padx=12, pady=8)

    def add_row(self):
        self.tree.insert("", "end", values=[""] * len(FIELDS))

    def delete_row(self):
        for item in self.tree.selection():
            self.tree.delete(item)

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                missing = [x for x in FIELDS if x not in (reader.fieldnames or [])]
                if missing:
                    raise ValueError("缺少字段：" + "、".join(missing))
                for item in self.tree.get_children():
                    self.tree.delete(item)
                for row in reader:
                    self.tree.insert("", "end", values=[row.get(x, "") for x in FIELDS])
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                for item in self.tree.get_children():
                    writer.writerow(dict(zip(FIELDS, self.tree.item(item, "values"))))
            messagebox.showinfo("导出完成", "已导出：" + os.path.basename(path))
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def stats(self):
        rows = [dict(zip(FIELDS, self.tree.item(i, "values"))) for i in self.tree.get_children()]
        overdue = [r for r in rows if str(r["状态"]).strip().lower() in ("逾期", "overdue")]
        total = 0.0
        invalid = 0
        for row in overdue:
            try:
                total += parse_amount(row["金额"])
            except ValueError:
                invalid += 1
        msg = f"逾期账单：{len(overdue)}\n逾期金额：￥{total:,.2f}"
        if invalid:
            msg += f"\n金额无法识别：{invalid} 条"
        messagebox.showinfo("逾期统计", msg)

def self_test():
    assert parse_amount("1,200.50") == 1200.5
    assert parse_amount("￥2,000") == 2000
    assert parse_amount(" 300 ") == 300
    assert FIELDS[0] == "客户" and FIELDS[-1] == "备注"
    return True

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        print("SELF_TEST_OK")
    else:
        App().mainloop()
