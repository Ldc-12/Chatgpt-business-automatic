import csv
import datetime as dt
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

FIELDS = ["客户", "账单编号", "金额", "币种", "到期日", "状态", "上次跟进", "下次跟进", "备注"]
STATUSES = ["待跟进", "已发送", "部分付款", "已付款", "逾期"]


def parse_amount(value):
    s = str(value).strip().replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").replace(" ", "")
    if not s:
        return 0.0
    return float(s)


def today():
    return dt.date.today().isoformat()


def days_until(date_text):
    try:
        return (dt.date.fromisoformat(str(date_text).strip()) - dt.date.today()).days
    except ValueError:
        return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自由职业催款管理工具｜大陆版")
        self.geometry("1250x720")
        self.minsize(1050, 620)
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(10, 5))

        actions = [
            ("新增", self.add_row),
            ("编辑选中", self.edit_row),
            ("删除", self.delete_row),
            ("导入 CSV", self.import_csv),
            ("导出 CSV", self.export_csv),
            ("逾期统计", self.stats),
            ("催款话术", self.copy_followup),
        ]
        for label, cmd in actions:
            ttk.Button(bar, text=label, command=cmd).pack(side="left", padx=3)

        ttk.Label(bar, text="搜索").pack(side="left", padx=(18, 4))
        self.search_var = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.search_var, width=24)
        search.pack(side="left")
        search.bind("<KeyRelease>", lambda e: self.refresh_view())

        self.filter_var = tk.StringVar(value="全部")
        ttk.Combobox(
            bar, textvariable=self.filter_var, values=["全部", "待跟进", "已发送", "部分付款", "已付款", "逾期", "本周到期"],
            state="readonly", width=11
        ).pack(side="left", padx=6)
        self.filter_var.trace_add("write", lambda *_: self.refresh_view())

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=5)

        self.tree = ttk.Treeview(frame, columns=FIELDS, show="headings", selectmode="extended")
        widths = [130, 110, 100, 70, 105, 90, 105, 105, 230]
        for f, w in zip(FIELDS, widths):
            self.tree.heading(f, text=f)
            self.tree.column(f, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_row())

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self.status_var = tk.StringVar(value="0 条记录")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12, pady=(2, 0))
        ttk.Label(
            self,
            text="双击行即可编辑；日期建议使用 YYYY-MM-DD。数据只保存在你自己的电脑/CSV，不上传云端。",
            anchor="w"
        ).pack(fill="x", padx=12, pady=8)

    def all_rows(self):
        return [dict(zip(FIELDS, self.tree.item(i, "values"))) for i in self.tree.get_children()]

    def add_row(self):
        values = ["", "", "", "CNY", "", "待跟进", "", today(), ""]
        item = self.tree.insert("", "end", values=values)
        self.tree.selection_set(item)
        self.tree.see(item)
        self.edit_row()

    def edit_row(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条记录。")
            return
        item = selection[0]
        old = list(self.tree.item(item, "values"))
        win = tk.Toplevel(self)
        win.title("编辑账单")
        win.transient(self)
        win.grab_set()
        vars_ = []
        for i, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=i, column=0, padx=10, pady=5, sticky="w")
            var = tk.StringVar(value=old[i] if i < len(old) else "")
            vars_.append(var)
            if field == "状态":
                ttk.Combobox(win, textvariable=var, values=STATUSES, state="readonly", width=32).grid(row=i, column=1, padx=10, pady=5)
            else:
                ttk.Entry(win, textvariable=var, width=35).grid(row=i, column=1, padx=10, pady=5)

        def save():
            vals = [v.get().strip() for v in vars_]
            if not vals[0]:
                messagebox.showwarning("提示", "客户名称不能为空。", parent=win)
                return
            if vals[2]:
                try:
                    parse_amount(vals[2])
                except ValueError:
                    messagebox.showwarning("提示", "金额格式无法识别。", parent=win)
                    return
            self.tree.item(item, values=vals)
            self.refresh_view()
            win.destroy()

        ttk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, padx=10, pady=12)
        ttk.Button(win, text="取消", command=win.destroy).grid(row=len(FIELDS), column=1, padx=10, pady=12, sticky="e")

    def delete_row(self):
        for item in self.tree.selection():
            self.tree.delete(item)
        self.refresh_view()

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
            self.refresh_view()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                for row in self.all_rows():
                    writer.writerow(row)
            messagebox.showinfo("导出完成", "已导出：" + os.path.basename(path))
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def refresh_view(self):
        # Treeview itself is the data store; filtering rebuilds the visible rows from a snapshot.
        rows = self.all_rows()
        query = self.search_var.get().strip().lower()
        filt = self.filter_var.get()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            text = " ".join(row.values()).lower()
            if query and query not in text:
                continue
            if filt in STATUSES and row["状态"] != filt:
                continue
            if filt == "本周到期":
                d = days_until(row["下次跟进"])
                if d is None or d < 0 or d > 7:
                    continue
            self.tree.insert("", "end", values=[row[f] for f in FIELDS])
        self.status_var.set(f"{len(self.tree.get_children())} 条记录")

    def stats(self):
        rows = self.all_rows()
        overdue = [r for r in rows if r["状态"] == "逾期"]
        total = 0.0
        invalid = 0
        for row in overdue:
            try:
                total += parse_amount(row["金额"])
            except ValueError:
                invalid += 1
        due_soon = sum(1 for r in rows if (days_until(r["下次跟进"]) is not None and 0 <= days_until(r["下次跟进"]) <= 7))
        msg = f"账单总数：{len(rows)}\n逾期账单：{len(overdue)}\n逾期金额：￥{total:,.2f}\n未来7天需跟进：{due_soon}"
        if invalid:
            msg += f"\n金额无法识别：{invalid} 条"
        messagebox.showinfo("经营统计", msg)

    def copy_followup(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条账单。")
            return
        row = dict(zip(FIELDS, self.tree.item(selection[0], "values")))
        amount = row["金额"] or "待确认"
        due = row["到期日"] or "约定日期"
        text = (
            f"您好，{row['客户']}，跟进一下账单 {row['账单编号'] or '（未填写编号）'}。"
            f"本次金额为 {row['币种'] or 'CNY'} {amount}，原定到期日为 {due}。"
            "如果已经安排付款，麻烦告知一下预计到账时间；如有任何问题也可以直接和我说，谢谢。"
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        messagebox.showinfo("催款话术", "已复制到剪贴板，可直接粘贴到微信/QQ/邮件。")


def self_test():
    assert parse_amount("1,200.50") == 1200.5
    assert parse_amount("￥2,000") == 2000
    assert parse_amount(" 300 ") == 300
    assert FIELDS[0] == "客户" and FIELDS[-1] == "备注"
    assert days_until(today()) == 0
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        print("SELF_TEST_OK")
    else:
        App().mainloop()
