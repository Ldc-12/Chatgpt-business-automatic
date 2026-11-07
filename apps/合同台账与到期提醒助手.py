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

PRODUCT = "合同台账与到期提醒助手"
FIELDS = ["合同编号", "合同名称", "甲方/客户", "乙方/供应商", "签订日期", "生效日期", "到期日期",
          "合同金额", "续约提醒提前天数", "状态", "负责人", "联系方式", "备注"]
STATUSES = ["执行中", "待续约", "已续约", "已到期", "已终止"]
BACKUP_FORMAT = "mainland-contract-ledger"
BACKUP_VERSION = 1


def money(value):
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

    def backup(self, path):
        payload = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION,
                   "created_at": datetime.now().isoformat(timespec="seconds"), "contracts": self.rows}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取备份文件：{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("备份文件内容必须是对象")
        if payload.get("format") != BACKUP_FORMAT or type(payload.get("version")) is not int or payload.get("version") != BACKUP_VERSION:
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
        old = self.rows[:]
        self.rows = rows
        try:
            self.save()
        except Exception:
            self.rows = old
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
        bar = ttk.Frame(root, padding=8); bar.pack(fill="x")
        for label, command in [("新增合同", self.add), ("编辑", self.edit), ("删除", self.delete),
                               ("导入 CSV", self.import_csv), ("导出筛选结果", self.export_csv),
                               ("备份", self.backup), ("恢复", self.restore)]:
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
        self.summary.set(f"合同总数：{len(self.store.rows)}    需要提醒：{due}    数据位置：{self.store.path}")

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
                if existing: self.store.update(existing["合同编号"], item)
                else: self.store.add(item)
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
        if row and messagebox.askyesno("确认删除", f"删除合同 {row['合同编号']}？"):
            self.store.delete(row["合同编号"]); self.refresh()
    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path); self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 份合同")
            except (ValueError, OSError) as exc: messagebox.showerror("导入失败", str(exc))
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
            try: self.store.backup(path); messagebox.showinfo("备份完成", "备份文件已保存")
            except OSError as exc: messagebox.showerror("备份失败", str(exc))
    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前合同台账，建议先备份。继续？"):
            try: self.store.restore(path); self.refresh(); messagebox.showinfo("恢复完成", "合同台账已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc: messagebox.showerror("恢复失败", str(exc))


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
