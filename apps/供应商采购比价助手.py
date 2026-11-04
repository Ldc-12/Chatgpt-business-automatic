"""Offline supplier quote comparison assistant for small businesses."""
import csv
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "供应商采购比价助手"
FIELDS = [
    "报价编号", "物料编码", "物料名称", "供应商", "规格", "单位",
    "未税单价", "税率(%)", "采购数量", "运费总额", "报价日期", "有效期至", "备注",
]
DECIMAL_FIELDS = {"未税单价", "税率(%)", "采购数量", "运费总额"}
BACKUP_FORMAT = "mainland-purchase-compare-backup"
BACKUP_VERSION = 1
DISPLAY_FIELDS = FIELDS + ["含税到货单价", "报价状态", "推荐"]


def decimal_value(value, field, *, allow_zero=True, maximum=None):
    raw = str(value).replace(",", "").replace("，", "").strip() or "0"
    try:
        result = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是有效数字") from exc
    if not result.is_finite():
        raise ValueError(f"{field}必须是有限数字")
    if result < 0 or (not allow_zero and result == 0):
        suffix = "必须大于 0" if not allow_zero else "不能为负数"
        raise ValueError(f"{field}{suffix}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field}不能超过 {maximum}")
    return result


def decimal_text(value):
    return format(value, "f")


def normalize_quote(row):
    if not isinstance(row, dict):
        raise ValueError("报价记录格式错误")
    result = {field: str(row.get(field, "")).strip() for field in FIELDS}
    required = ("报价编号", "物料编码", "物料名称", "供应商", "单位")
    missing = [field for field in required if not result[field]]
    if missing:
        raise ValueError("以下字段不能为空：" + "、".join(missing))
    for field in DECIMAL_FIELDS:
        parsed = decimal_value(
            result[field],
            field,
            allow_zero=(field != "采购数量"),
            maximum=Decimal("100") if field == "税率(%)" else None,
        )
        result[field] = decimal_text(parsed)
    try:
        quote_date = date.fromisoformat(result["报价日期"])
    except ValueError as exc:
        raise ValueError("报价日期必须使用 YYYY-MM-DD 格式") from exc
    if result["有效期至"]:
        try:
            valid_until = date.fromisoformat(result["有效期至"])
        except ValueError as exc:
            raise ValueError("有效期至必须使用 YYYY-MM-DD 格式") from exc
        if valid_until < quote_date:
            raise ValueError("报价有效期不能早于报价日期")
    return result


def landed_unit_cost(quote):
    unit_price = Decimal(quote["未税单价"])
    tax_rate = Decimal(quote["税率(%)"])
    quantity = Decimal(quote["采购数量"])
    freight_total = Decimal(quote["运费总额"])
    return unit_price * (Decimal("1") + tax_rate / Decimal("100")) + freight_total / quantity


def quote_status(quote, as_of=None):
    if not quote["有效期至"]:
        return "未设置有效期"
    as_of = as_of or date.today()
    return "已过期" if date.fromisoformat(quote["有效期至"]) < as_of else "有效"


def best_quote_by_material(quotes, as_of=None):
    best = {}
    for quote in quotes:
        if quote_status(quote, as_of) == "已过期":
            continue
        code = quote["物料编码"]
        key = (landed_unit_cost(quote), quote["报价日期"], quote["供应商"], quote["报价编号"])
        previous = best.get(code)
        if previous is None or key < previous[0]:
            best[code] = (key, quote)
    return {code: item[1] for code, item in best.items()}


class PurchaseStore:
    def __init__(self, path):
        self.path = Path(path)
        self.quotes = []
        self.load()

    @staticmethod
    def validate_unique(quotes):
        ids = [quote["报价编号"] for quote in quotes]
        if len(ids) != len(set(ids)):
            raise ValueError("报价编号重复，请检查后再保存")

    def load(self):
        if not self.path.exists():
            self.quotes = []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != BACKUP_VERSION
                or not isinstance(payload.get("quotes"), list)
            ):
                raise ValueError("采购报价数据格式或版本不受支持")
            quotes = [normalize_quote(item) for item in payload["quotes"]]
            self.validate_unique(quotes)
            self.quotes = quotes
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"采购报价数据无法读取，原文件未修改：{exc}") from exc

    def save(self, quotes=None):
        rows = self.quotes if quotes is None else quotes
        self.validate_unique(rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "quotes": rows,
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def add(self, row):
        quote = normalize_quote(row)
        if any(item["报价编号"] == quote["报价编号"] for item in self.quotes):
            raise ValueError("报价编号已存在")
        updated = self.quotes + [quote]
        self.save(updated)
        self.quotes = updated

    def update(self, old_id, row):
        quote = normalize_quote(row)
        if any(item["报价编号"] == quote["报价编号"] and item["报价编号"] != old_id for item in self.quotes):
            raise ValueError("报价编号已存在")
        index = next((i for i, item in enumerate(self.quotes) if item["报价编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要编辑的报价")
        updated = list(self.quotes)
        updated[index] = quote
        self.save(updated)
        self.quotes = updated

    def delete(self, quote_id):
        updated = [item for item in self.quotes if item["报价编号"] != quote_id]
        self.save(updated)
        self.quotes = updated

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS).issubset(set(reader.fieldnames)):
                raise ValueError("CSV 必须包含全部字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, start=2):
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_quote(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self.validate_unique(incoming)
        existing = {item["报价编号"] for item in self.quotes}
        duplicates = existing.intersection(item["报价编号"] for item in incoming)
        if duplicates:
            raise ValueError("导入包含已存在报价编号，未导入任何数据：" + "、".join(sorted(duplicates)))
        updated = self.quotes + incoming
        self.save(updated)
        self.quotes = updated
        return len(incoming)

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.quotes)

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "quotes": self.quotes,
        }
        target = Path(path)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("format") != BACKUP_FORMAT
            or payload.get("version") != BACKUP_VERSION
            or not isinstance(payload.get("quotes"), list)
        ):
            raise ValueError("备份文件格式或版本不受支持")
        quotes = [normalize_quote(item) for item in payload["quotes"]]
        self.validate_unique(quotes)
        self.save(quotes)
        self.quotes = quotes


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "purchase_quotes.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("供应商采购比价助手｜大陆版")
        root.geometry("1420x700")
        self.store = PurchaseStore(default_data_path())
        bar = tk.Frame(root)
        bar.pack(fill="x", padx=8, pady=8)
        actions = [
            ("新增报价", self.add), ("编辑报价", self.edit), ("删除报价", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]
        for label, command in actions:
            tk.Button(bar, text=label, command=command).pack(side="left", padx=3)
        self.query = tk.StringVar()
        tk.Label(bar, text="搜索").pack(side="left", padx=(14, 3))
        tk.Entry(bar, textvariable=self.query, width=24).pack(side="left")
        self.query.trace_add("write", lambda *_: self.refresh())
        frame = tk.Frame(root)
        frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(frame, columns=DISPLAY_FIELDS, show="headings")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        widths = {"备注": 150, "物料名称": 145, "供应商": 130, "报价编号": 115, "规格": 110}
        for field in DISPLAY_FIELDS:
            self.tree.heading(field, text=field)
            self.tree.column(field, width=widths.get(field, 105), minwidth=75, stretch=False)
        self.tree.tag_configure("best", background="#e6f4ea")
        self.summary = tk.StringVar()
        tk.Label(root, textvariable=self.summary, anchor="w").pack(fill="x", padx=10, pady=8)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        best = best_quote_by_material(self.store.quotes)
        query = self.query.get().casefold()
        ordered = sorted(self.store.quotes, key=lambda q: (q["物料编码"], landed_unit_cost(q), q["供应商"]))
        for quote in ordered:
            cost = landed_unit_cost(quote)
            status = quote_status(quote)
            recommended = best.get(quote["物料编码"], {}).get("报价编号") == quote["报价编号"]
            values = [quote[field] for field in FIELDS] + [f"{cost:.4f}", status, "推荐" if recommended else ""]
            searchable = " ".join(str(value) for value in values).casefold()
            if query and query not in searchable:
                continue
            self.tree.insert("", "end", iid=quote["报价编号"], values=values, tags=("best",) if recommended else ())
        material_count = len({q["物料编码"] for q in self.store.quotes})
        valid_count = sum(1 for q in self.store.quotes if quote_status(q) != "已过期")
        self.summary.set(
            f"报价记录：{len(self.store.quotes)} 条    物料种类：{material_count} 种"
            f"    当前有效报价：{valid_count} 条    绿色行：该物料当前最低含税到货单价"
            f"    数据位置：{self.store.path}"
        )

    def form(self, existing=None):
        win = tk.Toplevel(self.root)
        win.title("供应商报价资料")
        defaults = {"报价日期": date.today().isoformat(), "税率(%)": "13", "采购数量": "1", "运费总额": "0"}
        values = {
            field: tk.StringVar(value=str((existing or {}).get(field, defaults.get(field, ""))))
            for field in FIELDS
        }
        for index, field in enumerate(FIELDS):
            tk.Label(win, text=field).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            tk.Entry(win, textvariable=values[field], width=38).grid(row=index, column=1, padx=8, pady=4)
        tk.Label(
            win,
            text="比较公式：未税单价 × (1 + 税率) + 运费总额 ÷ 采购数量",
            fg="gray",
        ).grid(row=len(FIELDS), column=0, columnspan=2, padx=8, pady=6)

        def save():
            try:
                row = {field: values[field].get() for field in FIELDS}
                if existing:
                    self.store.update(existing["报价编号"], row)
                else:
                    self.store.add(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        tk.Button(win, text="保存报价", command=save).grid(row=len(FIELDS) + 1, column=0, columnspan=2, pady=8)

    def add(self):
        self.form()

    def edit(self):
        selected = self.tree.selection()
        if selected:
            quote = next((q for q in self.store.quotes if q["报价编号"] == selected[0]), None)
            if quote:
                self.form(quote)

    def delete(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno("确认删除", "删除所选报价记录？"):
            try:
                self.store.delete(selected[0])
                self.refresh()
            except OSError as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功追加 {count} 条报价记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("导出完成", "CSV 已保存")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "备份文件已保存")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前全部报价记录，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "报价数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    sample = normalize_quote({
        "报价编号": "Q-001", "物料编码": "M-001", "物料名称": "测试物料",
        "供应商": "测试供应商", "单位": "件", "未税单价": "10",
        "税率(%)": "13", "采购数量": "100", "运费总额": "20",
        "报价日期": date.today().isoformat(),
    })
    assert landed_unit_cost(sample) == Decimal("11.70")
    assert best_quote_by_material([sample])["M-001"]["报价编号"] == "Q-001"
    assert PRODUCT == "供应商采购比价助手"
    print("SELF_TEST_OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
