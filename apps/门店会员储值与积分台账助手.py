"""门店会员储值与积分台账助手：本地记录会员、储值和不可变交易流水。"""
import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.store_membership import MemberStore, self_test as core_self_test

PRODUCT = "门店会员储值与积分台账助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return base / "MainlandBusinessTools" / "store-membership-ledger.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.store = MemberStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1120x720")
        self.minsize(980, 620)

        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self,
            text="本地会员资料、储值余额、积分与逐笔流水；不连接支付平台，也不代收款。",
            foreground="#666",
        ).pack(anchor="w", padx=18, pady=(0, 10))

        self.summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=18, pady=(0, 8))

        columns = ("member_id", "name", "phone", "balance", "points", "status", "joined")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=18)
        headings = {
            "member_id": ("会员编号", 150),
            "name": ("会员姓名", 150),
            "phone": ("联系电话", 140),
            "balance": ("储值余额（元）", 130),
            "points": ("积分", 90),
            "status": ("状态", 80),
            "joined": ("入会日期", 110),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=18, pady=6)

        actions = ttk.Frame(self, padding=(18, 8))
        actions.pack(fill="x")
        buttons = [
            ("新增会员", self.add_member),
            ("充值", self.recharge),
            ("消费", self.consume),
            ("办理退款", self.refund),
            ("积分兑换", self.redeem_points),
            ("启用/停用", self.toggle_status),
            ("导入会员 CSV", self.import_members),
            ("导出会员", self.export_members),
            ("导出交易流水", self.export_transactions),
            ("导出余额报表", self.export_balances),
            ("备份", self.backup),
            ("恢复", self.restore),
            ("校验日志", self.verify_log),
            ("刷新", self.refresh),
        ]
        for index, (label, callback) in enumerate(buttons):
            ttk.Button(actions, text=label, command=callback).grid(
                row=index // 7, column=index % 7, padx=3, pady=4, sticky="ew"
            )
        for column in range(7):
            actions.columnconfigure(column, weight=1)
        self.refresh()

    def _selected_member_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("选择会员", "请先在列表中选择一位会员。", parent=self)
            return None
        return str(self.tree.item(selected[0], "values")[0])

    def _ask_operator(self):
        return simpledialog.askstring("操作人", "请输入操作人（可留空）：", parent=self) or "本机用户"

    def _ask_note(self, title="备注"):
        return simpledialog.askstring(title, "备注或原因（可留空）：", parent=self) or ""

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        states = self.store._states()
        for member in self.store.members:
            state = states[member["会员编号"]]
            self.tree.insert(
                "",
                "end",
                values=(
                    member["会员编号"],
                    member["会员姓名"],
                    member["联系电话"],
                    format(state["balance"], ".2f"),
                    state["points"],
                    member["状态"],
                    member["入会日期"],
                ),
            )
        summary = self.store.summary()
        self.summary_var.set(
            f"会员 {summary['会员总数']} 人（正常 {summary['正常会员']} / 停用 {summary['停用会员']}）"
            f"　未用储值余额合计：¥{summary['储值余额合计']}"
            f"　积分余额合计：{summary['积分余额合计']}"
            f"　交易流水：{summary['交易流水数']} 笔"
        )

    def add_member(self):
        name = simpledialog.askstring("新增会员", "会员姓名：", parent=self)
        if not name:
            return
        phone = simpledialog.askstring("联系电话", "联系电话（可留空）：", parent=self) or ""
        note = self._ask_note()
        try:
            member_id = self.store.add_member(
                {"会员姓名": name, "联系电话": phone, "备注": note},
                actor=self._ask_operator(),
            )
            self.refresh()
            messagebox.showinfo("新增成功", f"会员编号：{member_id}", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("新增会员失败", str(exc), parent=self)

    def _post_amount(self, action, title):
        member_id = self._selected_member_id()
        if not member_id:
            return
        amount = simpledialog.askstring(title, "金额（人民币，最多两位小数）：", parent=self)
        if amount is None:
            return
        try:
            transaction_id = action(member_id, amount, operator=self._ask_operator(), note=self._ask_note())
            self.refresh()
            messagebox.showinfo("交易已记录", f"流水编号：{transaction_id}", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"{title}失败", str(exc), parent=self)

    def recharge(self):
        self._post_amount(self.store.recharge, "会员充值")

    def consume(self):
        self._post_amount(self.store.consume, "会员消费")

    def refund(self):
        member_id = self._selected_member_id()
        if not member_id:
            return
        candidates = self.store.list_refundable_transactions(member_id)
        if not candidates:
            messagebox.showinfo("办理退款", "该会员没有可退款的消费流水。", parent=self)
            return
        choices = "\n".join(
            f"{tx['流水编号']}｜消费 ¥{tx['交易金额']}｜剩余可退 ¥{tx['可退金额']}"
            for tx in candidates[-20:]
        )
        reference = simpledialog.askstring(
            "选择原消费流水",
            "请输入要退款的原消费流水编号（列表仅显示最近 20 笔）：\n" + choices,
            parent=self,
        )
        if not reference:
            return
        amount = simpledialog.askstring("退款金额", "本次退款金额（人民币）：", parent=self)
        if amount is None:
            return
        try:
            txid = self.store.refund(
                member_id,
                amount,
                reference.strip(),
                operator=self._ask_operator(),
                note=self._ask_note("退款原因/备注"),
            )
            self.refresh()
            messagebox.showinfo("退款流水已记录", f"流水编号：{txid}", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("退款失败", str(exc), parent=self)

    def redeem_points(self):
        member_id = self._selected_member_id()
        if not member_id:
            return
        points = simpledialog.askstring("积分兑换", "兑换积分数量（正整数）：", parent=self)
        if points is None:
            return
        try:
            txid = self.store.redeem_points(
                member_id,
                points,
                operator=self._ask_operator(),
                note=self._ask_note("兑换说明"),
            )
            self.refresh()
            messagebox.showinfo("兑换已记录", f"流水编号：{txid}", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("积分兑换失败", str(exc), parent=self)

    def toggle_status(self):
        member_id = self._selected_member_id()
        if not member_id:
            return
        member = self.store._member(member_id)
        target = "停用" if member["状态"] == "正常" else "正常"
        reason = self._ask_note("状态变更原因")
        try:
            self.store.set_member_status(member_id, target, self._ask_operator(), reason)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("修改状态失败", str(exc), parent=self)

    def import_members(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")], parent=self)
        if not path:
            return
        try:
            count = self.store.import_members_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 位会员。\n导入采用整批校验，任何一行不合格都不会写入。", parent=self)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def _export(self, title, method):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")], parent=self
        )
        if not path:
            return
        try:
            method(path)
            messagebox.showinfo(title, "已导出 UTF-8 BOM CSV。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror(title + "失败", str(exc), parent=self)

    def export_members(self):
        self._export("导出会员资料", self.store.export_members_csv)

    def export_transactions(self):
        self._export("导出交易流水", self.store.export_transactions_csv)

    def export_balances(self):
        self._export("导出会员余额", self.store.export_balances_csv)

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")], parent=self
        )
        if not path:
            return
        try:
            self.store.backup(path)
            messagebox.showinfo("备份完成", "备份文件已写入并包含 SHA256 完整性校验。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("备份失败", str(exc), parent=self)

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")], parent=self)
        if not path or not messagebox.askyesno(
            "确认恢复", "恢复会替换当前会员和交易数据，建议先备份。是否继续？", parent=self
        ):
            return
        try:
            self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", "备份已校验并恢复；恢复操作已写入本地日志。", parent=self)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            messagebox.showerror("恢复失败", str(exc), parent=self)

    def verify_log(self):
        try:
            summary = self.store.audit_summary()
            messagebox.showinfo(
                "操作日志校验",
                f"SHA256 链校验通过。\n累计事件：{summary['事件数']}\n"
                f"最后操作：{summary['最后操作'] or '无'}\n"
                f"最新摘要：{summary['最新摘要'] or '暂无日志'}",
                parent=self,
            )
        except ValueError as exc:
            messagebox.showerror("日志校验失败", str(exc), parent=self)


def self_test():
    core_self_test()


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App().mainloop()
