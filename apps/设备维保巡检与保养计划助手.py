"""Offline equipment maintenance planner for small shops and property teams."""
import csv
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "设备维保巡检与保养计划助手"
FIELDS = [
    "设备编号", "设备名称", "设备类别", "安装位置", "负责人", "启用日期",
    "保修到期日", "保养周期(天)", "最近保养日期", "下次保养日期", "设备状态", "备注",
]
LOG_FIELDS = [
    "记录编号", "设备编号", "维护日期", "维护类型", "维护内容", "服务商/人员",
    "停机时长(小时)", "费用(元)", "下次保养日期", "验收状态", "备注",
]
CATEGORIES = ["空调通风", "冷藏冷冻", "厨房设备", "办公设备", "水泵机电", "消防设施", "其他"]
DEFAULT_INTERVALS = {
    "空调通风": 90, "冷藏冷冻": 30, "厨房设备": 90, "办公设备": 180,
    "水泵机电": 90, "消防设施": 180, "其他": 90,
}
ASSET_STATUSES = ["正常", "待检修", "维修中", "停用"]
LOG_TYPES = ["例行保养", "故障维修", "巡检", "更换部件", "校准"]
ACCEPTANCE = ["已验收", "待验收", "不通过"]
BACKUP_FORMAT = "mainland-equipment-maintenance-backup"
BACKUP_VERSION = 1
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 50000


def _date(value, field, required=False):
    value = str(value or "").strip()
    if not value:
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式")
    return value


def _positive_days(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("保养周期必须为 1–3650 的整数天") from exc
    if str(number) != str(value).strip() or not 1 <= number <= 3650:
        raise ValueError("保养周期必须为 1–3650 的整数天")
    return str(number)


def _decimal(value, field):
    try:
        amount = Decimal(str(value if value is not None else "0").replace(",", "").replace("，", "").strip() or "0")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field}必须是有效数字") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field}不能为负数或非有限数")
    try:
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{field}超出可处理范围") from exc
    return format(amount, "f")


def normalize_asset(row):
    if not isinstance(row, dict):
        raise ValueError("设备记录格式错误")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    for field in ("设备编号", "设备名称", "设备类别", "安装位置", "启用日期"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if item["设备类别"] not in CATEGORIES:
        raise ValueError("设备类别不在内置分类中")
    item["启用日期"] = _date(item["启用日期"], "启用日期", required=True)
    item["保修到期日"] = _date(item["保修到期日"], "保修到期日")
    item["最近保养日期"] = _date(item["最近保养日期"], "最近保养日期")
    item["下次保养日期"] = _date(item["下次保养日期"], "下次保养日期")
    item["保养周期(天)"] = _positive_days(item["保养周期(天)"] or DEFAULT_INTERVALS[item["设备类别"]])
    start = date.fromisoformat(item["启用日期"])
    if item["保修到期日"] and date.fromisoformat(item["保修到期日"]) < start:
        raise ValueError("保修到期日不能早于启用日期")
    if item["最近保养日期"] and date.fromisoformat(item["最近保养日期"]) < start:
        raise ValueError("最近保养日期不能早于启用日期")
    if not item["下次保养日期"]:
        anchor = date.fromisoformat(item["最近保养日期"]) if item["最近保养日期"] else start
        item["下次保养日期"] = (anchor + timedelta(days=int(item["保养周期(天)"]))).isoformat()
    due = date.fromisoformat(item["下次保养日期"])
    if due < start:
        raise ValueError("下次保养日期不能早于启用日期")
    if item["最近保养日期"] and due <= date.fromisoformat(item["最近保养日期"]):
        raise ValueError("下次保养日期必须晚于最近保养日期")
    if item["设备状态"] not in ASSET_STATUSES:
        raise ValueError("设备状态不正确")
    return item


def normalize_log(row, assets):
    if not isinstance(row, dict):
        raise ValueError("维保记录格式错误")
    item = {field: str(row.get(field, "") or "").strip() for field in LOG_FIELDS}
    for field in ("记录编号", "设备编号", "维护日期", "维护类型", "维护内容"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if item["设备编号"] not in assets:
        raise ValueError("维保记录引用了不存在的设备")
    if item["维护类型"] not in LOG_TYPES:
        raise ValueError("维护类型不正确")
    if item["验收状态"] not in ACCEPTANCE:
        raise ValueError("验收状态不正确")
    item["维护日期"] = _date(item["维护日期"], "维护日期", required=True)
    asset = assets[item["设备编号"]]
    if date.fromisoformat(item["维护日期"]) < date.fromisoformat(asset["启用日期"]):
        raise ValueError("维护日期不能早于设备启用日期")
    item["停机时长(小时)"] = _decimal(item["停机时长(小时)"], "停机时长")
    item["费用(元)"] = _decimal(item["费用(元)"], "费用")
    item["下次保养日期"] = _date(item["下次保养日期"], "下次保养日期")
    if not item["下次保养日期"]:
        item["下次保养日期"] = (
            date.fromisoformat(item["维护日期"]) + timedelta(days=int(asset["保养周期(天)"]))
        ).isoformat()
    if date.fromisoformat(item["下次保养日期"]) <= date.fromisoformat(item["维护日期"]):
        raise ValueError("下次保养日期必须晚于维护日期")
    return item


def _safe_csv_value(value):
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe.startswith(("=", "+", "-", "@")) or (text and text[0] in "\t\r\n"):
        return "'" + text
    return text


def _restore_csv_value(value):
    text = str(value if value is not None else "")
    if text.startswith("'") and (text[1:].lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or (len(text) > 1 and text[1] in "\t\r\n")):
        return text[1:]
    return text


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _read_csv(path, fields):
    path = Path(path)
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV 文件超过 25 MiB 限制")
    incoming = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(fields) or len(set(headers)) != len(headers) or set(headers) != set(fields):
            raise ValueError("CSV 表头必须且只能包含全部规定字段：" + "、".join(fields))
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"第 {line} 行包含多余列")
            if all(not str(value or "").strip() for value in row.values()):
                continue
            if any(value is None for value in row.values()):
                raise ValueError(f"第 {line} 行字段数量不足")
            incoming.append({key: _restore_csv_value(value).strip() for key, value in row.items()})
            if len(incoming) > MAX_CSV_ROWS:
                raise ValueError("CSV 行数超过 50,000 条限制")
    return incoming


def _write_csv(path, fields, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _safe_csv_value(row.get(field, "")) for field in fields})
    atomic_write(path, "\ufeff" + output.getvalue())


class EquipmentStore:
    def __init__(self, path):
        self.path = Path(path)
        self.assets = []
        self.logs = []
        self.load()

    @staticmethod
    def _unique(rows, field, label):
        values = [row[field] for row in rows]
        if len(values) != len(set(values)):
            raise ValueError(f"{label}重复")

    def _validate(self, assets, logs):
        self._unique(assets, "设备编号", "设备编号")
        asset_map = {row["设备编号"]: row for row in assets}
        normalized_logs = [normalize_log(row, asset_map) for row in logs]
        self._unique(normalized_logs, "记录编号", "维保记录编号")
        return assets, normalized_logs

    def load(self):
        if not self.path.exists():
            self.assets, self.logs = [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
                raise ValueError("设备数据文件版本或格式不受支持")
            assets = [normalize_asset(row) for row in payload.get("assets", [])]
            logs = payload.get("logs", [])
            if not isinstance(logs, list):
                raise ValueError("维保记录列表格式错误")
            assets, logs = self._validate(assets, logs)
            self.assets, self.logs = assets, logs
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"设备数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        assets, logs = self._validate(self.assets, self.logs)
        payload = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION, "assets": assets, "logs": logs}
        atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def add_asset(self, row):
        item = normalize_asset(row)
        if any(old["设备编号"] == item["设备编号"] for old in self.assets):
            raise ValueError("设备编号已存在")
        previous = self.assets
        self.assets = previous + [item]
        try:
            self.save()
        except Exception:
            self.assets = previous
            raise
        return item["设备编号"]

    def update_asset(self, old_id, row):
        item = normalize_asset(row)
        if any(old["设备编号"] == item["设备编号"] and old["设备编号"] != old_id for old in self.assets):
            raise ValueError("设备编号已存在")
        index = next((i for i, old in enumerate(self.assets) if old["设备编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的设备")
        previous = self.assets[index]
        if item["设备编号"] != old_id and any(log["设备编号"] == old_id for log in self.logs):
            raise ValueError("已有维保历史的设备不允许修改编号")
        self.assets[index] = item
        try:
            self.save()
        except Exception:
            self.assets[index] = previous
            raise

    def delete_asset(self, asset_id):
        if any(log["设备编号"] == asset_id for log in self.logs):
            raise ValueError("该设备已有维保历史，不能删除；可将状态改为停用")
        previous = self.assets
        self.assets = [row for row in self.assets if row["设备编号"] != asset_id]
        try:
            self.save()
        except Exception:
            self.assets = previous
            raise

    def next_log_id(self, on_date=None):
        day = _date(on_date or date.today().isoformat(), "维护日期", required=True)
        prefix = "WB" + day.replace("-", "") + "-"
        numbers = []
        for row in self.logs:
            value = row["记录编号"]
            if value.startswith(prefix) and value[len(prefix):].isdigit():
                numbers.append(int(value[len(prefix):]))
        return f"{prefix}{max(numbers, default=0) + 1:04d}"

    def record_maintenance(self, row):
        asset_map = {item["设备编号"]: item for item in self.assets}
        item = normalize_log(row, asset_map)
        if any(old["记录编号"] == item["记录编号"] for old in self.logs):
            raise ValueError("维保记录编号已存在")
        index = next(i for i, asset in enumerate(self.assets) if asset["设备编号"] == item["设备编号"])
        old_asset = dict(self.assets[index])
        if old_asset["最近保养日期"] and item["维护日期"] < old_asset["最近保养日期"]:
            raise ValueError("维护日期不能早于最近一次维保日期")
        old_logs = self.logs
        self.logs = old_logs + [item]
        asset = dict(old_asset)
        asset["最近保养日期"] = item["维护日期"]
        asset["下次保养日期"] = item["下次保养日期"]
        if item["验收状态"] == "已验收" and asset["设备状态"] != "停用":
            asset["设备状态"] = "正常"
        elif item["验收状态"] == "不通过":
            asset["设备状态"] = "待检修"
        self.assets[index] = asset
        try:
            self.save()
        except Exception:
            self.logs = old_logs
            self.assets[index] = old_asset
            raise
        return item["记录编号"]

    def import_assets_csv(self, path):
        incoming = [normalize_asset(row) for row in _read_csv(path, FIELDS)]
        self._unique(incoming, "设备编号", "导入设备编号")
        existing = {row["设备编号"] for row in self.assets}
        duplicates = existing.intersection(row["设备编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在设备编号，未导入任何数据：" + "、".join(sorted(duplicates)))
        if incoming:
            previous = self.assets
            self.assets = previous + incoming
            try:
                self.save()
            except Exception:
                self.assets = previous
                raise
        return len(incoming)

    def export_assets_csv(self, path, rows=None):
        _write_csv(path, FIELDS, self.assets if rows is None else rows)

    def export_logs_csv(self, path, rows=None):
        _write_csv(path, LOG_FIELDS, self.logs if rows is None else rows)

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "assets": self.assets,
            "logs": self.logs,
        }
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        source_assets, source_logs = payload.get("assets"), payload.get("logs")
        if not isinstance(source_assets, list) or not isinstance(source_logs, list):
            raise ValueError("备份中的设备或维保记录列表格式错误")
        assets = [normalize_asset(row) for row in source_assets]
        assets, logs = self._validate(assets, source_logs)
        previous_assets, previous_logs = self.assets, self.logs
        self.assets, self.logs = assets, logs
        try:
            self.save()
        except Exception:
            self.assets, self.logs = previous_assets, previous_logs
            raise


def analyze_assets(assets, logs, today=None, lead_days=14):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(_date(today, "分析日期", required=True))
    by_asset = {}
    for log in logs:
        by_asset.setdefault(log["设备编号"], []).append(log)
    results = []
    for asset in assets:
        due = date.fromisoformat(asset["下次保养日期"])
        overdue_days = 0 if asset["设备状态"] == "停用" else max(0, (today - due).days)
        reasons = []
        level = "正常"
        if asset["设备状态"] in ("维修中", "待检修"):
            level = "高风险"
            reasons.append("设备状态为" + asset["设备状态"])
        elif asset["设备状态"] != "停用" and overdue_days > 0:
            level = "高风险"
            reasons.append(f"保养已逾期 {overdue_days} 天")
        elif asset["设备状态"] != "停用" and due <= today + timedelta(days=lead_days):
            level = "中风险"
            reasons.append(f"将在 {max(0, (due - today).days)} 天内到期")
        history = by_asset.get(asset["设备编号"], [])
        failed = [log for log in history if log["验收状态"] in ("待验收", "不通过")]
        if failed:
            level = "高风险"
            latest = max(failed, key=lambda row: (row["维护日期"], row["记录编号"]))
            reasons.append("存在未通过或待验收的维保记录：" + latest["记录编号"])
        warranty = asset["保修到期日"]
        if warranty and asset["设备状态"] != "停用":
            warranty_date = date.fromisoformat(warranty)
            if today <= warranty_date <= today + timedelta(days=30):
                if level == "正常":
                    level = "中风险"
                reasons.append("保修将在 30 天内到期")
            elif warranty_date < today:
                if level == "正常":
                    level = "中风险"
                reasons.append("设备保修已到期")
        results.append({
            **asset,
            "风险等级": level,
            "风险说明": "；".join(reasons) if reasons else "当前无到期或验收异常",
            "逾期天数": overdue_days,
            "维护记录数": len(history),
        })
    order = {"高风险": 0, "中风险": 1, "正常": 2}
    results.sort(key=lambda row: (order[row["风险等级"]], row["下次保养日期"], row["设备编号"]))
    return results


def maintenance_totals(logs):
    cost = sum((Decimal(row["费用(元)"]) for row in logs), Decimal("0.00"))
    downtime = sum((Decimal(row["停机时长(小时)"]) for row in logs), Decimal("0.00"))
    return {"count": len(logs), "cost": cost, "downtime": downtime}


def history_for_asset(logs, asset_id):
    rows = [row for row in logs if row["设备编号"] == asset_id]
    return sorted(rows, key=lambda row: (row["维护日期"], row["记录编号"]), reverse=True)


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "equipment_maintenance.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("设备维保巡检与保养计划助手｜大陆版")
        root.geometry("1540x800")
        self.store = EquipmentStore(default_data_path())

        toolbar = ttk.Frame(root, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        for label, command in [
            ("新增设备", self.add_asset), ("编辑设备", self.edit_asset), ("删除设备", self.delete_asset),
            ("登记维保", self.record_maintenance), ("查看维保历史", self.show_history), ("导入设备 CSV", self.import_csv),
            ("导出设备 CSV", self.export_csv), ("导出维保记录", self.export_logs),
            ("导出风险清单", self.export_risks), ("备份", self.backup), ("恢复备份", self.restore),
        ]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=2)

        filters = ttk.Frame(root, padding=(8, 4, 8, 8))
        filters.pack(fill="x")
        self.keyword = tk.StringVar()
        self.category = tk.StringVar(value="全部")
        self.status = tk.StringVar(value="全部")
        ttk.Label(filters, text="搜索").pack(side="left")
        ttk.Entry(filters, textvariable=self.keyword, width=24).pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="类别").pack(side="left")
        ttk.Combobox(filters, textvariable=self.category, values=["全部"] + CATEGORIES, state="readonly", width=14).pack(side="left", padx=(4, 12))
        ttk.Label(filters, text="状态").pack(side="left")
        ttk.Combobox(filters, textvariable=self.status, values=["全部"] + ASSET_STATUSES, state="readonly", width=12).pack(side="left", padx=(4, 12))
        ttk.Button(filters, text="清空筛选", command=self.clear_filters).pack(side="left")

        columns = ["设备编号", "设备名称", "设备类别", "安装位置", "负责人", "下次保养日期", "剩余天数", "设备状态", "风险等级", "风险说明", "保修到期日"]
        frame = ttk.Frame(root, padding=(8, 0, 8, 0))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        widths = [120, 150, 110, 150, 90, 115, 85, 85, 90, 260, 110]
        for field, width in zip(columns, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, minwidth=65, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, anchor="w", padding=10).pack(fill="x")
        for variable in (self.keyword, self.category, self.status):
            variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def selected_asset(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("请选择设备", "请先在列表中选择一台设备。", parent=self.root)
            return None
        asset_id = selection[0]
        return next((row for row in self.store.assets if row["设备编号"] == asset_id), None)

    def visible_assets(self):
        query = self.keyword.get().casefold().strip()
        rows = analyze_assets(self.store.assets, self.store.logs)
        return [
            row for row in rows
            if (self.category.get() == "全部" or row["设备类别"] == self.category.get())
            and (self.status.get() == "全部" or row["设备状态"] == self.status.get())
            and (not query or query in " ".join(str(row.get(field, "")) for field in FIELDS + ["风险等级", "风险说明"]).casefold())
        ]

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.visible_assets()
        today = date.today()
        for row in rows:
            remaining = (date.fromisoformat(row["下次保养日期"]) - today).days
            self.tree.insert("", "end", iid=row["设备编号"], values=[
                row["设备编号"], row["设备名称"], row["设备类别"], row["安装位置"], row["负责人"],
                row["下次保养日期"], remaining, row["设备状态"], row["风险等级"], row["风险说明"], row["保修到期日"],
            ])
        all_risks = analyze_assets(self.store.assets, self.store.logs)
        high = sum(row["风险等级"] == "高风险" for row in all_risks)
        medium = sum(row["风险等级"] == "中风险" for row in all_risks)
        totals = maintenance_totals(self.store.logs)
        self.summary.set(
            f"设备 {len(self.store.assets)} 台｜高风险 {high} 台｜中风险 {medium} 台｜"
            f"维保记录 {totals['count']} 条｜累计费用 ¥{totals['cost']:.2f}｜"
            f"累计停机 {totals['downtime']:.2f} 小时｜数据位置：{self.store.path}"
        )

    def clear_filters(self):
        self.keyword.set("")
        self.category.set("全部")
        self.status.set("全部")

    def asset_form(self, existing=None):
        old_id = existing["设备编号"] if existing else ""
        initial = dict(existing or {})
        initial.setdefault("设备编号", "EQ" + date.today().strftime("%Y%m%d") + f"-{len(self.store.assets)+1:04d}")
        initial.setdefault("设备名称", "")
        initial.setdefault("设备类别", "其他")
        initial.setdefault("安装位置", "")
        initial.setdefault("负责人", "")
        initial.setdefault("启用日期", date.today().isoformat())
        initial.setdefault("保修到期日", "")
        initial.setdefault("保养周期(天)", str(DEFAULT_INTERVALS[initial["设备类别"]]))
        initial.setdefault("最近保养日期", "")
        initial.setdefault("下次保养日期", "")
        initial.setdefault("设备状态", "正常")
        initial.setdefault("备注", "")
        win = tk.Toplevel(self.root)
        win.title("设备资料")
        win.transient(self.root)
        win.grab_set()
        variables = {field: tk.StringVar(value=str(initial[field])) for field in FIELDS}
        for index, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=10, pady=5, sticky="e")
            if field == "设备编号" and existing:
                widget = ttk.Entry(win, textvariable=variables[field], width=42, state="readonly")
            elif field == "设备类别":
                widget = ttk.Combobox(win, textvariable=variables[field], values=CATEGORIES, state="readonly", width=39)
                variables[field].trace_add("write", lambda *_: variables["保养周期(天)"].set(str(DEFAULT_INTERVALS.get(variables["设备类别"].get(), 90))) if not existing else None)
            elif field == "设备状态":
                widget = ttk.Combobox(win, textvariable=variables[field], values=ASSET_STATUSES, state="readonly", width=39)
            else:
                widget = ttk.Entry(win, textvariable=variables[field], width=42)
            widget.grid(row=index, column=1, padx=10, pady=5, sticky="w")
        ttk.Label(win, text="日期格式 YYYY-MM-DD；保养周期为 1–3650 天；类别周期仅为可调整的内部提醒默认值。").grid(
            row=len(FIELDS), column=0, columnspan=2, padx=10, pady=6)

        def save():
            row = {field: variables[field].get() for field in FIELDS}
            try:
                if existing:
                    self.store.update_asset(old_id, row)
                else:
                    self.store.add_asset(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(win, text="保存", command=save).grid(row=len(FIELDS)+1, column=0, columnspan=2, pady=10)

    def add_asset(self):
        self.asset_form()

    def edit_asset(self):
        row = self.selected_asset()
        if row:
            self.asset_form(row)

    def delete_asset(self):
        row = self.selected_asset()
        if not row:
            return
        if not messagebox.askyesno("确认删除", f"确定删除设备 {row['设备编号']}？有维保历史的设备不可删除。", parent=self.root):
            return
        try:
            self.store.delete_asset(row["设备编号"])
            self.refresh()
        except (ValueError, OSError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def record_maintenance(self):
        asset = self.selected_asset()
        if not asset:
            return
        win = tk.Toplevel(self.root)
        win.title("登记维保记录")
        win.transient(self.root)
        win.grab_set()
        initial = {
            "维护日期": date.today().isoformat(), "维护类型": "例行保养", "维护内容": "",
            "服务商/人员": "", "停机时长(小时)": "0", "费用(元)": "0",
            "验收状态": "已验收", "备注": "",
        }
        variables = {key: tk.StringVar(value=value) for key, value in initial.items()}
        labels = ["维护日期", "维护类型", "维护内容", "服务商/人员", "停机时长(小时)", "费用(元)", "验收状态", "备注"]
        for index, field in enumerate(labels):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=10, pady=5, sticky="e")
            if field in ("维护类型", "验收状态"):
                values = LOG_TYPES if field == "维护类型" else ACCEPTANCE
                widget = ttk.Combobox(win, textvariable=variables[field], values=values, state="readonly", width=39)
            else:
                widget = ttk.Entry(win, textvariable=variables[field], width=42)
            widget.grid(row=index, column=1, padx=10, pady=5, sticky="w")
        ttk.Label(win, text=f"设备：{asset['设备编号']}｜{asset['设备名称']}；下次保养日期按周期自动计算。").grid(
            row=len(labels), column=0, columnspan=2, padx=10, pady=6)

        def save():
            service_date = variables["维护日期"].get().strip()
            try:
                due = (date.fromisoformat(_date(service_date, "维护日期", required=True)) +
                       timedelta(days=int(asset["保养周期(天)"]))).isoformat()
                row = {
                    "记录编号": self.store.next_log_id(service_date),
                    "设备编号": asset["设备编号"],
                    "维护日期": service_date,
                    "维护类型": variables["维护类型"].get(),
                    "维护内容": variables["维护内容"].get(),
                    "服务商/人员": variables["服务商/人员"].get(),
                    "停机时长(小时)": variables["停机时长(小时)"].get(),
                    "费用(元)": variables["费用(元)"].get(),
                    "下次保养日期": due,
                    "验收状态": variables["验收状态"].get(),
                    "备注": variables["备注"].get(),
                }
                self.store.record_maintenance(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(win, text="保存维保记录", command=save).grid(row=len(labels)+1, column=0, columnspan=2, pady=10)

    def show_history(self):
        asset = self.selected_asset()
        if not asset:
            return
        rows = history_for_asset(self.store.logs, asset["设备编号"])
        win = tk.Toplevel(self.root)
        win.title(f"维保历史｜{asset['设备编号']} {asset['设备名称']}")
        win.geometry("1180x520")
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=LOG_FIELDS, show="headings")
        widths = [155, 110, 100, 100, 220, 120, 110, 100, 110, 90, 160]
        for field, width in zip(LOG_FIELDS, widths):
            tree.heading(field, text=field)
            tree.column(field, width=width, minwidth=70, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for row in rows:
            tree.insert("", "end", values=[row[field] for field in LOG_FIELDS])
        totals = maintenance_totals(rows)
        ttk.Label(
            win,
            text=f"共 {totals['count']} 条记录｜累计费用 ¥{totals['cost']:.2f}｜累计停机 {totals['downtime']:.2f} 小时",
            anchor="w",
            padding=8,
        ).pack(fill="x")

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_assets_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功追加 {count} 台设备。", parent=self.root)
        except (ValueError, OSError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_assets_csv(path, self.visible_assets())
                messagebox.showinfo("导出完成", f"已导出 {len(self.visible_assets())} 台设备。", parent=self.root)
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.root)

    def export_logs(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_logs_csv(path)
                messagebox.showinfo("导出完成", f"已导出 {len(self.store.logs)} 条维保记录。", parent=self.root)
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.root)

    def export_risks(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            fields = FIELDS + ["风险等级", "风险说明", "逾期天数", "维护记录数"]
            try:
                _write_csv(path, fields, analyze_assets(self.store.assets, self.store.logs))
                messagebox.showinfo("导出完成", "风险清单已导出。", parent=self.root)
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.root)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "设备台账和完整维保历史已备份。", parent=self.root)
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc), parent=self.root)

    def restore(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("JSON 备份", "*.json")])
        if not path or not messagebox.askyesno("确认恢复", "恢复将替换当前设备台账和维保历史，是否继续？", parent=self.root):
            return
        try:
            self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", "备份数据已恢复。", parent=self.root)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("恢复失败", str(exc), parent=self.root)


def self_test():
    assert len(CATEGORIES) == len(DEFAULT_INTERVALS)
    assert set(CATEGORIES) == set(DEFAULT_INTERVALS)
    assert _positive_days("30") == "30"
    assert _decimal("12.345", "费用") == "12.35"
    with tempfile.TemporaryDirectory() as folder:
        store = EquipmentStore(Path(folder) / "equipment.json")
        row = {
            "设备编号": "EQ-001", "设备名称": "冷藏柜", "设备类别": "冷藏冷冻",
            "安装位置": "后厨", "负责人": "张三", "启用日期": "2026-01-01",
            "保修到期日": "2027-01-01", "保养周期(天)": "30", "最近保养日期": "",
            "下次保养日期": "", "设备状态": "正常", "备注": "",
        }
        store.add_asset(row)
        log = {
            "记录编号": store.next_log_id("2026-02-01"), "设备编号": "EQ-001",
            "维护日期": "2026-02-01", "维护类型": "例行保养", "维护内容": "清洁冷凝器",
            "服务商/人员": "内部", "停机时长(小时)": "0.5", "费用(元)": "80",
            "下次保养日期": "2026-03-03", "验收状态": "已验收", "备注": "",
        }
        store.record_maintenance(log)
        assert store.assets[0]["最近保养日期"] == "2026-02-01"
        assert len(store.logs) == 1
        restored = EquipmentStore(Path(folder) / "restored.json")
        store.backup(Path(folder) / "backup.json")
        restored.restore(Path(folder) / "backup.json")
        assert len(restored.assets) == len(restored.logs) == 1
        risks = analyze_assets(restored.assets, restored.logs, today="2026-02-02")
        assert risks[0]["风险等级"] == "正常"
        assert maintenance_totals(restored.logs)["cost"] == Decimal("80.00")
    if sys.stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.getenv("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
