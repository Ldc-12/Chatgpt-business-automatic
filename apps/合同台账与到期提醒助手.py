"""Offline contract register and expiry reminder for Mainland Windows users."""
import csv
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.contract_workflow import (WorkflowStore, MILESTONE_FIELDS, MILESTONE_TYPES, MILESTONE_STATUSES, AUDIT_FIELDS, WORKFLOW_FORMAT, WORKFLOW_VERSION, risk_findings, finance_summary)
from src.contract_document_parser import write_draft_csv

PRODUCT = "合同台账与到期提醒助手"
FIELDS = ["合同编号", "合同名称", "甲方/客户", "乙方/供应商", "签订日期", "生效日期", "到期日期",
          "合同金额", "续约提醒提前天数", "状态", "负责人", "联系方式", "备注"]
STATUSES = ["执行中", "待续约", "已续约", "已到期", "已终止"]
BACKUP_FORMAT = "mainland-contract-ledger"
BACKUP_VERSION = 2


def money(value):
    if value is None or not str(value).strip():
        raise ValueError("合同金额不能为空；无偿合同请明确填写 0")
    try:
        amount = Decimal(str(value or "0").replace(",", "").strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("合同金额必须是有效数字")
    if not amount.is_finite() or amount < 0:
        raise ValueError("合同金额不能为负数或无效数值")
    return str(amount)


def iso_date(value, field):
    value = str(value or "").strip()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 日期格式")


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("合同记录必须是对象")
    item = {f: str(row.get(f, "")).strip() for f in FIELDS}
    if not item["合同编号"] or not item["合同名称"]:
        raise ValueError("合同编号和合同名称不能为空")
    item["签订日期"] = iso_date(item["签订日期"], "签订日期")
    item["生效日期"] = iso_date(item["生效日期"], "生效日期")
    item["到期日期"] = iso_date(item["到期日期"], "到期日期")
    if item["生效日期"] > item["到期日期"]:
        raise ValueError("生效日期不能晚于到期日期")
    if item["签订日期"] > item["到期日期"]:
        raise ValueError("签订日期不能晚于到期日期")
    item["合同金额"] = money(item["合同金额"])
    try:
        days = int(item["续约提醒提前天数"] or "30")
    except ValueError:
        raise ValueError("续约提醒提前天数必须为整数")
    if days < 0 or days > 3650:
        raise ValueError("续约提醒提前天数须在 0 至 3650 天之间")
    item["续约提醒提前天数"] = str(days)
    if item["状态"] not in STATUSES:
        raise ValueError("合同状态无效")
    return item


def reminder_state(item, today=None):
    today = today or date.today()
    end = date.fromisoformat(item["到期日期"])
    days_left = (end - today).days
    if item["状态"] in ("已终止", "已续约"):
        return "无需提醒", days_left
    if days_left < 0:
        return "已逾期", days_left
    if days_left <= int(item["续约提醒提前天数"]):
        return "即将到期", days_left
    return "正常", days_left


class ContractStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def check_unique(rows):
        ids = [r["合同编号"] for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("合同编号重复")

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("合同数据格式错误")
            rows = [normalize(r) for r in raw]
            self.check_unique(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"合同数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        self.check_unique(self.rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.rows, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def add(self, row):
        item = normalize(row)
        if any(r["合同编号"] == item["合同编号"] for r in self.rows):
            raise ValueError("合同编号已存在")
        self.rows.append(item)
        try:
            self.save()
        except Exception:
            self.rows.pop()
            raise

    def update(self, old_id, row):
        item = normalize(row)
        if any(r["合同编号"] == item["合同编号"] and r["合同编号"] != old_id for r in self.rows):
            raise ValueError("合同编号已存在")
        index = next((i for i, r in enumerate(self.rows) if r["合同编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到合同")
        old = self.rows[index]
        self.rows[index] = item
        try:
            self.save()
        except Exception:
            self.rows[index] = old
            raise

    def delete(self, contract_id):
        old = self.rows[:]
        self.rows = [r for r in self.rows if r["合同编号"] != contract_id]
        try:
            self.save()
        except Exception:
            self.rows = old
            raise

    def import_csv(self, path):
        incoming = []
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
                raise ValueError("CSV 缺少必要字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, 2):
                try:
                    incoming.append(normalize(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self.check_unique(incoming)
        existing = {r["合同编号"] for r in self.rows}
        duplicates = existing.intersection(r["合同编号"] for r in incoming)
        if duplicates:
            raise ValueError("导入包含已有合同编号，整批未导入：" + "、".join(sorted(duplicates)))
        old = self.rows[:]
        self.rows.extend(incoming)
        try:
            self.save()
        except Exception:
            self.rows = old
            raise
        return len(incoming)

    def export_csv(self, path, rows=None):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows if rows is None else rows)

    def backup(self, path, workflow=None):
        payload = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION,
                   "created_at": datetime.now().isoformat(timespec="seconds"), "contracts": self.rows}
        if workflow is not None:
            payload["workflow"] = workflow.payload()
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, path, workflow=None):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取备份文件：{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("备份文件内容必须是对象")
        version = payload.get("version")
        if payload.get("format") != BACKUP_FORMAT or type(version) is not int or version not in (1, BACKUP_VERSION):
            raise ValueError("备份文件格式或版本不受支持")
        raw_rows = payload.get("contracts")
        if not isinstance(raw_rows, list):
            raise ValueError("备份文件缺少有效的合同记录列表")
        rows = []
        for index, raw in enumerate(raw_rows, 1):
            try:
                rows.append(normalize(raw))
            except ValueError as exc:
                raise ValueError(f"备份第 {index} 条合同记录无效：{exc}") from exc
        self.check_unique(rows)

        workflow_data = None
        if workflow is not None:
            if version == 1:
                workflow_data = {"format": "mainland-contract-workflow", "version": 1,
                                 "milestones": [], "audit": []}
            else:
                workflow_data = payload.get("workflow")
                if workflow_data is None:
                    raise ValueError("新版备份缺少履约节点和操作记录")
            milestones, audit = workflow.validate_payload(workflow_data)
            contract_ids = {item["合同编号"] for item in rows}
            if any(item["合同编号"] not in contract_ids for item in milestones):
                raise ValueError("备份包含关联不存在合同的履约节点")
        old_rows = self.rows[:]
        old_milestones = workflow.milestones[:] if workflow is not None else None
        old_audit = workflow.audit[:] if workflow is not None else None
        self.rows = rows
        if workflow is not None:
            workflow.milestones, workflow.audit = milestones, audit
        try:
            self.save()
            if workflow is not None:
                workflow.save()
        except Exception:
            self.rows = old_rows
            if workflow is not None:
                workflow.milestones, workflow.audit = old_milestones, old_audit
                try:
                    workflow.save()
                except Exception:
                    pass
            try:
                self.save()
            except Exception:
                pass
            raise


def data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "contracts.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("合同台账与到期提醒助手｜大陆版")
        root.geometry("1320x700")
        self.store = ContractStore(data_path())
        self.workflow = WorkflowStore(data_path().with_name("contract_workflow.json"))
        bar = ttk.Frame(root, padding=8); bar.pack(fill="x")
        for label, command in [("新增合同", self.add), ("编辑", self.edit), ("删除", self.delete),
                               ("履约节点", self.manage_milestones), ("风险检查", self.show_risks),
                               ("节点导入", self.import_milestones), ("节点导出", self.export_milestones),
                               ("操作记录", self.show_audit), ("批量识别合同文件", self.import_documents), ("导入 CSV", self.import_csv),
                               ("导出筛选结果", self.export_csv), ("备份", self.backup), ("恢复", self.restore)]:
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=3)
        self.search = tk.StringVar()
        ttk.Label(bar, text="搜索").pack(side="left", padx=(12, 3))
        entry = ttk.Entry(bar, textvariable=self.search, width=24); entry.pack(side="left")
        self.search.trace_add("write", lambda *_: self.refresh())
        self.only_due = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="只看需要提醒", variable=self.only_due, command=self.refresh).pack(side="left", padx=10)
        self.tree = ttk.Treeview(root, columns=FIELDS + ["提醒状态", "剩余天数"], show="headings")
        for col in FIELDS + ["提醒状态", "剩余天数"]:
            self.tree.heading(col, text=col); self.tree.column(col, width=105, stretch=True)
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, padding=8).pack(fill="x")
        self.refresh()

    def filtered(self):
        q = self.search.get().casefold()
        result = []
        for row in self.store.rows:
            state, left = reminder_state(row)
            if self.only_due.get() and state not in ("即将到期", "已逾期"):
                continue
            if q and q not in " ".join(row.values()).casefold():
                continue
            result.append((row, state, left))
        return result

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        items = self.filtered()
        for row, state, left in items:
            self.tree.insert("", "end", iid=row["合同编号"], values=[row[f] for f in FIELDS] + [state, left])
        due = sum(1 for row in self.store.rows if reminder_state(row)[0] in ("即将到期", "已逾期"))
        risks = risk_findings(self.store.rows, self.workflow.milestones)
        finance = finance_summary(self.workflow.milestones)
        self.summary.set(
            f"合同总数：{len(self.store.rows)}    合同到期提醒：{due}    高/中/低风险："
            f"{sum(x['等级']=='高' for x in risks)}/{sum(x['等级']=='中' for x in risks)}/{sum(x['等级']=='低' for x in risks)}"
            f"    待付款：{finance['待付款']}    待收款：{finance['待收款']}    数据位置：{self.store.path}"
        )

    def form(self, existing=None):
        win = tk.Toplevel(self.root); win.title("合同资料")
        defaults = dict(existing or {})
        defaults.setdefault("签订日期", date.today().isoformat())
        defaults.setdefault("生效日期", date.today().isoformat())
        defaults.setdefault("到期日期", date.today().isoformat())
        defaults.setdefault("续约提醒提前天数", "30")
        defaults.setdefault("合同金额", "0.00")
        defaults.setdefault("状态", "执行中")
        values = {f: tk.StringVar(value=defaults.get(f, "")) for f in FIELDS}
        for i, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=i, column=0, padx=8, pady=4, sticky="e")
            if field == "状态":
                ttk.Combobox(win, textvariable=values[field], values=STATUSES, state="readonly", width=34).grid(row=i, column=1, padx=8, pady=4)
            else:
                ttk.Entry(win, textvariable=values[field], width=38).grid(row=i, column=1, padx=8, pady=4)
        def save():
            try:
                item = {f: values[f].get() for f in FIELDS}
                if existing:
                    self.store.update(existing["合同编号"], item)
                    try: self.workflow.record_action(existing["合同编号"], "修改合同", f"合同资料更新为 {item['合同编号']}")
                    except OSError as exc: messagebox.showwarning("操作记录未保存", str(exc), parent=win)
                else:
                    self.store.add(item)
                    try: self.workflow.record_action(item["合同编号"], "新增合同", item["合同名称"])
                    except OSError as exc: messagebox.showwarning("操作记录未保存", str(exc), parent=win)
                self.refresh(); win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)
        ttk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, columnspan=2, pady=8)

    def selected(self):
        ids = self.tree.selection()
        return next((r for r in self.store.rows if ids and r["合同编号"] == ids[0]), None)

    def add(self): self.form()
    def edit(self):
        row = self.selected()
        if row: self.form(row)
    def delete(self):
        row = self.selected()
        if not row:
            return
        if any(item["合同编号"] == row["合同编号"] for item in self.workflow.milestones):
            messagebox.showwarning("不能删除", "该合同仍有关联履约节点，请先处理或删除节点后再删除合同。", parent=self.root)
            return
        if messagebox.askyesno("确认删除", f"删除合同 {row['合同编号']}？"):
            self.store.delete(row["合同编号"])
            try: self.workflow.record_action(row["合同编号"], "删除合同", row["合同名称"])
            except OSError as exc: messagebox.showwarning("操作记录未保存", str(exc), parent=self.root)
            self.refresh()
    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path); self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 份合同")
            except (ValueError, OSError) as exc: messagebox.showerror("导入失败", str(exc))
    def import_documents(self):
        paths = filedialog.askopenfilenames(
            title="批量识别合同文件",
            filetypes=[("支持的合同文件", "*.pdf *.docx *.txt *.md"),
                       ("PDF 文件", "*.pdf"), ("Word 文件", "*.docx"),
                       ("文本文件", "*.txt *.md")],
        )
        if not paths:
            return
        target = filedialog.asksaveasfilename(
            title="保存合同识别草稿",
            defaultextension=".csv",
            initialfile="合同识别草稿.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not target:
            return
        try:
            rows = write_draft_csv(paths, target)
            incomplete = sum(bool(row["待补齐字段"]) for row in rows)
            messagebox.showinfo(
                "识别草稿已生成",
                f"已处理 {len(rows)} 份合同文件，其中 {incomplete} 份仍有字段待补齐。\n"
                f"草稿位置：{target}\n\n"
                "请先用 Excel/WPS 打开 CSV，对照合同原文补齐并复核字段，再点击“导入 CSV”。"
                "软件不会自动把识别结果写入正式台账。",
                parent=self.root,
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("识别失败", str(exc), parent=self.root)

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path, [r for r, _, _ in self.filtered()])
                messagebox.showinfo("导出完成", "筛选结果已导出")
            except OSError as exc: messagebox.showerror("导出失败", str(exc))
    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try: self.store.backup(path, self.workflow); messagebox.showinfo("备份完成", "合同、履约节点和操作记录已备份")
            except OSError as exc: messagebox.showerror("备份失败", str(exc))
    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前合同台账，建议先备份。继续？"):
            try: self.store.restore(path, self.workflow); self.refresh(); messagebox.showinfo("恢复完成", "合同、履约节点和操作记录已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc: messagebox.showerror("恢复失败", str(exc))


    def manage_milestones(self):
        contract = self.selected()
        if not contract:
            messagebox.showinfo("履约节点", "请先在合同列表中选择一份合同。", parent=self.root)
            return
        contract_id = contract["合同编号"]
        win = tk.Toplevel(self.root)
        win.title(f"履约节点｜{contract_id}")
        win.geometry("980x520")
        columns = MILESTONE_FIELDS
        tree = ttk.Treeview(win, columns=columns, show="headings")
        widths = {"节点编号":110, "合同编号":100, "节点名称":170, "节点类型":85, "计划日期":100,
                  "金额":100, "状态":85, "完成日期":100, "备注":180}
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 100), stretch=True)
        tree.pack(fill="both", expand=True, padx=8, pady=8)

        def refresh_nodes():
            tree.delete(*tree.get_children())
            for item in self.workflow.milestones:
                if item["合同编号"] == contract_id:
                    tree.insert("", "end", iid=item["节点编号"], values=[item[f] for f in columns])

        def selected_node():
            ids = tree.selection()
            return next((item for item in self.workflow.milestones
                         if ids and item["节点编号"] == ids[0]), None)

        def form(existing=None):
            dialog = tk.Toplevel(win)
            dialog.title("编辑履约节点" if existing else "新增履约节点")
            dialog.transient(win)
            fields = ["节点名称", "节点类型", "计划日期", "金额", "状态", "完成日期", "备注"]
            defaults = dict(existing or {})
            defaults.setdefault("节点类型", "付款")
            defaults.setdefault("计划日期", date.today().isoformat())
            defaults.setdefault("金额", "0.00")
            defaults.setdefault("状态", "待处理")
            defaults.setdefault("完成日期", "")
            values = {field: tk.StringVar(value=defaults.get(field, "")) for field in fields}
            for index, field in enumerate(fields):
                ttk.Label(dialog, text=field).grid(row=index, column=0, padx=8, pady=5, sticky="e")
                if field == "节点类型":
                    widget = ttk.Combobox(dialog, textvariable=values[field], values=MILESTONE_TYPES,
                                          state="readonly", width=34)
                elif field == "状态":
                    widget = ttk.Combobox(dialog, textvariable=values[field], values=MILESTONE_STATUSES,
                                          state="readonly", width=34)
                else:
                    widget = ttk.Entry(dialog, textvariable=values[field], width=38)
                widget.grid(row=index, column=1, padx=8, pady=5, sticky="w")

            def save_node():
                try:
                    row = {field: values[field].get() for field in fields}
                    if row["状态"] == "已完成" and not row["完成日期"]:
                        row["完成日期"] = date.today().isoformat()
                    if row["状态"] != "已完成":
                        row["完成日期"] = ""
                    if existing:
                        self.workflow.update(existing["节点编号"], row)
                    else:
                        self.workflow.add(contract_id, row)
                    refresh_nodes()
                    self.refresh()
                    dialog.destroy()
                except (ValueError, OSError) as exc:
                    messagebox.showerror("保存失败", str(exc), parent=dialog)

            ttk.Button(dialog, text="保存", command=save_node).grid(row=len(fields), column=0,
                                                                    columnspan=2, pady=10)

        def complete_node():
            item = selected_node()
            if not item:
                return
            try:
                self.workflow.complete(item["节点编号"])
                refresh_nodes()
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("操作失败", str(exc), parent=win)

        def delete_node():
            item = selected_node()
            if item and messagebox.askyesno("确认删除", f"删除履约节点“{item['节点名称']}”？", parent=win):
                try:
                    self.workflow.delete(item["节点编号"])
                    refresh_nodes()
                    self.refresh()
                except (ValueError, OSError) as exc:
                    messagebox.showerror("删除失败", str(exc), parent=win)

        buttons = ttk.Frame(win, padding=6)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="新增节点", command=lambda: form()).pack(side="left", padx=4)
        ttk.Button(buttons, text="编辑节点", command=lambda: form(selected_node()) if selected_node() else None).pack(side="left", padx=4)
        ttk.Button(buttons, text="标记完成", command=complete_node).pack(side="left", padx=4)
        ttk.Button(buttons, text="删除节点", command=delete_node).pack(side="left", padx=4)
        refresh_nodes()

    def show_risks(self):
        findings = risk_findings(self.store.rows, self.workflow.milestones)
        win = tk.Toplevel(self.root)
        win.title("合同履约风险检查｜规则辅助结果")
        win.geometry("1080x560")
        columns = ["等级", "规则编号", "合同编号", "风险说明", "建议动作"]
        tree = ttk.Treeview(win, columns=columns, show="headings")
        for col, width in zip(columns, [65, 190, 120, 330, 330]):
            tree.heading(col, text=col)
            tree.column(col, width=width, stretch=True)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for index, item in enumerate(findings):
            tree.insert("", "end", iid=str(index), values=[item[col] for col in columns])
        high = sum(item["等级"] == "高" for item in findings)
        medium = sum(item["等级"] == "中" for item in findings)
        low = sum(item["等级"] == "低" for item in findings)
        ttk.Label(win, text=f"规则检查：{len(findings)} 项｜高风险 {high}｜中风险 {medium}｜低风险 {low}。"
                            "结果仅用于业务核对，不构成法律意见。", padding=8).pack(fill="x")

    def import_milestones(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.workflow.import_csv(path, {row["合同编号"] for row in self.store.rows})
                self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 个履约节点")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_milestones(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.workflow.export_csv(path)
                messagebox.showinfo("导出完成", "履约节点已导出")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def show_audit(self):
        win = tk.Toplevel(self.root)
        win.title("合同操作记录")
        win.geometry("900x500")
        columns = AUDIT_FIELDS
        tree = ttk.Treeview(win, columns=columns, show="headings")
        for col, width in zip(columns, [160, 130, 120, 110, 350]):
            tree.heading(col, text=col)
            tree.column(col, width=width, stretch=True)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for index, item in enumerate(reversed(self.workflow.audit[-500:])):
            tree.insert("", "end", iid=str(index), values=[item[field] for field in columns])


def self_test():
    sample = normalize({"合同编号":"C001","合同名称":"测试合同","签订日期":"2026-01-01","生效日期":"2026-01-01",
                        "到期日期":"2026-12-31","合同金额":"123.456","续约提醒提前天数":"30","状态":"执行中"})
    assert sample["合同金额"] == "123.46"
    assert reminder_state(sample, date(2026, 12, 1))[0] == "即将到期"
    assert reminder_state(sample, date(2027, 1, 1))[0] == "已逾期"
    print("SELF_TEST_OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test(); os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
