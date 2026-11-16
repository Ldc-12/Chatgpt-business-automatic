"""Offline vehicle maintenance and expense ledger for mainland Windows users."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "车辆维保与费用台账助手"
FORMAT = "mainland-vehicle-ledger"
VERSION = 1
FIELDS = ["记录编号", "车牌号码", "车辆名称", "日期", "里程公里", "费用类别", "项目/事项", "服务商", "金额元", "下次提醒日期", "备注"]
MAX_ROWS = 50000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
CATEGORIES = {"保养", "维修", "保险", "年检", "轮胎", "燃油/充电", "停车/通行", "其他"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def atomic_write(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("车辆记录必须是对象")
    record_id = str(row.get("记录编号", "")).strip() or uuid.uuid4().hex.upper()
    plate = str(row.get("车牌号码", "")).strip().upper()
    name = str(row.get("车辆名称", "")).strip()
    if not plate or len(plate) > 16 or any(ord(c) < 32 for c in plate):
        raise ValueError("车牌号码不能为空且长度不能超过 16")
    if not name:
        raise ValueError("车辆名称不能为空")
    try:
        day = date.fromisoformat(str(row.get("日期", "")).strip()).isoformat()
    except (TypeError, ValueError):
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from None
    category = str(row.get("费用类别", "")).strip()
    if category not in CATEGORIES:
        raise ValueError("费用类别不在允许范围内")
    item = str(row.get("项目/事项", "")).strip()
    if not item:
        raise ValueError("项目/事项不能为空")
    try:
        mileage = float(row.get("里程公里", 0))
        amount = float(row.get("金额元", 0))
    except (TypeError, ValueError):
        raise ValueError("里程和金额必须是数字") from None
    if not math.isfinite(mileage) or mileage < 0:
        raise ValueError("里程必须是非负有限数字")
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("金额必须是非负有限数字")
    reminder = str(row.get("下次提醒日期", "") or "").strip()
    if reminder:
        try:
            reminder = date.fromisoformat(reminder).isoformat()
        except ValueError:
            raise ValueError("下次提醒日期必须使用 YYYY-MM-DD 格式") from None
    return {
        "记录编号": record_id, "车牌号码": plate, "车辆名称": name, "日期": day,
        "里程公里": mileage, "费用类别": category, "项目/事项": item,
        "服务商": str(row.get("服务商", "") or "").strip(), "金额元": amount,
        "下次提醒日期": reminder, "备注": str(row.get("备注", "") or "").strip(),
    }


class VehicleStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def _payload(rows):
        body = {"格式": FORMAT, "版本": VERSION, "记录": rows}
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("车辆台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("车辆台账 SHA256 校验失败")
        raw = body.get("记录")
        if not isinstance(raw, list) or len(raw) > MAX_ROWS:
            raise ValueError("车辆记录缺失或超过 50000 条安全上限")
        rows = [normalize(item) for item in raw]
        ids = [item["记录编号"] for item in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("车辆记录编号重复")
        return rows

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("本地车辆台账超过 100 MiB，已拒绝加载且原文件未修改")
        try:
            self.rows = self.decode(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"车辆台账无法读取，原文件未修改：{exc}") from exc

    def _commit(self, rows):
        normalized = [normalize(item) for item in rows]
        if len(normalized) > MAX_ROWS:
            raise ValueError("车辆记录超过 50000 条安全上限")
        ids = [item["记录编号"] for item in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("车辆记录编号重复")
        data = json.dumps(self._payload(normalized), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("车辆台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.rows = normalized

    def add(self, row):
        normalized = normalize(row)
        if any(item["记录编号"] == normalized["记录编号"] for item in self.rows):
            raise ValueError("记录编号已存在")
        self._commit(self.rows + [normalized])
        return normalized["记录编号"]

    def export_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({key: csv_safe(row.get(key, "")) for key in FIELDS})
        atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

    def import_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("CSV 超过 25 MiB 安全上限")
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise ValueError("CSV 表头与本软件模板不一致")
            incoming = []
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"CSV 第 {line} 行列数不正确")
                incoming.append(normalize(row))
                if len(incoming) > MAX_ROWS:
                    raise ValueError("CSV 超过 50000 条记录上限")
        ids = [item["记录编号"] for item in incoming]
        if len(ids) != len(set(ids)):
            raise ValueError("CSV 内记录编号重复，未导入任何数据")
        existing = {item["记录编号"] for item in self.rows}
        if existing.intersection(ids):
            raise ValueError("CSV 包含已存在的记录编号，未导入任何数据")
        if len(self.rows) + len(incoming) > MAX_ROWS:
            raise ValueError("导入后车辆记录超过 50000 条安全上限")
        self._commit(self.rows + incoming)
        return len(incoming)

    def backup(self, path):
        data = json.dumps(self._payload(self.rows), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        self._commit(self.decode(payload))

    def due_reminders(self, on=None):
        today = on or date.today()
        return [row for row in self.rows if row["下次提醒日期"] and date.fromisoformat(row["下次提醒日期"]) <= today]


def default_data_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "MainlandBusinessTools" / "vehicle_maintenance_ledger.json"


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        store = VehicleStore(Path(folder) / "data.json")
        store.add({"车牌号码": "粤A12345", "车辆名称": "测试车辆", "日期": "2026-01-01",
                   "里程公里": 10000, "费用类别": "保养", "项目/事项": "机油保养",
                   "金额元": 300, "下次提醒日期": "2026-07-01"})
        assert len(store.rows) == 1
        assert len(store.due_reminders(date.fromisoformat("2026-08-01"))) == 1
    print("SELF_TEST_OK")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        require_license(PRODUCT)
        self.store = VehicleStore(default_data_path())
        self.title(PRODUCT)
        self.geometry("1180x700")
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        for label, command in (("新增记录", self.add_record), ("导入 CSV", self.import_csv),
                               ("导出 CSV", self.export_csv), ("备份", self.backup), ("恢复", self.restore)):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=4)
        self.tree = ttk.Treeview(self, columns=FIELDS[1:], show="headings")
        for field in FIELDS[1:]:
            self.tree.heading(field, text=field)
            self.tree.column(field, width=105, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.refresh()
        due = self.store.due_reminders()
        if due:
            messagebox.showinfo("保养提醒", f"有 {len(due)} 条车辆维保/年检提醒到期或逾期，请核对。")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.store.rows:
            self.tree.insert("", "end", values=[row.get(field, "") for field in FIELDS[1:]])

    def add_record(self):
        values = {}
        prompts = [("车牌号码", "粤A12345"), ("车辆名称", "家用轿车"), ("日期", date.today().isoformat()),
                   ("里程公里", "0"), ("费用类别", "保养"), ("项目/事项", "常规保养"),
                   ("服务商", ""), ("金额元", "0"), ("下次提醒日期", ""), ("备注", "")]
        for field, default in prompts:
            value = tk.simpledialog.askstring("新增车辆记录", field, initialvalue=default, parent=self)
            if value is None:
                return
            values[field] = value
        try:
            self.store.add(values)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path: return
        try:
            count = self.store.import_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 条记录")
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try: self.store.export_csv(path)
            except OSError as exc: messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try: self.store.backup(path)
            except (OSError, ValueError) as exc: messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复将替换当前车辆台账，建议先备份。是否继续？"):
            try:
                self.store.restore(path)
                self.refresh()
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    App().mainloop()
