"""Offline Chinese quotation generator for small businesses and freelancers."""
import csv
import json
import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "报价单生成器"
BACKUP_FORMAT = "mainland-quotation-backup"
BACKUP_VERSION = 1
QUOTE_FIELDS = ["报价单号", "客户名称", "联系人", "联系电话", "报价日期", "有效期至", "税率(%)", "备注"]
ITEM_FIELDS = ["项目名称", "规格型号", "单位", "数量", "单价", "项目备注"]
CSV_FIELDS = QUOTE_FIELDS + ITEM_FIELDS


def decimal_value(value, field, *, positive=False, maximum=None):
    raw = str(value).replace(",", "").replace("，", "").strip() or "0"
    try:
        result = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是有效数字") from exc
    if not result.is_finite():
        raise ValueError(f"{field}必须是有限数字")
    if result < 0 or (positive and result == 0):
        raise ValueError(f"{field}{'必须大于 0' if positive else '不能为负数'}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field}不能超过 {maximum}")
    return result


def decimal_text(value):
    return format(value, "f")


def money_text(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def normalize_item(item):
    if not isinstance(item, dict):
        raise ValueError("报价明细格式错误")
    result = {field: str(item.get(field, "")).strip() for field in ITEM_FIELDS}
    if not result["项目名称"]:
        raise ValueError("项目名称不能为空")
    if not result["单位"]:
        raise ValueError("单位不能为空")
    quantity = decimal_value(result["数量"], "数量", positive=True)
    price = decimal_value(result["单价"], "单价")
    result["数量"] = decimal_text(quantity)
    result["单价"] = decimal_text(price)
    return result


def normalize_quote(quote):
    if not isinstance(quote, dict):
        raise ValueError("报价单格式错误")
    result = {field: str(quote.get(field, "")).strip() for field in QUOTE_FIELDS}
    if not result["报价单号"] or not result["客户名称"]:
        raise ValueError("报价单号和客户名称不能为空")
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
    tax_rate = decimal_value(result["税率(%)"], "税率", maximum=Decimal("100"))
    result["税率(%)"] = decimal_text(tax_rate)
    items = quote.get("明细")
    if not isinstance(items, list) or not items:
        raise ValueError("至少添加一条报价明细")
    result["明细"] = [normalize_item(item) for item in items]
    return result


def calculate_totals(quote):
    normalized = normalize_quote(quote)
    subtotal_raw = sum(
        (Decimal(item["数量"]) * Decimal(item["单价"]) for item in normalized["明细"]),
        Decimal("0"),
    )
    subtotal = subtotal_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax = (subtotal * Decimal(normalized["税率(%)"]) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}


def next_quote_number(existing, today=None):
    today = today or date.today()
    prefix = f"BJ-{today:%Y%m%d}-"
    used = []
    for quote in existing:
        number = str(quote.get("报价单号", ""))
        if number.startswith(prefix):
            try:
                used.append(int(number[len(prefix):]))
            except ValueError:
                continue
    return prefix + f"{max(used, default=0) + 1:03d}"


class QuoteStore:
    def __init__(self, path):
        self.path = Path(path)
        self.quotes = []
        self.load()

    @staticmethod
    def _check_unique(quotes):
        ids = [q["报价单号"] for q in quotes]
        if len(ids) != len(set(ids)):
            raise ValueError("报价单号重复")

    def load(self):
        if not self.path.exists():
            self.quotes = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("报价数据文件格式错误")
            rows = [normalize_quote(q) for q in raw]
            self._check_unique(rows)
            self.quotes = rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"报价数据无法读取，原文件未修改：{exc}") from exc

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def save(self):
        self._check_unique(self.quotes)
        self._write(self.quotes)

    def add(self, quote):
        item = normalize_quote(quote)
        if any(q["报价单号"] == item["报价单号"] for q in self.quotes):
            raise ValueError("报价单号已存在")
        rows = self.quotes + [item]
        self._write(rows)
        self.quotes = rows

    def update(self, old_number, quote):
        item = normalize_quote(quote)
        if any(q["报价单号"] == item["报价单号"] and q["报价单号"] != old_number for q in self.quotes):
            raise ValueError("报价单号已存在")
        index = next((i for i, q in enumerate(self.quotes) if q["报价单号"] == old_number), None)
        if index is None:
            raise ValueError("找不到要修改的报价单")
        rows = list(self.quotes)
        rows[index] = item
        self._write(rows)
        self.quotes = rows

    def delete(self, number):
        rows = [q for q in self.quotes if q["报价单号"] != number]
        self._write(rows)
        self.quotes = rows

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for quote in self.quotes:
                metadata = {field: quote[field] for field in QUOTE_FIELDS}
                for item in quote["明细"]:
                    writer.writerow({**metadata, **item})

    def import_csv(self, path):
        grouped = {}
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(CSV_FIELDS).issubset(set(reader.fieldnames)):
                raise ValueError("CSV 必须包含完整报价单和明细字段：" + "、".join(CSV_FIELDS))
            for line, row in enumerate(reader, start=2):
                try:
                    metadata = {field: str(row.get(field, "")).strip() for field in QUOTE_FIELDS}
                    number = metadata["报价单号"]
                    if not number:
                        raise ValueError("报价单号不能为空")
                    item = normalize_item({field: row.get(field, "") for field in ITEM_FIELDS})
                    if number not in grouped:
                        grouped[number] = {**metadata, "明细": []}
                    elif any(grouped[number][field] != metadata[field] for field in QUOTE_FIELDS):
                        raise ValueError("同一报价单号的客户或日期等信息不一致")
                    grouped[number]["明细"].append(item)
                except ValueError as exc:
                    raise ValueError(f"CSV 第 {line} 行：{exc}") from exc
        incoming = [normalize_quote(q) for q in grouped.values()]
        self._check_unique(incoming)
        existing = {q["报价单号"] for q in self.quotes}
        duplicates = existing.intersection(q["报价单号"] for q in incoming)
        if duplicates:
            raise ValueError("导入包含已存在报价单号，未导入任何数据：" + "、".join(sorted(duplicates)))
        rows = self.quotes + incoming
        self._write(rows)
        self.quotes = rows
        return len(incoming)

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "quotes": self.quotes,
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
            raise ValueError("备份文件版本或格式不受支持")
        raw = payload.get("quotes")
        if not isinstance(raw, list):
            raise ValueError("备份中的报价单列表格式错误")
        rows = [normalize_quote(q) for q in raw]
        self._check_unique(rows)
        self._write(rows)
        self.quotes = rows


def export_quote_pdf(quote, path):
    quote = normalize_quote(quote)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass
    font = "STSong-Light"
    title = ParagraphStyle("QuoteTitle", fontName=font, fontSize=20, leading=26, alignment=1, spaceAfter=12)
    body = ParagraphStyle("QuoteBody", fontName=font, fontSize=9, leading=14)
    small = ParagraphStyle("QuoteSmall", fontName=font, fontSize=8, leading=11)
    story = [
        Paragraph("报价单", title),
        Paragraph(f"报价单号：{escape(quote['报价单号'])}　报价日期：{escape(quote['报价日期'])}", body),
        Paragraph(f"客户名称：{escape(quote['客户名称'])}　联系人：{escape(quote['联系人'])}　联系电话：{escape(quote['联系电话'])}", body),
        Paragraph(f"报价有效期至：{escape(quote['有效期至'] or '未设置')}　税率：{escape(quote['税率(%)'])}%", body),
        Spacer(1, 10),
    ]
    rows = [[
        Paragraph("序号", small), Paragraph("项目名称", small), Paragraph("规格型号", small),
        Paragraph("单位", small), Paragraph("数量", small), Paragraph("单价（元）", small),
        Paragraph("金额（元）", small),
    ]]
    for index, item in enumerate(quote["明细"], start=1):
        amount = Decimal(item["数量"]) * Decimal(item["单价"])
        rows.append([
            str(index), Paragraph(escape(item["项目名称"]), small),
            Paragraph(escape(item["规格型号"]), small), item["单位"],
            item["数量"], money_text(Decimal(item["单价"])), money_text(amount),
        ])
    table = Table(rows, colWidths=[34, 112, 92, 42, 48, 75, 75], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8A929B")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 12)])
    totals = calculate_totals(quote)
    total_rows = [
        [Paragraph("未税小计", body), Paragraph(f"¥ {money_text(totals['subtotal'])}", body)],
        [Paragraph(f"税额（{escape(quote['税率(%)'])}%）", body), Paragraph(f"¥ {money_text(totals['tax'])}", body)],
        [Paragraph("含税总计", body), Paragraph(f"¥ {money_text(totals['total'])}", body)],
    ]
    total_table = Table(total_rows, colWidths=[100, 120], hAlign="RIGHT")
    total_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([total_table, Spacer(1, 18)])
    if quote["备注"]:
        story.append(Paragraph(f"备注：{escape(quote['备注'])}", body))
    story.extend([
        Spacer(1, 26),
        Paragraph("客户确认：____________________　　报价方盖章：____________________", body),
        Spacer(1, 8),
        Paragraph("本报价单由本地软件生成，请核对商品、数量、税率及有效期后再发送。", small),
    ])
    SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=28, leftMargin=28,
        topMargin=32, bottomMargin=32, title=f"报价单 {quote['报价单号']}",
    ).build(story)


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "quotations.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("报价单生成器｜大陆离线版")
        root.geometry("1120x720")
        self.store = QuoteStore(default_data_path())
        self.current_number = None
        self.items = []
        self.vars = {field: tk.StringVar() for field in QUOTE_FIELDS}
        self.vars["报价日期"].set(date.today().isoformat())
        self.vars["有效期至"].set(date.today().isoformat())
        self.vars["税率(%)"].set("13")
        self.vars["报价单号"].set(next_quote_number(self.store.quotes))
        form = tk.LabelFrame(root, text="报价单信息")
        form.pack(fill="x", padx=10, pady=8)
        labels = [
            ("报价单号", 0, 0), ("客户名称", 0, 2), ("联系人", 0, 4),
            ("联系电话", 1, 0), ("报价日期", 1, 2), ("有效期至", 1, 4),
            ("税率(%)", 2, 0), ("备注", 2, 2),
        ]
        for label, row, col in labels:
            tk.Label(form, text=label).grid(row=row, column=col, padx=5, pady=5, sticky="e")
            width = 26 if label == "备注" else 20
            tk.Entry(form, textvariable=self.vars[label], width=width).grid(row=row, column=col + 1, padx=5, pady=5, sticky="w")
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x", padx=10, pady=4)
        actions = [
            ("新建报价", self.new_quote), ("添加明细", self.add_item),
            ("删除明细", self.remove_item), ("保存报价", self.save_quote),
            ("导出 PDF", self.export_pdf), ("导入 CSV", self.import_csv),
            ("导出 CSV", self.export_csv), ("备份", self.backup),
            ("恢复备份", self.restore), ("删除报价", self.delete_quote),
        ]
        for label, command in actions:
            tk.Button(toolbar, text=label, command=command).pack(side="left", padx=2)
        self.tree = ttk.Treeview(root, columns=ITEM_FIELDS + ["金额"], show="headings", height=16)
        widths = [180, 130, 60, 70, 90, 170, 100]
        for field, width in zip(ITEM_FIELDS + ["金额"], widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)
        bottom = tk.Frame(root)
        bottom.pack(fill="x", padx=10, pady=8)
        self.saved = tk.StringVar()
        tk.Label(bottom, text="已保存报价单：").pack(side="left")
        self.selector = ttk.Combobox(bottom, textvariable=self.saved, state="readonly", width=28)
        self.selector.pack(side="left")
        self.selector.bind("<<ComboboxSelected>>", self.load_selected)
        self.summary = tk.StringVar()
        tk.Label(bottom, textvariable=self.summary, anchor="e").pack(side="right", fill="x", expand=True)
        self.refresh_saved()
        self.refresh_items()

    def collect_quote(self):
        return normalize_quote({**{field: self.vars[field].get() for field in QUOTE_FIELDS}, "明细": self.items})

    def set_quote(self, quote):
        for field in QUOTE_FIELDS:
            self.vars[field].set(quote[field])
        self.items = [dict(item) for item in quote["明细"]]
        self.current_number = quote["报价单号"]
        self.refresh_items()

    def refresh_saved(self):
        values = [q["报价单号"] for q in self.store.quotes]
        self.selector["values"] = values
        self.saved.set(self.current_number if self.current_number in values else "")

    def refresh_items(self):
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.items):
            amount = Decimal(item["数量"]) * Decimal(item["单价"])
            self.tree.insert("", "end", iid=str(index), values=[
                item["项目名称"], item["规格型号"], item["单位"], item["数量"],
                money_text(Decimal(item["单价"])), item["项目备注"], money_text(amount),
            ])
        try:
            quote = {**{field: self.vars[field].get() for field in QUOTE_FIELDS}, "明细": self.items}
            totals = calculate_totals(quote)
            self.summary.set(f"未税小计：¥{money_text(totals['subtotal'])}　税额：¥{money_text(totals['tax'])}　含税总计：¥{money_text(totals['total'])}")
        except ValueError:
            self.summary.set("请完善报价单信息和明细")

    def new_quote(self):
        self.current_number = None
        for field in QUOTE_FIELDS:
            self.vars[field].set("")
        self.vars["报价单号"].set(next_quote_number(self.store.quotes))
        self.vars["报价日期"].set(date.today().isoformat())
        self.vars["有效期至"].set(date.today().isoformat())
        self.vars["税率(%)"].set("13")
        self.items = []
        self.saved.set("")
        self.refresh_items()

    def add_item(self):
        win = tk.Toplevel(self.root)
        win.title("添加报价明细")
        fields = ["项目名称", "规格型号", "单位", "数量", "单价", "项目备注"]
        values = {field: tk.StringVar() for field in fields}
        values["单位"].set("件")
        values["数量"].set("1")
        values["单价"].set("0")
        for row, field in enumerate(fields):
            tk.Label(win, text=field).grid(row=row, column=0, padx=8, pady=5, sticky="e")
            tk.Entry(win, textvariable=values[field], width=34).grid(row=row, column=1, padx=8, pady=5)
        def save():
            try:
                item = normalize_item({field: values[field].get() for field in fields})
                self.items.append(item)
                self.refresh_items()
                win.destroy()
            except ValueError as exc:
                messagebox.showerror("明细无效", str(exc), parent=win)
        tk.Button(win, text="添加", command=save).grid(row=len(fields), column=0, columnspan=2, pady=8)

    def remove_item(self):
        selected = self.tree.selection()
        if selected:
            self.items.pop(int(selected[0]))
            self.refresh_items()

    def save_quote(self):
        try:
            quote = self.collect_quote()
            if self.current_number:
                self.store.update(self.current_number, quote)
            else:
                self.store.add(quote)
            self.current_number = quote["报价单号"]
            self.refresh_saved()
            messagebox.showinfo("保存完成", "报价单已保存到本机")
        except (ValueError, OSError) as exc:
            messagebox.showerror("保存失败", str(exc))

    def load_selected(self, _event=None):
        number = self.saved.get()
        quote = next((q for q in self.store.quotes if q["报价单号"] == number), None)
        if quote:
            self.set_quote(quote)

    def delete_quote(self):
        if not self.current_number:
            messagebox.showinfo("提示", "请先选择或保存一张报价单")
            return
        if messagebox.askyesno("确认删除", f"确定删除 {self.current_number}？"):
            self.store.delete(self.current_number)
            self.new_quote()
            self.refresh_saved()

    def export_pdf(self):
        try:
            quote = self.collect_quote()
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf", initialfile=f"{quote['报价单号']}.pdf",
                filetypes=[("PDF 文件", "*.pdf")],
            )
            if path:
                export_quote_pdf(quote, path)
                messagebox.showinfo("导出完成", f"PDF 已保存：{path}")
        except (ValueError, OSError) as exc:
            messagebox.showerror("导出失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh_saved()
                messagebox.showinfo("导入完成", f"成功导入 {count} 张报价单")
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
        if path and messagebox.askyesno("确认恢复", "恢复会替换本机全部报价单，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.new_quote()
                self.refresh_saved()
                messagebox.showinfo("恢复完成", "报价单数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    sample = normalize_quote({
        "报价单号": "BJ-TEST-001", "客户名称": "测试客户",
        "报价日期": date.today().isoformat(), "有效期至": "2099-12-31",
        "税率(%)": "13",
        "明细": [{"项目名称": "测试服务", "单位": "项", "数量": "2", "单价": "100"}],
    })
    assert calculate_totals(sample)["total"] == Decimal("226.00")
    assert PRODUCT == "报价单生成器"
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "self-test.pdf"
        export_quote_pdf(sample, output)
        assert output.read_bytes().startswith(b"%PDF-")
    print("SELF_TEST_OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
