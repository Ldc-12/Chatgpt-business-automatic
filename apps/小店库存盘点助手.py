"""Offline inventory counting assistant for small shops (Windows/Tkinter)."""
import csv
import json
import os
import sys
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


def number(value, field="数值"):
    try:
        result = float(str(value).replace(",", "").replace("，", "").strip() or "0")
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是数字")
    if result < 0:
        raise ValueError(f"{field}不能为负数")
    return result


def normalize_row(row):
    result = {field: str(row.get(field, "")).strip() for field in FIELDS}
    if not result["商品编码"] or not result["商品名称"]:
        raise ValueError("商品编码和商品名称不能为空")
    for field in NUMERIC_FIELDS:
        result[field] = number(result[field], field)
    return result


class InventoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("数据文件格式错误")
            self.rows = [normalize_row(row) for row in data]
            self._check_unique(self.rows)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"库存数据无法读取，原文件未修改：{exc}") from exc

    @staticmethod
    def _check_unique(rows):
        codes = [row["商品编码"] for row in rows]
        if len(codes) != len(set(codes)):
            raise ValueError("商品编码重复，请先修正重复编码")

    def save(self):
        self._check_unique(self.rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def add(self, row):
        item = normalize_row(row)
        if any(r["商品编码"] == item["商品编码"] for r in self.rows):
            raise ValueError("商品编码已存在")
        self.rows.append(item)
        self.save()

    def update(self, old_code, row):
        item = normalize_row(row)
        if any(r["商品编码"] == item["商品编码"] and r["商品编码"] != old_code for r in self.rows):
            raise ValueError("商品编码已存在")
        index = next((i for i, r in enumerate(self.rows) if r["商品编码"] == old_code), None)
        if index is None:
            raise ValueError("找不到要编辑的商品")
        self.rows[index] = item
        self.save()

    def delete(self, code):
        self.rows = [r for r in self.rows if r["商品编码"] != code]
        self.save()

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS).issubset(set(reader.fieldnames)):
                raise ValueError("CSV 必须包含全部字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, start=2):
                try:
                    incoming.append(normalize_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self._check_unique(incoming)
        existing = {r["商品编码"] for r in self.rows}
        duplicates = existing.intersection(r["商品编码"] for r in incoming)
        if duplicates:
            raise ValueError("导入包含已存在商品编码，未导入任何数据：" + "、".join(sorted(duplicates)))
        self.rows.extend(incoming)
        self.save()
        return len(incoming)

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

    def backup(self, path):
        payload = {"format": "mainland-inventory-backup", "version": BACKUP_VERSION,
                   "created_at": datetime.now().isoformat(timespec="seconds"), "items": self.rows}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("format") != "mainland-inventory-backup" or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        rows = [normalize_row(row) for row in payload.get("items", [])]
        self._check_unique(rows)
        self.rows = rows
        self.save()


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "inventory.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("小店库存盘点助手｜大陆版")
        root.geometry("1100x650")
        self.store = InventoryStore(default_data_path())
        bar = tk.Frame(root); bar.pack(fill="x", padx=8, pady=8)
        actions = [("新增商品", self.add), ("编辑", self.edit), ("删除", self.delete),
                   ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
                   ("备份", self.backup), ("恢复备份", self.restore)]
        for label, command in actions:
            tk.Button(bar, text=label, command=command).pack(side="left", padx=3)
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
            self.store.delete(selected[0]); self.refresh()
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
            except OSError as exc: messagebox.showerror("导出失败", str(exc))
    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try: self.store.backup(path); messagebox.showinfo("备份完成", "备份文件已保存")
            except OSError as exc: messagebox.showerror("备份失败", str(exc))
    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前库存数据，建议先备份。继续？"):
            try: self.store.restore(path); self.refresh(); messagebox.showinfo("恢复完成", "库存数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc: messagebox.showerror("恢复失败", str(exc))


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
