"""Offline inventory counting assistant for small shops (Windows/Tkinter)."""
import csv
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "小店库存盘点助手"
FIELDS = ["商品编码", "商品名称", "分类", "单位", "库存数量", "预警下限", "进货单价", "备注"]
NUMERIC_FIELDS = {"库存数量", "预警下限", "进货单价"}
BACKUP_VERSION = 1
MAX_ITEMS = 100_000
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 50_000
VALUATION_EXPORT_FIELDS = [
    "商品编码", "商品名称", "分类", "单位", "库存数量",
    "进货单价", "库存成本估值", "预警下限", "库存状态",
]


def number(value, field="数值"):
    try:
        result = float(str(value).replace(",", "").replace("，", "").strip() or "0")
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是数字")
    if not math.isfinite(result):
        raise ValueError(f"{field}必须是有限数字")
    if result < 0:
        raise ValueError(f"{field}不能为负数")
    return result


def normalize_row(row):
    if not isinstance(row, dict):
        raise ValueError("商品记录必须是对象")
    result = {field: str(row.get(field, "")).strip() for field in FIELDS}
    if not result["商品编码"] or not result["商品名称"]:
        raise ValueError("商品编码和商品名称不能为空")
    for field in NUMERIC_FIELDS:
        result[field] = number(result[field], field)
    return result


def _atomic_write(path, write_callback, encoding="utf-8"):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            write_callback(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _spreadsheet_safe(value):
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(" \t\r\n")
    if value[:1] in ("\t", "\r", "\n") or stripped[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _restore_spreadsheet_text(value):
    if not isinstance(value, str) or not value.startswith("'"):
        return value
    original = value[1:]
    stripped = original.lstrip(" \t\r\n")
    if original[:1] in ("\t", "\r", "\n") or stripped[:1] in ("=", "+", "-", "@"):
        return original
    return value


class InventoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.read_only = False
        self.load_error = None
        self.load()

    @classmethod
    def open_for_recovery(cls, path):
        """Open a damaged store without replacing or hiding its original file."""
        try:
            return cls(path)
        except ValueError as exc:
            store = cls.__new__(cls)
            store.path = Path(path)
            store.rows = []
            store.read_only = True
            store.load_error = str(exc)
            return store

    def _ensure_writable(self):
        if self.read_only:
            raise ValueError(
                "库存数据无法读取，软件已进入只读恢复模式。"
                "请先恢复有效备份；恢复前不会覆盖原始数据文件。"
            )

    @staticmethod
    def _check_unique(rows):
        codes = [row["商品编码"] for row in rows]
        if len(codes) != len(set(codes)):
            raise ValueError("商品编码重复，请先修正重复编码")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            if self.path.stat().st_size > MAX_BACKUP_BYTES:
                raise ValueError("库存数据文件超过 100 MiB 限制")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("数据文件格式错误")
            if len(data) > MAX_ITEMS:
                raise ValueError("库存记录超过 100,000 条限制")
            rows = []
            for index, row in enumerate(data, start=1):
                try:
                    rows.append(normalize_row(row))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"第 {index} 条商品记录无效：{exc}") from exc
            self._check_unique(rows)
            self.rows = rows
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"库存数据无法读取，原文件未修改：{exc}") from exc

    def _commit_rows(self, rows, allow_recovery=False):
        if self.read_only and not allow_recovery:
            self._ensure_writable()
        snapshot = [dict(row) for row in rows]
        if len(snapshot) > MAX_ITEMS:
            raise ValueError("库存记录超过 100,000 条限制")
        self._check_unique(snapshot)
        content = json.dumps(snapshot, ensure_ascii=False, indent=2)
        if len(content.encode("utf-8")) > MAX_BACKUP_BYTES:
            raise ValueError("库存数据超过 100 MiB 限制")
        _atomic_write(self.path, lambda handle: handle.write(content))
        self.rows = snapshot
        self.read_only = False
        self.load_error = None

    def save(self):
        self._commit_rows(self.rows)

    def add(self, row):
        self._ensure_writable()
        item = normalize_row(row)
        if any(r["商品编码"] == item["商品编码"] for r in self.rows):
            raise ValueError("商品编码已存在")
        self._commit_rows([*self.rows, item])

    def update(self, old_code, row):
        self._ensure_writable()
        item = normalize_row(row)
        if any(r["商品编码"] == item["商品编码"] and r["商品编码"] != old_code for r in self.rows):
            raise ValueError("商品编码已存在")
        index = next((i for i, r in enumerate(self.rows) if r["商品编码"] == old_code), None)
        if index is None:
            raise ValueError("找不到要编辑的商品")
        updated = list(self.rows)
        updated[index] = item
        self._commit_rows(updated)

    def delete(self, code):
        self._ensure_writable()
        target_code = str(code or "").strip()
        if not target_code:
            raise ValueError("商品编码不能为空")
        if not any(row["商品编码"] == target_code for row in self.rows):
            raise ValueError("找不到要删除的商品")
        self._commit_rows([r for r in self.rows if r["商品编码"] != target_code])

    def import_csv(self, path):
        self._ensure_writable()
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("CSV 文件超过 25 MiB 限制")
        incoming = []
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                raise ValueError("CSV 表头存在重复列")
            if set(headers) != set(FIELDS):
                raise ValueError("CSV 必须且只能包含全部字段：" + "、".join(FIELDS))
            for line, raw_row in enumerate(reader, start=2):
                if raw_row is None or all(value is None or str(value).strip() == "" for value in raw_row.values()):
                    continue
                if None in raw_row or any(raw_row.get(field) is None for field in FIELDS):
                    raise ValueError(f"第 {line} 行：列数与表头不一致")
                row = dict(raw_row)
                for field in FIELDS:
                    if field not in NUMERIC_FIELDS:
                        row[field] = _restore_spreadsheet_text(row[field])
                try:
                    incoming.append(normalize_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
                if len(incoming) > MAX_CSV_ROWS:
                    raise ValueError("CSV 超过 50,000 条记录限制")
        self._check_unique(incoming)
        existing = {r["商品编码"] for r in self.rows}
        duplicates = existing.intersection(r["商品编码"] for r in incoming)
        if duplicates:
            raise ValueError("导入包含已存在商品编码，未导入任何数据：" + "、".join(sorted(duplicates)))
        if len(self.rows) + len(incoming) > MAX_ITEMS:
            raise ValueError("导入后库存记录将超过 100,000 条限制")
        self._commit_rows([*self.rows, *incoming])
        return len(incoming)

    def export_csv(self, path):
        self._ensure_writable()
        target = Path(path)

        def write(handle):
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row in self.rows:
                writer.writerow({field: _spreadsheet_safe(row[field]) for field in FIELDS})

        _atomic_write(target, write, encoding="utf-8-sig")

    def backup(self, path):
        self._ensure_writable()
        payload = {
            "format": "mainland-inventory-backup",
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "items": self.rows,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(content.encode("utf-8")) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 限制")
        _atomic_write(path, lambda handle: handle.write(content))

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 限制")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"备份文件无法读取：{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("备份文件顶层必须是 JSON 对象")
        if payload.get("format") != "mainland-inventory-backup" or type(payload.get("version")) is not int or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("备份文件 items 必须是数组")
        if len(items) > MAX_ITEMS:
            raise ValueError("备份记录超过 100,000 条限制")
        rows = []
        for index, row in enumerate(items, start=1):
            try:
                rows.append(normalize_row(row))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"备份第 {index} 条商品记录无效：{exc}") from exc
        self._check_unique(rows)
        self._commit_rows(rows, allow_recovery=True)



def build_valuation_report(rows):
    """Build a read-only valuation snapshot using each SKU's currently recorded purchase price."""
    categories = {}
    items = []
    total_quantity = Decimal("0")
    total_value = Decimal("0.00")
    zero_stock_count = 0
    alert_count = 0

    for raw in rows:
        row = normalize_row(raw)
        quantity = Decimal(str(row["库存数量"]))
        unit_price = Decimal(str(row["进货单价"]))
        threshold = Decimal(str(row["预警下限"]))
        try:
            value = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError(f"商品 {row['商品编码']} 的库存估值超出可计算范围") from exc
        category = row["分类"].strip() or "未分类"
        is_zero = quantity == 0
        is_alert = quantity <= threshold
        status = "零库存" if is_zero else ("库存预警" if is_alert else "库存正常")

        item = {
            "商品编码": row["商品编码"],
            "商品名称": row["商品名称"],
            "分类": category,
            "单位": row["单位"],
            "库存数量": quantity,
            "进货单价": unit_price,
            "库存成本估值": value,
            "预警下限": threshold,
            "库存状态": status,
        }
        items.append(item)
        total_quantity += quantity
        total_value += value
        zero_stock_count += int(is_zero)
        alert_count += int(is_alert)

        group = categories.setdefault(category, {
            "分类": category,
            "商品种类": 0,
            "库存总数量": Decimal("0"),
            "库存成本估值": Decimal("0.00"),
            "零库存商品数": 0,
            "预警商品数": 0,
        })
        group["商品种类"] += 1
        group["库存总数量"] += quantity
        group["库存成本估值"] += value
        group["零库存商品数"] += int(is_zero)
        group["预警商品数"] += int(is_alert)

    category_rows = sorted(
        categories.values(),
        key=lambda item: (-item["库存成本估值"], item["分类"].casefold()),
    )
    item_rows = sorted(
        items,
        key=lambda item: (-item["库存成本估值"], item["商品编码"].casefold()),
    )
    return {
        "summary": {
            "商品种类": len(items),
            "库存总数量": total_quantity,
            "库存成本估值": total_value,
            "零库存商品数": zero_stock_count,
            "预警商品数": alert_count,
        },
        "categories": category_rows,
        "items": item_rows,
    }


def export_valuation_csv(path, rows):
    """Export SKU-level valuation details with spreadsheet-formula protection."""
    report = build_valuation_report(rows)

    def write(handle):
        writer = csv.DictWriter(handle, fieldnames=VALUATION_EXPORT_FIELDS)
        writer.writeheader()
        for item in report["items"]:
            writer.writerow({
                "商品编码": _spreadsheet_safe(item["商品编码"]),
                "商品名称": _spreadsheet_safe(item["商品名称"]),
                "分类": _spreadsheet_safe(item["分类"]),
                "单位": _spreadsheet_safe(item["单位"]),
                "库存数量": format(item["库存数量"], "f"),
                "进货单价": format(item["进货单价"], ".2f"),
                "库存成本估值": format(item["库存成本估值"], ".2f"),
                "预警下限": format(item["预警下限"], "f"),
                "库存状态": _spreadsheet_safe(item["库存状态"]),
            })

    _atomic_write(path, write, encoding="utf-8-sig")
    return len(report["items"])

def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "inventory.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("小店库存盘点助手｜大陆版")
        root.geometry("1100x650")
        self.store = InventoryStore.open_for_recovery(default_data_path())
        bar = tk.Frame(root); bar.pack(fill="x", padx=8, pady=8)
        actions = [("新增商品", self.add), ("编辑", self.edit), ("删除", self.delete),
                   ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
                   ("库存估值分析", self.valuation), ("备份", self.backup), ("恢复备份", self.restore)]
        self.action_buttons = {}
        for label, command in actions:
            button = tk.Button(bar, text=label, command=command)
            button.pack(side="left", padx=3)
            self.action_buttons[label] = button
            if self.store.read_only and label != "恢复备份":
                button.configure(state="disabled")
        self.recovery_notice = None
        if self.store.read_only:
            self.recovery_notice = tk.Label(
                root,
                text="库存数据文件无法读取，已进入只读恢复模式。原文件未修改；请先恢复有效备份。",
                fg="#b00020",
                anchor="w",
                justify="left",
            )
            self.recovery_notice.pack(fill="x", padx=10, pady=4)
        self.query = tk.StringVar()
        tk.Label(bar, text="搜索").pack(side="left", padx=(14, 3))
        entry = tk.Entry(bar, textvariable=self.query, width=22); entry.pack(side="left")
        self.query.trace_add("write", lambda *_: self.refresh())
        self.tree = ttk.Treeview(root, columns=FIELDS, show="headings")
        for field in FIELDS:
            self.tree.heading(field, text=field); self.tree.column(field, width=125)
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.summary = tk.StringVar(); tk.Label(root, textvariable=self.summary, anchor="w").pack(fill="x", padx=10, pady=8)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if self.store.read_only:
            self.summary.set(
                f"恢复模式：原始库存文件未修改。请先恢复有效备份。数据位置：{self.store.path}"
            )
            return
        q = self.query.get().casefold()
        for row in self.store.rows:
            if q and q not in " ".join(str(row[f]) for f in FIELDS).casefold():
                continue
            self.tree.insert("", "end", iid=row["商品编码"], values=[row[f] for f in FIELDS])
        low = sum(1 for row in self.store.rows if row["库存数量"] <= row["预警下限"])
        self.summary.set(f"商品种类：{len(self.store.rows)}    库存预警：{low} 项    数据位置：{self.store.path}")

    def form(self, existing=None):
        win = tk.Toplevel(self.root); win.title("商品资料")
        values = {f: tk.StringVar(value=str((existing or {}).get(f, ""))) for f in FIELDS}
        for i, field in enumerate(FIELDS):
            tk.Label(win, text=field).grid(row=i, column=0, padx=8, pady=4, sticky="e")
            tk.Entry(win, textvariable=values[field], width=36).grid(row=i, column=1, padx=8, pady=4)
        def save():
            try:
                row = {f: values[f].get() for f in FIELDS}
                if existing: self.store.update(existing["商品编码"], row)
                else: self.store.add(row)
                self.refresh(); win.destroy()
            except (ValueError, OSError) as exc: messagebox.showerror("保存失败", str(exc), parent=win)
        tk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, columnspan=2, pady=8)

    def add(self): self.form()
    def edit(self):
        selected = self.tree.selection()
        if selected:
            row = next((r for r in self.store.rows if r["商品编码"] == selected[0]), None)
            if row: self.form(row)
    def delete(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno("确认删除", "删除所选商品？"):
            try:
                self.store.delete(selected[0]); self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))
    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path); self.refresh()
                messagebox.showinfo("导入完成", f"成功导入 {count} 条商品")
            except (ValueError, OSError) as exc: messagebox.showerror("导入失败", str(exc))
    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try: self.store.export_csv(path); messagebox.showinfo("导出完成", "CSV 已保存")
            except (ValueError, OSError) as exc: messagebox.showerror("导出失败", str(exc))
    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try: self.store.backup(path); messagebox.showinfo("备份完成", "备份文件已保存")
            except (ValueError, OSError) as exc: messagebox.showerror("备份失败", str(exc))

    def valuation(self):
        try:
            self.store._ensure_writable()
            report = build_valuation_report(self.store.rows)
        except (ValueError, OSError) as exc:
            messagebox.showerror("库存估值失败", str(exc))
            return

        win = tk.Toplevel(self.root)
        win.title("库存估值分析｜按当前进货单价估算")
        win.geometry("1000x620")
        summary = report["summary"]
        summary_text = (
            f"商品种类：{summary['商品种类']}    "
            f"库存总数量：{format(summary['库存总数量'], 'f')}    "
            f"库存成本估值：¥{summary['库存成本估值']:,.2f}    "
            f"零库存：{summary['零库存商品数']}    "
            f"库存预警：{summary['预警商品数']}"
        )
        tk.Label(win, text=summary_text, anchor="w", justify="left").pack(
            fill="x", padx=10, pady=10
        )
        tk.Label(
            win,
            text="估值口径：当前库存数量 × 商品资料中的进货单价；不含税费、运费及市场售价。",
            anchor="w",
            fg="#555555",
        ).pack(fill="x", padx=10, pady=(0, 8))

        columns = ("分类", "商品种类", "库存总数量", "库存成本估值", "零库存商品数", "预警商品数")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=18)
        widths = (220, 100, 130, 150, 120, 120)
        for field, width in zip(columns, widths):
            tree.heading(field, text=field)
            tree.column(field, width=width, anchor="w" if field == "分类" else "center")
        for item in report["categories"]:
            tree.insert("", "end", values=(
                item["分类"],
                item["商品种类"],
                format(item["库存总数量"], "f"),
                f"{item['库存成本估值']:,.2f}",
                item["零库存商品数"],
                item["预警商品数"],
            ))
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        def export_details():
            target = filedialog.asksaveasfilename(
                parent=win,
                defaultextension=".csv",
                initialfile="库存估值明细.csv",
                filetypes=[("CSV 文件", "*.csv")],
            )
            if not target:
                return
            try:
                count = export_valuation_csv(target, self.store.rows)
                messagebox.showinfo("导出完成", f"已导出 {count} 条商品估值明细。", parent=win)
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc), parent=win)

        tk.Button(win, text="导出商品估值明细 CSV", command=export_details).pack(
            anchor="e", padx=10, pady=10
        )

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path:
            if self.store.read_only:
                prompt = (
                    "恢复会使用所选备份替换无法读取的库存文件。"
                    "如果需要保留损坏原件，请先在资源管理器复制该文件。继续？"
                )
            else:
                prompt = "恢复会替换当前库存数据，建议先备份。继续？"
            if messagebox.askyesno("确认恢复", prompt):
                try:
                    self.store.restore(path)
                    for button in self.action_buttons.values():
                        button.configure(state="normal")
                    if self.recovery_notice is not None:
                        self.recovery_notice.destroy()
                        self.recovery_notice = None
                    self.refresh()
                    messagebox.showinfo("恢复完成", "库存数据已恢复")
                except (ValueError, OSError) as exc:
                    messagebox.showerror("恢复失败", str(exc))


def self_test():
    sample = normalize_row({"商品编码": "A001", "商品名称": "测试商品", "库存数量": "5", "预警下限": "2", "进货单价": "3.5"})
    assert sample["库存数量"] == 5.0 and sample["进货单价"] == 3.5
    report = build_valuation_report([sample])
    assert report["summary"]["库存成本估值"] == Decimal("17.50")
    assert report["categories"][0]["商品种类"] == 1
    assert PRODUCT == "小店库存盘点助手"
    print("SELF_TEST_OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test(); os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
