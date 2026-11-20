"""门店优惠券与活动核销助手：本地管理活动、发行券码和核销记录。"""
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.store_coupon import CouponStore, filter_coupon_rows, paginate_coupon_rows, self_test as core_self_test

PRODUCT = "门店优惠券与活动核销助手"


def default_data_path():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return base / "MainlandBusinessTools" / "store-coupon-ledger.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.store = CouponStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1180x740")
        self.minsize(1040, 640)
        self.page = 1
        self.page_size = 100

        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self,
            text="离线登记营销活动、优惠券发行和逐笔核销；不连接支付平台，不生成平台官方券。",
            foreground="#666",
        ).pack(anchor="w", padx=18, pady=(0, 10))

        self.summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=18, pady=(0, 8))

        filter_bar = ttk.Frame(self, padding=(18, 0))
        filter_bar.pack(fill="x", pady=(0, 4))
        ttk.Label(filter_bar, text="关键词").pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar(value="")
        ttk.Entry(filter_bar, textvariable=self.search_var, width=28).pack(side="left", padx=(0, 10))
        ttk.Label(filter_bar, text="状态").pack(side="left", padx=(0, 6))
        self.status_var = tk.StringVar(value="全部")
        self.status_combo = ttk.Combobox(
            filter_bar, textvariable=self.status_var, state="readonly",
            values=("全部", "未使用", "已核销", "已作废"), width=9,
        )
        self.status_combo.pack(side="left")
        self.page_info = tk.StringVar(value="第 1/1 页")
        ttk.Label(filter_bar, textvariable=self.page_info, anchor="e").pack(side="right", padx=(8, 0))
        self.next_button = ttk.Button(filter_bar, text="下一页", command=self.next_page)
        self.next_button.pack(side="right", padx=(4, 0))
        self.prev_button = ttk.Button(filter_bar, text="上一页", command=self.prev_page)
        self.prev_button.pack(side="right", padx=(4, 0))
        self.search_var.trace_add("write", self._filter_changed)
        self.status_combo.bind("<<ComboboxSelected>>", self._filter_changed)

        columns = (
            "code", "campaign", "discount", "minimum", "status",
            "created", "order", "spend", "actual_discount",
        )
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=19)
        headings = {
            "code": ("券编号", 170),
            "campaign": ("活动名称", 170),
            "discount": ("优惠金额", 90),
            "minimum": ("最低消费", 90),
            "status": ("状态", 80),
            "created": ("生成时间", 145),
            "order": ("核销订单号", 140),
            "spend": ("实际消费", 90),
            "actual_discount": ("实际优惠", 90),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=18, pady=6)

        actions = ttk.Frame(self, padding=(18, 8))
        actions.pack(fill="x")
        buttons = [
            ("新建活动", self.add_campaign),
            ("发行优惠券", self.issue_coupons),
            ("核销优惠券", self.redeem_coupon),
            ("作废优惠券", self.void_coupon),
            ("启用/停用活动", self.toggle_campaign),
            ("导入活动 CSV", self.import_campaigns),
            ("导出活动", self.export_campaigns),
            ("导出优惠券", self.export_coupons),
            ("导出核销报表", self.export_redemptions),
            ("导出活动汇总", self.export_campaign_report),
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
        self.refresh(reset_page=True)

    def _campaign_text(self):
        if not self.store.campaigns:
            return "当前没有活动。"
        return "\n".join(
            f"{item['活动编号']}｜{item['活动名称']}｜{item['状态']}｜"
            f"¥{item['优惠金额']} / 满 ¥{item['最低消费金额']}｜"
            f"{item['开始日期']} 至 {item['结束日期']}"
            for item in self.store.campaigns[-30:]
        )

    def _selected_coupon_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("选择优惠券", "请先在列表中选择一张优惠券。", parent=self)
            return None
        return str(self.tree.item(selected[0], "values")[0])

    def _ask_operator(self):
        return simpledialog.askstring("操作人", "请输入操作人（可留空）：", parent=self) or "本机用户"

    def _filter_changed(self, *_):
        self.page = 1
        self.refresh()

    def prev_page(self):
        self.page = max(1, self.page - 1)
        self.refresh()

    def next_page(self):
        self.page += 1
        self.refresh()

    def refresh(self, reset_page=False):
        if reset_page:
            self.page = 1
        for item in self.tree.get_children():
            self.tree.delete(item)
        filtered = filter_coupon_rows(self.store.coupons, self.search_var.get(), self.status_var.get())
        filtered.reverse()  # newest coupons appear first
        page_rows, self.page, page_count, total = paginate_coupon_rows(filtered, self.page, self.page_size)
        for coupon in page_rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    coupon["券编号"],
                    coupon["活动名称"],
                    coupon["优惠金额"],
                    coupon["最低消费金额"],
                    coupon["状态"],
                    coupon["生成时间"].replace("T", " "),
                    coupon["核销订单号"],
                    coupon["实际消费金额"],
                    coupon["实际优惠金额"],
                ),
            )
        start = (self.page - 1) * self.page_size + 1 if total else 0
        end = min(self.page * self.page_size, total)
        self.page_info.set(f"第 {self.page}/{page_count} 页 · 显示 {start}-{end} / {total} 张（每页 {self.page_size} 张）")
        self.prev_button.configure(state="normal" if self.page > 1 else "disabled")
        self.next_button.configure(state="normal" if self.page < page_count else "disabled")
        summary = self.store.summary()
        self.summary_var.set(
            f"活动 {summary['活动数量']} 个　已发行 {summary['发行优惠券']} 张"
            f"　已核销 {summary['已核销']} 张　未使用 {summary['未使用']} 张"
            f"　已作废 {summary['已作废']} 张　已过期 {summary['已过期']} 张"
            f"　实际优惠合计：¥{summary['实际优惠合计']}"
        )

    def add_campaign(self):
        today = date.today()
        name = simpledialog.askstring("新建活动", "活动名称：", parent=self)
        if not name:
            return
        discount = simpledialog.askstring("优惠金额", "每张券优惠金额（元）：", parent=self)
        if discount is None:
            return
        minimum = simpledialog.askstring("最低消费", "最低消费金额（元）：", parent=self)
        if minimum is None:
            return
        start = simpledialog.askstring("开始日期", "活动开始日期 YYYY-MM-DD：", initialvalue=today.isoformat(), parent=self)
        if start is None:
            return
        end = simpledialog.askstring(
            "结束日期",
            "活动结束日期 YYYY-MM-DD：",
            initialvalue=(today + timedelta(days=30)).isoformat(),
            parent=self,
        )
        if end is None:
            return
        limit = simpledialog.askstring("发行上限", "本活动最多发行多少张券？", initialvalue="100", parent=self)
        if limit is None:
            return
        note = simpledialog.askstring("活动备注", "活动备注（可留空）：", parent=self) or ""
        try:
            campaign_id = self.store.create_campaign(
                {
                    "活动名称": name,
                    "优惠金额": discount,
                    "最低消费金额": minimum,
                    "开始日期": start,
                    "结束日期": end,
                    "发行上限": limit,
                    "备注": note,
                },
                actor=self._ask_operator(),
            )
            self.refresh(reset_page=True)
            messagebox.showinfo("活动已建立", f"活动编号：{campaign_id}", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("新建活动失败", str(exc), parent=self)

    def issue_coupons(self):
        if not self.store.campaigns:
            messagebox.showinfo("发行优惠券", "请先新建营销活动。", parent=self)
            return
        campaign_id = simpledialog.askstring(
            "发行优惠券",
            "请输入活动编号：\n" + self._campaign_text(),
            parent=self,
        )
        if not campaign_id:
            return
        count = simpledialog.askstring("发行数量", "本次发行张数（最多 5000）：", initialvalue="10", parent=self)
        if count is None:
            return
        try:
            codes = self.store.issue_coupons(campaign_id.strip(), count, actor=self._ask_operator())
            self.refresh(reset_page=True)
            messagebox.showinfo(
                "发行完成",
                f"已生成 {len(codes)} 张本地券码。\n"
                "请由门店自行核对并通过已有渠道告知顾客；软件不会发送短信或创建平台券。",
                parent=self,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("发行失败", str(exc), parent=self)

    def redeem_coupon(self):
        coupon_id = self._selected_coupon_id()
        if not coupon_id:
            return
        order = simpledialog.askstring("核销订单", "请输入本次消费订单号：", parent=self)
        if order is None:
            return
        spend = simpledialog.askstring("实际消费", "请输入实际消费金额（元）：", parent=self)
        if spend is None:
            return
        note = simpledialog.askstring("核销备注", "备注（可留空）：", parent=self) or ""
        try:
            self.store.redeem(coupon_id, order, spend, actor=self._ask_operator(), note=note)
            self.refresh(reset_page=True)
            messagebox.showinfo("核销完成", "优惠券已记录为已核销。请按门店实际收款结果核对。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("核销失败", str(exc), parent=self)

    def void_coupon(self):
        coupon_id = self._selected_coupon_id()
        if not coupon_id:
            return
        reason = simpledialog.askstring("作废优惠券", "请输入作废原因：", parent=self)
        if reason is None:
            return
        try:
            self.store.void_coupon(coupon_id, reason, actor=self._ask_operator())
            self.refresh(reset_page=True)
            messagebox.showinfo("作废完成", "优惠券已作废，不能再次核销。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("作废失败", str(exc), parent=self)

    def toggle_campaign(self):
        if not self.store.campaigns:
            messagebox.showinfo("活动状态", "当前没有活动。", parent=self)
            return
        campaign_id = simpledialog.askstring(
            "修改活动状态",
            "请输入活动编号：\n" + self._campaign_text(),
            parent=self,
        )
        if not campaign_id:
            return
        try:
            campaign = self.store._campaign(campaign_id.strip())
            target = "停用" if campaign["状态"] == "启用" else "启用"
            reason = simpledialog.askstring("状态变更原因", "原因（可留空）：", parent=self) or ""
            self.store.set_campaign_status(campaign_id.strip(), target, self._ask_operator(), reason)
            self.refresh(reset_page=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("修改活动状态失败", str(exc), parent=self)

    def import_campaigns(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")], parent=self)
        if not path:
            return
        try:
            count = self.store.import_campaigns_csv(path)
            self.refresh(reset_page=True)
            messagebox.showinfo(
                "导入完成",
                f"成功导入 {count} 个活动。任何一行无效都会导致整批不写入。",
                parent=self,
            )
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def _export(self, title, method, extension=".csv"):
        path = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[("CSV 文件", "*.csv")] if extension == ".csv" else [("JSON 备份", "*.json")],
            parent=self,
        )
        if not path:
            return
        try:
            method(path)
            messagebox.showinfo(title, "已导出 UTF-8 BOM CSV。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror(title + "失败", str(exc), parent=self)

    def export_campaigns(self):
        self._export("导出活动", self.store.export_campaigns_csv)

    def export_coupons(self):
        self._export("导出优惠券", self.store.export_coupons_csv)

    def export_redemptions(self):
        self._export("导出核销报表", self.store.export_redemptions_csv)

    def export_campaign_report(self):
        self._export("导出活动汇总", self.store.export_campaign_report_csv)

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 备份", "*.json")], parent=self
        )
        if not path:
            return
        try:
            self.store.backup(path)
            messagebox.showinfo("备份完成", "备份包含 SHA256 完整性摘要和操作日志。", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("备份失败", str(exc), parent=self)

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")], parent=self)
        if not path or not messagebox.askyesno(
            "确认恢复", "恢复会替换当前活动和优惠券记录，建议先备份。是否继续？", parent=self
        ):
            return
        try:
            self.store.restore(path)
            self.refresh(reset_page=True)
            messagebox.showinfo("恢复完成", "备份校验通过，恢复操作已写入本地日志。", parent=self)
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
