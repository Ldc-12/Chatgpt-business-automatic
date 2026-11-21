"""Offline store receiving inspection and supplier discrepancy ledger."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-store-receiving"
VERSION = 1
MAX_LINES = 200000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_QUANTITY = Decimal("999999999.999")
MAX_MONEY = Decimal("999999999999.99")
QUANTITY_UNIT = Decimal("0.001")
CENT = Decimal("0.01")

LINE_FIELDS = [
    "明细编号", "收货单号", "采购单号", "供应商", "到货日期", "经办人", "备注",
    "SKU", "商品名称", "订购数量", "实收数量", "破损数量", "拒收数量",
    "采购单价", "差异原因", "差异处理", "处理备注",
]
REPORT_FIELDS = [
    "明细编号", "收货单号", "采购单号", "供应商", "到货日期", "SKU", "商品名称",
    "订购数量", "实收数量", "验收合格数量", "短缺数量", "超收数量",
    "破损数量", "拒收数量", "采购单价", "验收金额", "差异金额",
    "差异状态", "差异原因", "差异处理", "处理备注",
]
SUPPLIER_SUMMARY_FIELDS = [
    "供应商", "统计开始日期", "统计结束日期", "收货单数", "收货明细数", "差异明细数", "待处理差异",
    "短缺数量", "超收数量", "破损数量", "拒收数量", "验收金额", "差异金额", "待处理差异金额",
]
RESOLUTION_STATES = ("待处理", "已补发", "已折让", "已退款", "已关闭", "无需处理")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decimal_text(value, places=3):
    quantum = QUANTITY_UNIT if places == 3 else CENT
    rendered = format(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP), "f")
    if places == 2:
        return rendered
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def parse_decimal(value, field, *, minimum=Decimal("0"), maximum=MAX_QUANTITY, places=3):
    text = "" if value is None else str(value).strip()
    text = text.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "").replace("元", "").strip()
    if len(text) > 40:
        raise ValueError(f"{field}超出可接受长度")
    try:
        number = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效数字") from None
    if not number.is_finite() or number < minimum or number > maximum:
        raise ValueError(f"{field}必须在 {minimum} 至 {maximum} 之间")
    quantum = QUANTITY_UNIT if places == 3 else CENT
    try:
        return format(number.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    except InvalidOperation:
        raise ValueError(f"{field}精度超出可接受范围") from None


def parse_date(value, field, *, today=None):
    try:
        parsed = date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None
    if parsed > (today or date.today()):
        raise ValueError(f"{field}不能晚于今天")
    return parsed.isoformat()


def csv_safe(value):
    text = "" if value is None else str(value)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


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


def _identifier(value, field, *, required=True):
    text = str(value or "").strip()
    if not text and not required:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", text):
        raise ValueError(f"{field}只能包含 1–64 位字母、数字、点、下划线或连字符")
    return text


def _bounded_text(value, field, maximum, *, required=False):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field}不能为空")
    if len(text) > maximum or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"{field}长度或字符不符合要求")
    return text


def normalize_line(row, *, today=None):
    if not isinstance(row, dict):
        raise ValueError("收货明细必须是对象")
    line_id = _identifier(row.get("明细编号") or ("R" + uuid.uuid4().hex[:20].upper()), "明细编号")
    receipt_id = _identifier(row.get("收货单号"), "收货单号")
    purchase_id = _identifier(row.get("采购单号"), "采购单号", required=False)
    supplier = _bounded_text(row.get("供应商"), "供应商", 80, required=True)
    receipt_date = parse_date(row.get("到货日期", ""), "到货日期", today=today)
    operator = _bounded_text(row.get("经办人"), "经办人", 40)
    note = _bounded_text(row.get("备注"), "备注", 500)
    sku = _identifier(row.get("SKU"), "SKU")
    name = _bounded_text(row.get("商品名称"), "商品名称", 80, required=True)

    ordered = parse_decimal(row.get("订购数量"), "订购数量", minimum=QUANTITY_UNIT)
    received = parse_decimal(row.get("实收数量"), "实收数量")
    damaged = parse_decimal(row.get("破损数量"), "破损数量")
    rejected = parse_decimal(row.get("拒收数量"), "拒收数量")
    if Decimal(damaged) + Decimal(rejected) > Decimal(received):
        raise ValueError("破损数量与拒收数量之和不能超过实收数量")
    price = parse_decimal(row.get("采购单价"), "采购单价", maximum=MAX_MONEY, places=2)

    shortage = max(Decimal(ordered) - Decimal(received), Decimal("0"))
    overage = max(Decimal(received) - Decimal(ordered), Decimal("0"))
    has_difference = any(value > 0 for value in (shortage, overage, Decimal(damaged), Decimal(rejected)))
    reason = _bounded_text(row.get("差异原因"), "差异原因", 200)
    state = str(row.get("差异处理", "") or "").strip()
    resolution_note = _bounded_text(row.get("处理备注"), "处理备注", 500)

    if has_difference:
        if not reason:
            raise ValueError("存在短缺、超收、破损或拒收时必须填写差异原因")
        if not state:
            state = "待处理"
        if state not in RESOLUTION_STATES[:-1]:
            raise ValueError("差异处理状态无效：有差异的明细必须选择待处理、已补发、已折让、已退款或已关闭")
    else:
        if state not in ("", "无需处理", "已关闭"):
            raise ValueError("没有数量差异的明细不能设置差异处理状态")
        state = "已关闭" if state == "已关闭" else "无需处理"

    return {
        "明细编号": line_id,
        "收货单号": receipt_id,
        "采购单号": purchase_id,
        "供应商": supplier,
        "到货日期": receipt_date,
        "经办人": operator,
        "备注": note,
        "SKU": sku,
        "商品名称": name,
        "订购数量": ordered,
        "实收数量": received,
        "破损数量": damaged,
        "拒收数量": rejected,
        "采购单价": price,
        "差异原因": reason,
        "差异处理": state,
        "处理备注": resolution_note,
    }


def validate_state(raw_lines):
    if not isinstance(raw_lines, list) or len(raw_lines) > MAX_LINES:
        raise ValueError(f"收货明细缺失或超过 {MAX_LINES} 条安全上限")
    lines = [normalize_line(row) for row in raw_lines]
    ids = [row["明细编号"].casefold() for row in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("收货明细编号重复（不区分大小写）")

    headers = {}
    for row in lines:
        key = row["收货单号"].casefold()
        header = (
            row["采购单号"].casefold(),
            row["供应商"].casefold(),
            row["到货日期"],
            row["经办人"].casefold(),
        )
        previous = headers.setdefault(key, header)
        if previous != header:
            raise ValueError("同一收货单号的采购单号、供应商、到货日期和经办人必须一致")
    return lines


def read_csv_rows(path):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV 文件超过 25 MiB 安全上限")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != LINE_FIELDS:
            raise ValueError("CSV 表头不匹配，请使用本软件导出的模板")
        rows = list(reader)
    if len(rows) > MAX_LINES:
        raise ValueError(f"CSV 行数超过 {MAX_LINES} 条安全上限")
    return rows


class ReceivingStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        self.load()

    @staticmethod
    def _payload(lines):
        body = {
            "格式": FORMAT,
            "版本": VERSION,
            "收货明细": json.loads(canonical(lines)),
        }
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("收货台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("收货台账 SHA256 校验失败")
        return validate_state(body.get("收货明细"))

    def load(self):
        if not self.path.exists():
            self.lines = []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("收货台账超过 100 MiB 安全上限")
        self.lines = self.decode(json.loads(self.path.read_text(encoding="utf-8")))

    def _commit(self, lines):
        normalized = validate_state(lines)
        data = canonical(self._payload(normalized)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("收货台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.lines = normalized

    def add_line(self, row):
        line = normalize_line(row)
        if any(item["明细编号"].casefold() == line["明细编号"].casefold() for item in self.lines):
            raise ValueError("收货明细编号已存在")
        if len(self.lines) >= MAX_LINES:
            raise ValueError(f"收货明细不能超过 {MAX_LINES} 条")
        self._commit(self.lines + [line])
        return line["明细编号"]

    def update_line(self, line_id, row):
        current = next((item for item in self.lines if item["明细编号"].casefold() == str(line_id).casefold()), None)
        if current is None:
            raise ValueError("未找到要修改的收货明细")
        line = normalize_line(row)
        if line["明细编号"].casefold() != current["明细编号"].casefold():
            raise ValueError("已有收货明细不能直接修改明细编号")
        updated = [
            line if item["明细编号"].casefold() == current["明细编号"].casefold() else item
            for item in self.lines
        ]
        self._commit(updated)
        return line["明细编号"]

    def search_lines(self, keyword=""):
        needle = str(keyword or "").strip().casefold()
        if not needle:
            return list(self.lines)
        fields = ("明细编号", "收货单号", "采购单号", "供应商", "SKU", "商品名称", "差异原因", "差异处理")
        return [
            row for row in self.lines
            if needle in " ".join(str(row.get(field, "")) for field in fields).casefold()
        ]

    @staticmethod
    def calculate(row):
        ordered = Decimal(row["订购数量"])
        received = Decimal(row["实收数量"])
        damaged = Decimal(row["破损数量"])
        rejected = Decimal(row["拒收数量"])
        price = Decimal(row["采购单价"])
        accepted = max(min(received, ordered) - damaged - rejected, Decimal("0"))
        shortage = max(ordered - received, Decimal("0"))
        overage = max(received - ordered, Decimal("0"))
        difference_quantity = shortage + overage + damaged + rejected
        return {
            **row,
            "验收合格数量": decimal_text(accepted),
            "短缺数量": decimal_text(shortage),
            "超收数量": decimal_text(overage),
            "验收金额": decimal_text(accepted * price, places=2),
            "差异金额": decimal_text(difference_quantity * price, places=2),
            "差异状态": "有差异" if difference_quantity > 0 else "无差异",
        }

    def report_rows(self):
        return [self.calculate(row) for row in self.lines]

    def difference_rows(self):
        return [row for row in self.report_rows() if row["差异状态"] == "有差异"]

    def summary(self):
        rows = self.report_rows()
        differences = [row for row in rows if row["差异状态"] == "有差异"]
        total = lambda field: sum((Decimal(row[field]) for row in rows), Decimal("0"))
        return {
            "收货单数": len({row["收货单号"].casefold() for row in self.lines}),
            "收货明细数": len(rows),
            "差异明细数": len(differences),
            "待处理差异": sum(row["差异处理"] == "待处理" for row in differences),
            "短缺数量": decimal_text(total("短缺数量")),
            "超收数量": decimal_text(total("超收数量")),
            "破损数量": decimal_text(total("破损数量")),
            "拒收数量": decimal_text(total("拒收数量")),
            "验收金额": decimal_text(total("验收金额"), places=2),
            "差异金额": decimal_text(sum((Decimal(row["差异金额"]) for row in differences), Decimal("0")), places=2),
        }

    def supplier_summary_rows(self, start_date=None, end_date=None):
        """Aggregate supplier exposure within an inclusive arrival-date range.

        Blank boundaries mean unbounded. The normalized boundaries are included
        in each result row so exported statements retain their reporting period.
        """
        start_text = parse_date(start_date, "统计开始日期") if str(start_date or "").strip() else ""
        end_text = parse_date(end_date, "统计结束日期") if str(end_date or "").strip() else ""
        start_day = date.fromisoformat(start_text) if start_text else None
        end_day = date.fromisoformat(end_text) if end_text else None
        if start_day and end_day and start_day > end_day:
            raise ValueError("统计开始日期不能晚于统计结束日期")

        groups = {}
        quantity_fields = ("短缺数量", "超收数量", "破损数量", "拒收数量")
        for row in self.report_rows():
            arrival_day = date.fromisoformat(row["到货日期"])
            if start_day and arrival_day < start_day:
                continue
            if end_day and arrival_day > end_day:
                continue
            key = row["供应商"].casefold()
            group = groups.get(key)
            if group is None:
                group = {
                    "供应商": row["供应商"],
                    "_收货单号": set(),
                    "收货明细数": 0,
                    "差异明细数": 0,
                    "待处理差异": 0,
                    "短缺数量": Decimal("0"),
                    "超收数量": Decimal("0"),
                    "破损数量": Decimal("0"),
                    "拒收数量": Decimal("0"),
                    "验收金额": Decimal("0"),
                    "差异金额": Decimal("0"),
                    "待处理差异金额": Decimal("0"),
                }
                groups[key] = group

            group["_收货单号"].add(row["收货单号"].casefold())
            group["收货明细数"] += 1
            for field in quantity_fields:
                group[field] += Decimal(row[field])
            group["验收金额"] += Decimal(row["验收金额"])

            if row["差异状态"] == "有差异":
                group["差异明细数"] += 1
                group["差异金额"] += Decimal(row["差异金额"])
                if row["差异处理"] == "待处理":
                    group["待处理差异"] += 1
                    group["待处理差异金额"] += Decimal(row["差异金额"])

        result = []
        for group in groups.values():
            result.append({
                "供应商": group["供应商"],
                "统计开始日期": start_text or "不限",
                "统计结束日期": end_text or "不限",
                "收货单数": len(group["_收货单号"]),
                "收货明细数": group["收货明细数"],
                "差异明细数": group["差异明细数"],
                "待处理差异": group["待处理差异"],
                "短缺数量": decimal_text(group["短缺数量"]),
                "超收数量": decimal_text(group["超收数量"]),
                "破损数量": decimal_text(group["破损数量"]),
                "拒收数量": decimal_text(group["拒收数量"]),
                "验收金额": decimal_text(group["验收金额"], places=2),
                "差异金额": decimal_text(group["差异金额"], places=2),
                "待处理差异金额": decimal_text(group["待处理差异金额"], places=2),
            })
        return sorted(result, key=lambda row: row["供应商"].casefold())

    @staticmethod
    def _write_csv(path, fields, rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe(row.get(field, "")) for field in fields})
        atomic_write(path, buffer.getvalue().encode("utf-8-sig"))

    def import_csv(self, path):
        incoming = [normalize_line(row) for row in read_csv_rows(path)]
        existing = {row["明细编号"].casefold() for row in self.lines}
        keys = [row["明细编号"].casefold() for row in incoming]
        if len(keys) != len(set(keys)) or existing.intersection(keys):
            raise ValueError("导入文件存在重复收货明细编号；本次导入已取消")
        if len(self.lines) + len(incoming) > MAX_LINES:
            raise ValueError(f"收货明细不能超过 {MAX_LINES} 条")
        if incoming:
            self._commit(self.lines + incoming)
        return len(incoming)

    def export_csv(self, path):
        self._write_csv(path, LINE_FIELDS, self.lines)

    def export_difference_csv(self, path):
        self._write_csv(path, REPORT_FIELDS, self.difference_rows())

    def export_supplier_summary_csv(self, path, start_date=None, end_date=None):
        self._write_csv(
            path,
            SUPPLIER_SUMMARY_FIELDS,
            self.supplier_summary_rows(start_date=start_date, end_date=end_date),
        )

    def backup(self, path):
        data = canonical(self._payload(self.lines)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)
        return hashlib.sha256(data).hexdigest()

    def restore(self, path):
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件不存在或超过 100 MiB 安全上限")
        lines = self.decode(json.loads(source.read_text(encoding="utf-8")))
        self._commit(lines)
        return len(lines)


def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        store = ReceivingStore(Path(directory) / "receiving.json")
        store.add_line({
            "收货单号": "RCV-DEMO-001", "采购单号": "PO-DEMO-001",
            "供应商": "演示供应商", "到货日期": date.today().isoformat(),
            "SKU": "DEMO-001", "商品名称": "演示商品",
            "订购数量": "10", "实收数量": "9", "破损数量": "0",
            "拒收数量": "0", "采购单价": "2.50", "差异原因": "少货",
        })
        report = store.report_rows()[0]
        assert report["短缺数量"] == "1"
        assert report["验收金额"] == "22.50"
        assert store.summary()["待处理差异"] == 1


if __name__ == "__main__":
    self_test()
    print("SELF_TEST_OK")
