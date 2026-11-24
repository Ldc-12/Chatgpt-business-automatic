"""Offline business licence and compliance deadline reminder for Mainland Windows users."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "经营证照与年报提醒助手"
FIELDS = [
    "事项编号", "事项名称", "事项类型", "登记/开始日期", "截止日期",
    "提醒提前天数", "状态", "责任人", "来源/主管部门", "联系方式", "备注",
]
CATEGORIES = ["经营证照", "年度报告", "税务申报", "消防/安全检查", "设备检验", "员工健康证", "其他"]
STATUSES = ["待办理", "办理中", "已完成", "已注销"]
BACKUP_FORMAT = "mainland-business-compliance-reminder"
BACKUP_VERSION = 1


def parse_date(value: str, field: str, *, required: bool = True) -> str:
    value = str(value or "").strip()
    if not value and not required:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式")
    return value


def normalize_item(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("事项记录必须是对象")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    for field in ("事项编号", "事项名称", "事项类型", "截止日期", "状态"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if item["事项类型"] not in CATEGORIES:
        raise ValueError("事项类型无效")
    if item["状态"] not in STATUSES:
        raise ValueError("事项状态无效")
    item["登记/开始日期"] = parse_date(item["登记/开始日期"], "登记/开始日期", required=False)
    item["截止日期"] = parse_date(item["截止日期"], "截止日期")
    if item["登记/开始日期"] and item["登记/开始日期"] > item["截止日期"]:
        raise ValueError("登记/开始日期不能晚于截止日期")
    try:
        days = int(item["提醒提前天数"] or "30")
    except (TypeError, ValueError) as exc:
        raise ValueError("提醒提前天数必须为整数") from exc
    if days < 0 or days > 3650:
        raise ValueError("提醒提前天数必须在 0 到 3650 之间")
    item["提醒提前天数"] = str(days)
    return item


def reminder_state(item: dict, today: date | None = None) -> tuple[str, int]:
    today = today or date.today()
    days_left = (date.fromisoformat(item["截止日期"]) - today).days
    if item["状态"] in ("已完成", "已注销"):
        return "无需提醒", days_left
    if days_left < 0:
        return "已逾期", days_left
    if days_left <= int(item["提醒提前天数"]):
        return "即将到期", days_left
    return "正常", days_left


def spreadsheet_safe_cell(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _atomic_write(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ComplianceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.rows: list[dict] = []
        self.load()

    @staticmethod
    def check_unique(rows: list[dict]) -> None:
        ids = [row["事项编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("事项编号重复")

    def load(self) -> None:
        if not self.path.exists():
            self.rows = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("事项数据格式错误")
            rows = [normalize_item(item) for item in raw]
            self.check_unique(rows)
            self.rows = rows
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"事项数据无法读取，原文件未修改：{exc}") from exc

    def save(self) -> None:
        self.check_unique(self.rows)
        _atomic_write(self.path, json.dumps(self.rows, ensure_ascii=False, indent=2) + "\n")

    def add(self, row: dict) -> None:
        item = normalize_item(row)
        if any(old["事项编号"] == item["事项编号"] for old in self.rows):
            raise ValueError("事项编号已存在")
        previous = self.rows
        self.rows = previous + [item]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise

    def update(self, old_id: str, row: dict) -> None:
        item = normalize_item(row)
        if any(old["事项编号"] == item["事项编号"] and old["事项编号"] != old_id for old in self.rows):
            raise ValueError("事项编号已存在")
        index = next((i for i, old in enumerate(self.rows) if old["事项编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的事项")
        previous = self.rows[index]
        self.rows[index] = item
        try:
            self.save()
        except Exception:
            self.rows[index] = previous
            raise

    def delete(self, item_id: str) -> None:
        previous = self.rows
        self.rows = [row for row in self.rows if row["事项编号"] != item_id]
        if len(previous) == len(self.rows):
            raise ValueError("找不到要删除的事项")
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise

    def import_csv(self, path: str | Path) -> int:
        incoming = []
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(FIELDS) or set(headers) != set(FIELDS):
                raise ValueError("CSV 必须且只能包含全部规定字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, 2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余列")
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_item(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self.check_unique(incoming)
        existing = {row["事项编号"] for row in self.rows}
        duplicates = existing.intersection(row["事项编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已有事项编号，整批未导入：" + "、".join(sorted(duplicates)))
        previous = self.rows
        self.rows = previous + incoming
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise
        return len(incoming)

    def export_csv(self, path: str | Path, rows: list[dict] | None = None) -> None:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for row in self.rows if rows is None else rows:
            writer.writerow({field: spreadsheet_safe_cell(row.get(field, "")) for field in FIELDS})
        _atomic_write(path, "\ufeff" + output.getvalue())

    def backup(self, path: str | Path) -> None:
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "items": self.rows,
        }
        document = {"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
        _atomic_write(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")

    def restore(self, path: str | Path) -> None:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取备份文件：{exc}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("payload"), dict):
            raise ValueError("备份文件格式错误")
        payload = document["payload"]
        if payload.get("format") != BACKUP_FORMAT or type(payload.get("version")) is not int or payload["version"] != BACKUP_VERSION:
            raise ValueError("备份文件格式或版本不受支持")
        expected = hashlib.sha256(_canonical(payload)).hexdigest()
        if not isinstance(document.get("sha256"), str) or document["sha256"] != expected:
            raise ValueError("备份 SHA256 校验失败，当前数据未修改")
        raw_rows = payload.get("items")
        if not isinstance(raw_rows, list):
            raise ValueError("备份文件缺少有效事项列表")
        rows = [normalize_item(item) for item in raw_rows]
        self.check_unique(rows)
        previous = self.rows
        self.rows = rows
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise


def default_data_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "business_compliance.json"


def filter_items(rows: list[dict], keyword: str = "", status: str = "全部", due_only: bool = False,
                 today: date | None = None) -> list[dict]:
    query = str(keyword or "").casefold().strip()
    result = []
    for row in rows:
        state, _ = reminder_state(row, today)
        if due_only and state not in ("即将到期", "已逾期"):
            continue
        if status != "全部" and row["状态"] != status:
            continue
        if query and query not in " ".join(row[field] for field in FIELDS).casefold():
            continue
        result.append(row)
    return sorted(result, key=lambda item: (item["截止日期"], item["事项编号"]))


def summarize_items(rows: list[dict], today: date | None = None) -> dict:
    states = {status: sum(1 for row in rows if row["状态"] == status) for status in STATUSES}
    reminders = {label: sum(1 for row in rows if reminder_state(row, today)[0] == label)
                 for label in ("已逾期", "即将到期", "正常", "无需提醒")}
    return {"count": len(rows), "states": states, "reminders": reminders}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("经营证照与年报提醒助手｜大陆版")
        root.geometry("1320x700")
        self.store = ComplianceStore(default_data_path())
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        for label, command in [
            ("新增事项", self.add), ("编辑", self.edit), ("删除", self.delete),
            ("导入 CSV", self.import_csv), ("导出筛选结果", self.export_csv),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)
        filters = ttk.Frame(root, padding=(8, 0, 8, 8))
        filters.pack(fill="x")
        self.query = tk.StringVar()
        self.status = tk.StringVar(value="全部")
        self.due_only = tk.BooleanVar(value=False)
        ttk.Label(filters, text="搜索").pack(side="left")
        ttk.Entry(filters, textvariable=self.query, width=28).pack(side="left", padx=4)
        ttk.Label(filters, text="办理状态").pack(side="left", padx=(12, 2))
        ttk.Combobox(filters, textvariable=self.status, values=["全部"] + STATUSES,
                     state="readonly", width=10).pack(side="left")
        ttk.Checkbutton(filters, text="只看临期/逾期", variable=self.due_only,
                        command=self.refresh).pack(side="left", padx=12)
        self.query.trace_add("write", lambda *_: self.refresh())
        self.status.trace_add("write", lambda *_: self.refresh())
        self.tree = ttk.Treeview(root, columns=FIELDS + ["提醒状态", "剩余天数"], show="headings", height=20)
        widths = [110, 150, 115, 105, 105, 90, 85, 90, 130, 115, 180, 90, 75]
        for field, width in zip(FIELDS + ["提醒状态", "剩余天数"], widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.visible_rows = []
        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, anchor="w", padding=8).pack(fill="x")
        self.refresh()

    def refresh(self):
        rows = filter_items(self.store.rows, self.query.get(), self.status.get(), self.due_only.get())
        self.visible_rows = rows
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(rows):
            state, left = reminder_state(row)
            self.tree.insert("", "end", iid=str(index), values=[row[field] for field in FIELDS] + [state, left])
        summary = summarize_items(self.store.rows)
        self.summary.set(
            f"事项：{summary['count']}    已逾期：{summary['reminders']['已逾期']}    "
            f"即将到期：{summary['reminders']['即将到期']}    正常：{summary['reminders']['正常']}    "
            f"已完成：{summary['states']['已完成']}    数据位置：{self.store.path}"
        )

    def selected_row(self):
        selected = self.tree.selection()
        return self.visible_rows[int(selected[0])] if selected else None

    def form(self, existing=None):
        win = tk.Toplevel(self.root)
        win.title("经营事项资料")
        values = {field: tk.StringVar(value=str((existing or {}).get(field, ""))) for field in FIELDS}
        if not existing:
            values["事项编号"].set("BC-" + date.today().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper())
            values["事项类型"].set("经营证照")
            values["登记/开始日期"].set(date.today().isoformat())
            values["提醒提前天数"].set("30")
            values["状态"].set("待办理")
        for index, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            if field == "事项类型":
                ttk.Combobox(win, textvariable=values[field], values=CATEGORIES,
                             state="readonly", width=36).grid(row=index, column=1, padx=8, pady=4)
            elif field == "状态":
                ttk.Combobox(win, textvariable=values[field], values=STATUSES,
                             state="readonly", width=36).grid(row=index, column=1, padx=8, pady=4)
            else:
                ttk.Entry(win, textvariable=values[field], width=39).grid(row=index, column=1, padx=8, pady=4)

        def save():
            try:
                item = {field: values[field].get() for field in FIELDS}
                if existing:
                    self.store.update(existing["事项编号"], item)
                else:
                    self.store.add(item)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, columnspan=2, pady=8)

    def add(self):
        self.form()

    def edit(self):
        row = self.selected_row()
        if row:
            self.form(row)

    def delete(self):
        row = self.selected_row()
        if row and messagebox.askyesno("确认删除", f"删除事项“{row['事项名称']}”？"):
            try:
                self.store.delete(row["事项编号"])
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功追加 {count} 条事项")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path, self.visible_rows)
                messagebox.showinfo("导出完成", "当前筛选结果已导出为 CSV")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "已生成带 SHA256 校验的备份")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前全部事项，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "事项数据已恢复")
            except (ValueError, OSError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    sample = normalize_item({
        "事项编号": "BC-SELFTEST", "事项名称": "测试经营证照", "事项类型": "经营证照",
        "登记/开始日期": "2026-01-01", "截止日期": "2026-12-31",
        "提醒提前天数": "30", "状态": "待办理",
    })
    assert reminder_state(sample, date(2026, 12, 1)) == ("即将到期", 30)
    assert PRODUCT == "经营证照与年报提醒助手"
    print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
