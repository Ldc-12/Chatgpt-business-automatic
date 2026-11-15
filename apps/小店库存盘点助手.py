"""Offline inventory counting assistant for small shops (Windows/Tkinter)."""
import csv
import json
import math
import os
import sys
import tempfile
from datetime import datetime
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
        self._commit_rows([r for r in self.rows if r["商品编码"] != code])

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
                   ("备份", self.backup), ("恢复备份", self.restore)]
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
    assert PRODUCT == "小店库存盘点助手"
    print("SELF_TEST_OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test(); os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
