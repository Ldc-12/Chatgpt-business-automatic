"""Offline food-batch expiry and traceability assistant for small shops."""

import csv
import json
import os
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "食品批次与保质期追踪助手"
FIELDS = [
    "批次编号", "商品编码", "商品名称", "供应商", "生产日期", "到期日期",
    "入库日期", "当前数量", "单位", "成本单价", "库位", "备注",
]
MOVEMENT_FIELDS = [
    "流水编号", "批次编号", "商品编码", "商品名称", "类型", "变动方向",
    "变动数量", "发生时间", "去向", "原因",
]
BACKUP_FORMAT = "mainland-food-batch-backup"
BACKUP_VERSION = 1
MOVEMENT_TYPES = {"入库", "出库", "调整", "作废"}


def decimal_value(value, field, *, allow_zero=True):
    text = str(value if value is not None else "").replace(",", "").replace("，", "").strip()
    try:
        number = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效数字") from None
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{field}必须是{'大于 0' if not allow_zero else '大于或等于 0'}的有限数字")
    return number


def decimal_text(value):
    return format(value.normalize(), "f") if value else "0"


def parse_date(value, field, *, required=True):
    text = str(value or "").strip()
    if not text and not required:
        return None
    if not text:
        raise ValueError(f"{field}不能为空")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


def normalize_batch(row):
    if not isinstance(row, dict):
        raise ValueError("批次记录必须是对象")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    for field in ("批次编号", "商品编码", "商品名称", "到期日期", "入库日期", "单位"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if any(ord(ch) < 32 for ch in item["批次编号"]):
        raise ValueError("批次编号不能包含换行")
    produced = parse_date(item["生产日期"], "生产日期", required=False)
    expires = parse_date(item["到期日期"], "到期日期")
    received = parse_date(item["入库日期"], "入库日期")
    if produced and produced > expires:
        raise ValueError("生产日期不能晚于到期日期")
    if produced and produced > received:
        raise ValueError("生产日期不能晚于入库日期")
    if received > expires:
        raise ValueError("入库日期不能晚于到期日期，过期商品不能作为新批次入库")
    item["生产日期"] = produced.isoformat() if produced else ""
    item["到期日期"] = expires.isoformat()
    item["入库日期"] = received.isoformat()
    item["当前数量"] = decimal_text(decimal_value(item["当前数量"], "当前数量"))
    item["成本单价"] = decimal_text(decimal_value(item["成本单价"], "成本单价"))
    return item


def normalize_movement(row, batch_ids):
    if not isinstance(row, dict):
        raise ValueError("库存流水记录必须是对象")
    item = {field: str(row.get(field, "") or "").strip() for field in MOVEMENT_FIELDS}
    if not item["流水编号"] or not item["批次编号"]:
        raise ValueError("库存流水编号和批次编号不能为空")
    if item["批次编号"] not in batch_ids:
        raise ValueError(f"库存流水引用了不存在的批次：{item['批次编号']}")
    if item["类型"] not in MOVEMENT_TYPES:
        raise ValueError(f"不支持的库存流水类型：{item['类型']}")
    if item["变动方向"] not in {"增加", "减少"}:
        raise ValueError("库存流水方向必须是增加或减少")
    item["变动数量"] = decimal_text(decimal_value(item["变动数量"], "变动数量", allow_zero=False))
    try:
        datetime.fromisoformat(item["发生时间"])
    except ValueError:
        raise ValueError("库存流水时间格式无效") from None
    return item


class FoodBatchStore:
    """Atomic local store for batches and append-only stock movement history."""

    def __init__(self, path):
        self.path = Path(path)
        self.batches = []
        self.movements = []
        self.load()

    @staticmethod
    def _unique_batches(rows):
        ids = [row["批次编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("批次编号重复，请先修正重复批次")

    @staticmethod
    def _unique_movements(rows):
        ids = [row["流水编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("库存流水编号重复，备份或数据文件可能损坏")

    def load(self):
        if not self.path.exists():
            self.batches, self.movements = [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
                raise ValueError("本地数据格式不受支持")
            if payload.get("version") != BACKUP_VERSION:
                raise ValueError("本地数据版本不受支持")
            raw_batches = payload.get("batches")
            raw_movements = payload.get("movements")
            if not isinstance(raw_batches, list) or not isinstance(raw_movements, list):
                raise ValueError("本地数据缺少批次或库存流水列表")
            batches = [normalize_batch(row) for row in raw_batches]
            self._unique_batches(batches)
            batch_ids = {row["批次编号"] for row in batches}
            movements = [normalize_movement(row, batch_ids) for row in raw_movements]
            self._unique_movements(movements)
            self.batches, self.movements = batches, movements
        except (OSError, json.JSONDecodeError, TypeError, AttributeError, ValueError) as exc:
            raise ValueError(f"本地数据无法读取，原文件未修改：{exc}") from exc

    def _commit(self, batches, movements):
        batches = [normalize_batch(row) for row in batches]
        self._unique_batches(batches)
        batch_ids = {row["批次编号"] for row in batches}
        movements = [normalize_movement(row, batch_ids) for row in movements]
        self._unique_movements(movements)
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "batches": batches,
            "movements": movements,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        self.batches, self.movements = batches, movements

    def _movement(self, batch, kind, direction, quantity, destination="", reason=""):
        return {
            "流水编号": uuid.uuid4().hex.upper(),
            "批次编号": batch["批次编号"],
            "商品编码": batch["商品编码"],
            "商品名称": batch["商品名称"],
            "类型": kind,
            "变动方向": direction,
            "变动数量": decimal_text(quantity),
            "发生时间": datetime.now().isoformat(timespec="seconds"),
            "去向": destination.strip(),
            "原因": reason.strip(),
        }

    def add_batch(self, row):
        item = normalize_batch(row)
        if any(r["批次编号"] == item["批次编号"] for r in self.batches):
            raise ValueError("批次编号已存在")
        batches = self.batches + [item]
        movements = list(self.movements)
        qty = Decimal(item["当前数量"])
        if qty > 0:
            movements.append(self._movement(item, "入库", "增加", qty, item["供应商"], "新批次入库"))
        self._commit(batches, movements)

    def update_batch(self, batch_id, row):
        current = next((r for r in self.batches if r["批次编号"] == batch_id), None)
        if current is None:
            raise ValueError("找不到要编辑的批次")
        item = normalize_batch(row)
        item["当前数量"] = current["当前数量"]
        if item["批次编号"] != batch_id:
            raise ValueError("批次编号创建后不可修改，以保持批次追溯关系")
        batches = [item if r["批次编号"] == batch_id else r for r in self.batches]
        movements = list(self.movements)
        self._commit(batches, movements)

    def adjust_batch(self, batch_id, direction, quantity, reason):
        if direction not in {"增加", "减少"}:
            raise ValueError("请选择增加或减少")
        if not reason.strip():
            raise ValueError("库存调整原因不能为空")
        qty = decimal_value(quantity, "调整数量", allow_zero=False)
        batch = next((r for r in self.batches if r["批次编号"] == batch_id), None)
        if batch is None:
            raise ValueError("找不到所选批次")
        old = Decimal(batch["当前数量"])
        new = old + qty if direction == "增加" else old - qty
        if new < 0:
            raise ValueError(f"库存不足，当前批次数量为 {old}")
        updated = dict(batch)
        updated["当前数量"] = decimal_text(new)
        batches = [updated if r["批次编号"] == batch_id else r for r in self.batches]
        movements = list(self.movements)
        movements.append(self._movement(updated, "调整", direction, qty, "", reason))
        self._commit(batches, movements)

    def void_batch(self, batch_id, reason):
        batch = next((r for r in self.batches if r["批次编号"] == batch_id), None)
        if batch is None:
            raise ValueError("找不到所选批次")
        qty = Decimal(batch["当前数量"])
        if qty == 0:
            raise ValueError("该批次库存已经为零")
        if not reason.strip():
            raise ValueError("作废原因不能为空")
        updated = dict(batch)
        updated["当前数量"] = "0"
        batches = [updated if r["批次编号"] == batch_id else r for r in self.batches]
        movements = list(self.movements)
        movements.append(self._movement(updated, "作废", "减少", qty, "", reason))
        self._commit(batches, movements)

    def issue_by_fefo(self, sku, quantity, destination, reason, *, today=None):
        if not destination.strip():
            raise ValueError("出库去向不能为空")
        if not reason.strip():
            raise ValueError("出库原因不能为空")
        requested = decimal_value(quantity, "出库数量", allow_zero=False)
        today = today or date.today()
        candidates = [
            row for row in self.batches
            if row["商品编码"] == sku and Decimal(row["当前数量"]) > 0
            and date.fromisoformat(row["到期日期"]) >= today
        ]
        candidates.sort(key=lambda row: (row["到期日期"], row["入库日期"], row["批次编号"]))
        remaining = requested
        allocations = []
        for batch in candidates:
            available = Decimal(batch["当前数量"])
            take = min(available, remaining)
            if take > 0:
                allocations.append((batch["批次编号"], take))
                remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            raise ValueError(f"未过期可用库存不足，缺少 {decimal_text(remaining)}")
        updated_by_id = {}
        movements = list(self.movements)
        result = []
        by_id = {batch["批次编号"]: batch for batch in self.batches}
        for batch_id, take in allocations:
            original = by_id[batch_id]
            updated = dict(original)
            updated["当前数量"] = decimal_text(Decimal(original["当前数量"]) - take)
            updated_by_id[batch_id] = updated
            movements.append(self._movement(updated, "出库", "减少", take, destination, reason))
            result.append({"批次编号": batch_id, "数量": decimal_text(take), "到期日期": original["到期日期"]})
        batches = [updated_by_id.get(batch["批次编号"], batch) for batch in self.batches]
        self._commit(batches, movements)
        return result

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS).issubset(set(reader.fieldnames)):
                raise ValueError("CSV 必须包含全部字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, start=2):
                try:
                    incoming.append(normalize_batch(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self._unique_batches(incoming)
        existing = {row["批次编号"] for row in self.batches}
        duplicates = existing.intersection(row["批次编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在批次，未导入任何数据：" + "、".join(sorted(duplicates)))
        if not incoming:
            return 0
        batches = self.batches + incoming
        movements = list(self.movements)
        for batch in incoming:
            qty = Decimal(batch["当前数量"])
            if qty > 0:
                movements.append(self._movement(batch, "入库", "增加", qty, batch["供应商"], "CSV 期初批次导入"))
        self._commit(batches, movements)
        return len(incoming)

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.batches)

    def export_movements_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MOVEMENT_FIELDS)
            writer.writeheader()
            writer.writerows(self.movements)

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "batches": self.batches,
            "movements": self.movements,
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        raw_batches = payload.get("batches")
        raw_movements = payload.get("movements")
        if not isinstance(raw_batches, list) or not isinstance(raw_movements, list):
            raise ValueError("备份文件缺少批次或库存流水")
        batches = [normalize_batch(row) for row in raw_batches]
        self._unique_batches(batches)
        batch_ids = {row["批次编号"] for row in batches}
        movements = [normalize_movement(row, batch_ids) for row in raw_movements]
        self._unique_movements(movements)
        self._commit(batches, movements)

    def movements_for(self, batch_id):
        return [row for row in self.movements if row["批次编号"] == batch_id]

    def expiry_state(self, batch, *, today=None):
        if Decimal(batch["当前数量"]) == 0:
            return "已清零", None
        today = today or date.today()
        days = (date.fromisoformat(batch["到期日期"]) - today).days
        if days < 0:
            return "已过期", days
        if days <= 3:
            return "3日内到期", days
        if days <= 7:
            return "4–7日内到期", days
        if days <= 30:
            return "8–30日内到期", days
        return "正常", days

    def fefo_batches(self, sku=None, *, today=None):
        today = today or date.today()
        rows = [
            row for row in self.batches
            if Decimal(row["当前数量"]) > 0 and date.fromisoformat(row["到期日期"]) >= today
            and (not sku or row["商品编码"] == sku)
        ]
        return sorted(rows, key=lambda row: (row["到期日期"], row["入库日期"], row["批次编号"]))


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "food_batches.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("食品批次与保质期追踪助手｜大陆版")
        root.geometry("1420x720")
        self.store = FoodBatchStore(default_data_path())

        bar = tk.Frame(root)
        bar.pack(fill="x", padx=8, pady=8)
        actions = [
            ("新增批次", self.add_batch), ("编辑批次", self.edit_batch),
            ("库存调整", self.adjust_batch), ("按效期出库", self.issue),
            ("作废批次", self.void_batch), ("批次追溯", self.trace),
            ("导入批次 CSV", self.import_csv), ("导出批次 CSV", self.export_csv),
            ("导出库存流水", self.export_movements), ("备份", self.backup),
            ("恢复备份", self.restore),
        ]
        for label, command in actions:
            tk.Button(bar, text=label, command=command).pack(side="left", padx=2)

        filters = tk.Frame(root)
        filters.pack(fill="x", padx=8, pady=(0, 4))
        self.query = tk.StringVar()
        tk.Label(filters, text="搜索").pack(side="left", padx=(0, 4))
        tk.Entry(filters, textvariable=self.query, width=26).pack(side="left")
        self.query.trace_add("write", lambda *_: self.refresh())
        tk.Label(filters, text="效期筛选").pack(side="left", padx=(14, 4))
        self.state_filter = tk.StringVar(value="全部")
        combo = ttk.Combobox(
            filters, textvariable=self.state_filter, state="readonly", width=14,
            values=("全部", "已过期", "3日内到期", "4–7日内到期", "8–30日内到期", "正常", "已清零"),
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        columns = FIELDS + ["效期状态", "剩余天数"]
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=22)
        widths = [115, 105, 145, 120, 95, 95, 95, 85, 65, 85, 90, 180, 95, 80]
        for field, width in zip(columns, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.summary = tk.StringVar()
        tk.Label(root, textvariable=self.summary, anchor="w").pack(fill="x", padx=10, pady=8)
        self.refresh()

    def selected_batch(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个批次", parent=self.root)
            return None
        values = self.tree.item(selected[0], "values")
        batch_id = values[0]
        return next((row for row in self.store.batches if row["批次编号"] == batch_id), None)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().casefold()
        selected_state = self.state_filter.get()
        expired = within7 = within30 = 0
        for index, batch in enumerate(self.store.batches):
            state, days = self.store.expiry_state(batch)
            if state == "已过期":
                expired += 1
            if days is not None and 0 <= days <= 7:
                within7 += 1
            if days is not None and 0 <= days <= 30:
                within30 += 1
            if selected_state != "全部" and selected_state != state:
                continue
            haystack = " ".join(batch[field] for field in FIELDS).casefold()
            if query and query not in haystack:
                continue
            self.tree.insert(
                "", "end", iid=str(index),
                values=[batch[field] for field in FIELDS] + [state, days if days is not None else ""],
            )
        self.summary.set(
            f"批次数：{len(self.store.batches)}    已过期：{expired}    "
            f"7 日内到期：{within7}    30 日内到期：{within30}    "
            f"库存流水：{len(self.store.movements)}    数据位置：{self.store.path}"
        )

    def form(self, existing=None):
        win = tk.Toplevel(self.root)
        win.title("批次资料")
        values = {field: tk.StringVar(value=str((existing or {}).get(field, ""))) for field in FIELDS}
        for index, field in enumerate(FIELDS):
            tk.Label(win, text=field).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            entry = tk.Entry(win, textvariable=values[field], width=38)
            entry.grid(row=index, column=1, padx=8, pady=4)
            if existing and field == "当前数量":
                entry.configure(state="readonly")
        def save():
            try:
                row = {field: values[field].get() for field in FIELDS}
                if existing:
                    self.store.update_batch(existing["批次编号"], row)
                else:
                    self.store.add_batch(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)
        tk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, columnspan=2, pady=8)

    def add_batch(self):
        self.form()

    def edit_batch(self):
        batch = self.selected_batch()
        if batch:
            self.form(batch)

    def adjust_batch(self):
        batch = self.selected_batch()
        if not batch:
            return
        win = tk.Toplevel(self.root)
        win.title("库存调整")
        direction = tk.StringVar(value="增加")
        quantity = tk.StringVar(value="1")
        reason = tk.StringVar()
        tk.Label(win, text=f"{batch['商品名称']}｜{batch['批次编号']}｜当前 {batch['当前数量']} {batch['单位']}").grid(row=0, column=0, columnspan=2, padx=8, pady=8)
        tk.Label(win, text="方向").grid(row=1, column=0, padx=8, pady=4)
        ttk.Combobox(win, textvariable=direction, state="readonly", values=("增加", "减少")).grid(row=1, column=1, padx=8, pady=4)
        tk.Label(win, text="数量").grid(row=2, column=0, padx=8, pady=4)
        tk.Entry(win, textvariable=quantity).grid(row=2, column=1, padx=8, pady=4)
        tk.Label(win, text="调整原因").grid(row=3, column=0, padx=8, pady=4)
        tk.Entry(win, textvariable=reason, width=38).grid(row=3, column=1, padx=8, pady=4)
        def save():
            try:
                self.store.adjust_batch(batch["批次编号"], direction.get(), quantity.get(), reason.get())
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("调整失败", str(exc), parent=win)
        tk.Button(win, text="确认调整", command=save).grid(row=4, column=0, columnspan=2, pady=8)

    def issue(self):
        win = tk.Toplevel(self.root)
        win.title("按效期优先出库")
        sku = tk.StringVar()
        quantity = tk.StringVar(value="1")
        destination = tk.StringVar()
        reason = tk.StringVar(value="销售出库")
        for index, (label, variable) in enumerate((
            ("商品编码", sku), ("出库数量", quantity), ("出库去向", destination), ("出库原因", reason),
        )):
            tk.Label(win, text=label).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            tk.Entry(win, textvariable=variable, width=36).grid(row=index, column=1, padx=8, pady=4)
        tk.Label(win, text="系统按最早到期批次优先分配；过期批次不会参与出库。", fg="#555").grid(row=4, column=0, columnspan=2, padx=8, pady=4)
        def save():
            try:
                allocations = self.store.issue_by_fefo(sku.get().strip(), quantity.get(), destination.get(), reason.get())
                detail = "\\n".join(f"{item['批次编号']}：{item['数量']}（到期 {item['到期日期']}）" for item in allocations)
                self.refresh()
                messagebox.showinfo("出库完成", "FEFO 批次分配：\\n" + detail, parent=win)
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("出库失败", str(exc), parent=win)
        tk.Button(win, text="确认出库", command=save).grid(row=5, column=0, columnspan=2, pady=8)

    def void_batch(self):
        batch = self.selected_batch()
        if not batch:
            return
        reason = simpledialog.askstring("作废批次", "请输入作废原因：", parent=self.root)
        if reason is None:
            return
        try:
            self.store.void_batch(batch["批次编号"], reason)
            self.refresh()
        except (ValueError, OSError) as exc:
            messagebox.showerror("作废失败", str(exc), parent=self.root)

    def trace(self):
        batch = self.selected_batch()
        if not batch:
            return
        win = tk.Toplevel(self.root)
        win.title(f"批次追溯｜{batch['批次编号']}")
        tk.Label(win, text=f"{batch['商品名称']}｜供应商：{batch['供应商']}｜到期：{batch['到期日期']}").pack(anchor="w", padx=8, pady=6)
        tree = ttk.Treeview(win, columns=MOVEMENT_FIELDS, show="headings", height=14)
        for field in MOVEMENT_FIELDS:
            tree.heading(field, text=field)
            tree.column(field, width=125)
        tree.pack(fill="both", expand=True, padx=8, pady=6)
        for movement in self.store.movements_for(batch["批次编号"]):
            tree.insert("", "end", values=[movement[field] for field in MOVEMENT_FIELDS])

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 个批次；每个批次已写入期初入库流水。")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("导出完成", "批次 CSV 已保存")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def export_movements(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_movements_csv(path)
                messagebox.showinfo("导出完成", "库存流水 CSV 已保存")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "批次和库存流水备份已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前批次和库存流水，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "批次和库存流水已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        store = FoodBatchStore(Path(folder) / "food_batches.json")
        today = date.today()
        store.add_batch({
            "批次编号": "LOT-A", "商品编码": "SKU-1", "商品名称": "测试食品",
            "供应商": "测试供应商", "生产日期": today.isoformat(),
            "到期日期": date.fromordinal(today.toordinal() + 10).isoformat(),
            "入库日期": today.isoformat(), "当前数量": "5",
            "单位": "件", "成本单价": "2.5", "库位": "A1", "备注": "",
        })
        store.issue_by_fefo("SKU-1", "1", "self-test", "smoke-test", today=today)
        assert store.batches[0]["当前数量"] == "4"
        assert len(store.movements) == 2
        assert PRODUCT == "食品批次与保质期追踪助手"
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
