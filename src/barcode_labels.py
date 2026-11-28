"""Offline product catalog, Code128 label printing, safe CSV and checksummed backups."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from tempfile import TemporaryDirectory

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.code128 import Code128

FORMAT = "mainland-barcode-labels"
VERSION = 1
MAX_ITEMS = 50000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_LABELS_PER_EXPORT = 20000
MAX_PRICE = Decimal("99999999.99")
CENT = Decimal("0.01")

LINE_FIELDS = ["SKU", "商品名称", "规格", "价格", "条码", "打印数量"]
TEXT_FIELDS = ("SKU", "商品名称", "规格", "条码")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def atomic_write(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def csv_safe(value):
    text = "" if value is None else str(value)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _text(value, field, maximum, *, required=False):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field}不能为空")
    if len(text) > maximum or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"{field}长度或字符不符合要求")
    return text


def _price(value):
    text = str(value or "").strip().replace(",", "").replace("，", "").replace("￥", "").replace("¥", "").replace("元", "")
    if len(text) > 40:
        raise ValueError("价格超出可接受长度")
    try:
        number = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError("价格必须是有效数字") from None
    if not number.is_finite() or number < 0 or number > MAX_PRICE:
        raise ValueError("价格必须在 0 至 99999999.99 元之间")
    try:
        return format(number.quantize(CENT, rounding=ROUND_HALF_UP), "f")
    except InvalidOperation:
        raise ValueError("价格精度超出可接受范围") from None


def normalize_item(row):
    if not isinstance(row, dict):
        raise ValueError("商品记录必须是对象")
    sku = _text(row.get("SKU"), "SKU", 18, required=True)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,17}", sku):
        raise ValueError("SKU 只能使用 1–18 位字母、数字、点、下划线或连字符，且必须以字母或数字开头")
    name = _text(row.get("商品名称"), "商品名称", 80, required=True)
    spec = _text(row.get("规格"), "规格", 60)
    barcode = _text(row.get("条码") or sku, "条码", 18, required=True)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._/-]{0,17}", barcode):
        raise ValueError("条码仅支持 1–18 位可打印 ASCII 字符，且必须以字母或数字开头")
    quantity_text = str(row.get("打印数量", "1") or "1").strip()
    if not re.fullmatch(r"\d{1,5}", quantity_text):
        raise ValueError("打印数量必须是 1–9999 的整数")
    quantity = int(quantity_text)
    if quantity < 1 or quantity > 9999:
        raise ValueError("打印数量必须在 1–9999 之间")
    return {
        "SKU": sku,
        "商品名称": name,
        "规格": spec,
        "价格": _price(row.get("价格")),
        "条码": barcode,
        "打印数量": str(quantity),
    }


def validate_items(raw_items):
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        raise ValueError(f"商品记录缺失或超过 {MAX_ITEMS} 条安全上限")
    items = [normalize_item(row) for row in raw_items]
    skus = [row["SKU"].casefold() for row in items]
    barcodes = [row["条码"].casefold() for row in items]
    if len(skus) != len(set(skus)):
        raise ValueError("SKU 重复（不区分大小写）")
    if len(barcodes) != len(set(barcodes)):
        raise ValueError("条码重复（不区分大小写）")
    return items


def read_csv_rows(path):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV 文件超过 25 MiB 安全上限")
    raw = source.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV 编码无法识别，请使用 UTF-8 或 GB18030")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != LINE_FIELDS:
        raise ValueError("CSV 表头不匹配，请使用本软件导出的模板")
    rows = list(reader)
    if len(rows) > MAX_ITEMS:
        raise ValueError(f"CSV 行数超过 {MAX_ITEMS} 条安全上限")
    return rows


class BarcodeLabelStore:
    def __init__(self, path):
        self.path = Path(path)
        self.items = []
        self.load()

    @staticmethod
    def _payload(items):
        body = {
            "格式": FORMAT,
            "版本": VERSION,
            "商品": json.loads(canonical(items)),
        }
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("商品台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("商品台账 SHA256 校验失败")
        return validate_items(body.get("商品"))

    def load(self):
        if not self.path.exists():
            self.items = []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("商品台账超过 100 MiB 安全上限")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = self.decode(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"商品台账无法读取，原文件未修改：{exc}") from exc

    def _commit(self, items):
        normalized = validate_items(items)
        data = canonical(self._payload(normalized)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("商品台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.items = normalized

    def add_item(self, row):
        item = normalize_item(row)
        if any(existing["SKU"].casefold() == item["SKU"].casefold() for existing in self.items):
            raise ValueError("SKU 已存在")
        if any(existing["条码"].casefold() == item["条码"].casefold() for existing in self.items):
            raise ValueError("条码已存在")
        if len(self.items) >= MAX_ITEMS:
            raise ValueError(f"商品记录不能超过 {MAX_ITEMS} 条")
        self._commit(self.items + [item])
        return item["SKU"]

    def update_item(self, old_sku, row):
        current = next((item for item in self.items if item["SKU"].casefold() == str(old_sku).casefold()), None)
        if current is None:
            raise ValueError("未找到要修改的商品")
        item = normalize_item(row)
        updated = [
            item if existing["SKU"].casefold() == current["SKU"].casefold() else existing
            for existing in self.items
        ]
        self._commit(updated)
        return item["SKU"]

    def delete_item(self, sku):
        remaining = [item for item in self.items if item["SKU"].casefold() != str(sku).casefold()]
        if len(remaining) == len(self.items):
            raise ValueError("未找到要删除的商品")
        self._commit(remaining)

    def search_items(self, keyword=""):
        needle = str(keyword or "").strip().casefold()
        if not needle:
            return list(self.items)
        return [
            item for item in self.items
            if needle in " ".join(str(item.get(field, "")) for field in LINE_FIELDS).casefold()
        ]

    def export_csv(self, path):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=LINE_FIELDS)
        writer.writeheader()
        for item in self.items:
            writer.writerow({
                field: csv_safe(item[field]) if field in TEXT_FIELDS else item[field]
                for field in LINE_FIELDS
            })
        atomic_write(path, output.getvalue().encode("utf-8-sig"))

    def import_csv(self, path):
        incoming = validate_items(read_csv_rows(path))
        existing_skus = {item["SKU"].casefold() for item in self.items}
        existing_barcodes = {item["条码"].casefold() for item in self.items}
        duplicates = [
            item["SKU"] for item in incoming
            if item["SKU"].casefold() in existing_skus
            or item["条码"].casefold() in existing_barcodes
        ]
        if duplicates:
            raise ValueError("导入包含已存在 SKU 或条码，未导入任何数据：" + "、".join(duplicates[:20]))
        if len(self.items) + len(incoming) > MAX_ITEMS:
            raise ValueError(f"导入后商品记录不能超过 {MAX_ITEMS} 条")
        self._commit(self.items + incoming)
        return len(incoming)

    def backup(self, path):
        body = {
            "format": FORMAT,
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "items": self.items,
        }
        payload = {**body, "sha256": hashlib.sha256(canonical(body)).hexdigest()}
        data = canonical(payload) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件不存在或超过 100 MiB 安全上限")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"备份文件无法读取：{exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != FORMAT or payload.get("version") != VERSION:
            raise ValueError("备份文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "sha256"}
        if payload.get("sha256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("备份 SHA256 校验失败")
        items = validate_items(body.get("items"))
        self._commit(items)
        return len(items)


def export_labels_pdf(items, path):
    normalized = validate_items(items)
    if not normalized:
        raise ValueError("没有可打印的商品")
    label_count = sum(int(item["打印数量"]) for item in normalized)
    if label_count > MAX_LABELS_PER_EXPORT:
        raise ValueError(f"单次最多生成 {MAX_LABELS_PER_EXPORT} 张价签，请分批导出")

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass
    font = "STSong-Light"
    page_width, page_height = A4
    columns, rows_per_page = 3, 8
    margin, gap = 7 * mm, 2 * mm
    label_width = (page_width - margin * 2 - gap * (columns - 1)) / columns
    label_height = (page_height - margin * 2 - gap * (rows_per_page - 1)) / rows_per_page
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(target), pagesize=A4, pageCompression=1)
    pdf.setTitle("门店条码与价签批量打印")
    pdf.setSubject("本地生成的商品 Code128 条码与价签")

    index = 0
    for item in normalized:
        barcode = Code128(item["条码"], barHeight=7 * mm, barWidth=0.18 * mm, humanReadable=False)
        if barcode.width > label_width - 8 * mm:
            raise ValueError(f"条码 {item['条码']} 过宽，无法放入价签")
        for _ in range(int(item["打印数量"])):
            slot = index % (columns * rows_per_page)
            if index and slot == 0:
                pdf.showPage()
            column, row = slot % columns, slot // columns
            x = margin + column * (label_width + gap)
            y = page_height - margin - label_height - row * (label_height + gap)

            pdf.setStrokeColor(colors.HexColor("#B8BEC6"))
            pdf.setLineWidth(0.45)
            pdf.rect(x, y, label_width, label_height)
            pdf.setFillColor(colors.black)
            pdf.setFont(font, 7)
            name = item["商品名称"]
            pdf.drawString(x + 3 * mm, y + label_height - 5.5 * mm, name[:22] + ("…" if len(name) > 22 else ""))
            if item["规格"]:
                pdf.setFont(font, 5.5)
                pdf.drawString(x + 3 * mm, y + label_height - 10 * mm, item["规格"][:28])
            pdf.setFont(font, 8)
            pdf.drawString(x + 3 * mm, y + label_height - 15 * mm, f"售价：¥{item['价格']}")
            barcode.drawOn(pdf, x + (label_width - barcode.width) / 2, y + 5 * mm)
            pdf.setFont("Helvetica", 5)
            pdf.drawCentredString(x + label_width / 2, y + 2.5 * mm, item["条码"])
            index += 1

    pdf.save()
    if not target.is_file() or target.stat().st_size < 1000:
        raise ValueError("价签 PDF 生成失败")
    return label_count


def self_test():
    sample = {
        "SKU": "SKU-001",
        "商品名称": "测试商品",
        "规格": "500g",
        "价格": "12.5",
        "条码": "SKU-001",
        "打印数量": "2",
    }
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = BarcodeLabelStore(root / "items.json")
        store.add_item(sample)
        csv_path = root / "items.csv"
        store.export_csv(csv_path)
        imported = BarcodeLabelStore(root / "imported.json")
        imported.import_csv(csv_path)
        backup = root / "backup.json"
        imported.backup(backup)
        restored = BarcodeLabelStore(root / "restored.json")
        restored.restore(backup)
        pdf_path = root / "labels.pdf"
        export_labels_pdf(restored.items, pdf_path)
        if len(restored.items) != 1 or not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("barcode label self-test failed")
    return True
