"""Offline purchase-order and partial-delivery tracker for small stores."""
from __future__ import annotations
import csv, hashlib, io, json, os, re, tempfile, uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-store-purchase-orders"
VERSION = 1
MAX_LINES = 100000
MAX_RECEIPTS = 200000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_QUANTITY = Decimal("999999999.999")
MAX_MONEY = Decimal("999999999999.99")
QUANTITY_UNIT = Decimal("0.001")
CENT = Decimal("0.01")
LINE_FIELDS = ["明细编号", "采购单号", "供应商", "下单日期", "预计到货日期", "采购员", "SKU", "商品名称", "订购数量", "采购单价", "备注"]
RECEIPT_FIELDS = ["到货记录编号", "明细编号", "到货日期", "合格数量", "破损数量", "拒收数量", "处理备注"]
REPORT_FIELDS = ["明细编号", "采购单号", "供应商", "下单日期", "预计到货日期", "采购员", "SKU", "商品名称", "订购数量", "到货总量", "合格到货", "破损数量", "拒收数量", "剩余待到货", "超出订购", "采购单价", "已验收金额", "待到货金额", "最后到货日期", "状态", "备注"]
SUPPLIER_SUMMARY_FIELDS = ["供应商", "采购单数", "采购明细数", "逾期未齐明细", "部分到货明细", "待到货数量", "待到货金额", "合格到货数量", "破损数量", "拒收数量", "已验收金额"]


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


def parse_date(value, field, *, today=None, allow_future=False):
    try:
        parsed = date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None
    if not allow_future and parsed > (today or date.today()):
        raise ValueError(f"{field}不能晚于今天")
    return parsed.isoformat()


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


def _is_formula_like_text(value):
    probe = str(value or "").lstrip(" \t\r\n")
    while probe.startswith("'"):
        probe = probe[1:]
    probe = probe.lstrip(" \t\r\n")
    return bool(probe) and probe[0] in ("=", "+", "-", "@")


def spreadsheet_safe_cell(value):
    text = "" if value is None else str(value)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    return "'" + text if _is_formula_like_text(text) else text


def restore_spreadsheet_safe_cell(value):
    text = "" if value is None else str(value)
    if text.startswith("'") and _is_formula_like_text(text[1:]):
        return text[1:]
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


def normalize_line(row, *, today=None):
    if not isinstance(row, dict):
        raise ValueError("采购明细必须是对象")
    line_id = _identifier(row.get("明细编号") or ("PO-LINE-" + uuid.uuid4().hex[:16].upper()), "明细编号")
    order_id = _identifier(row.get("采购单号"), "采购单号")
    supplier = _bounded_text(row.get("供应商"), "供应商", 80, required=True)
    order_date = parse_date(row.get("下单日期", ""), "下单日期", today=today)
    expected_date = parse_date(row.get("预计到货日期", ""), "预计到货日期", allow_future=True)
    if date.fromisoformat(expected_date) < date.fromisoformat(order_date):
        raise ValueError("预计到货日期不能早于下单日期")
    buyer = _bounded_text(row.get("采购员"), "采购员", 40)
    sku = _identifier(row.get("SKU"), "SKU")
    name = _bounded_text(row.get("商品名称"), "商品名称", 80, required=True)
    ordered = parse_decimal(row.get("订购数量"), "订购数量", minimum=QUANTITY_UNIT)
    price = parse_decimal(row.get("采购单价"), "采购单价", maximum=MAX_MONEY, places=2)
    note = _bounded_text(row.get("备注"), "备注", 500)
    return {"明细编号": line_id, "采购单号": order_id, "供应商": supplier, "下单日期": order_date, "预计到货日期": expected_date, "采购员": buyer, "SKU": sku, "商品名称": name, "订购数量": ordered, "采购单价": price, "备注": note}


def normalize_receipt(row, line_map, *, today=None):
    if not isinstance(row, dict):
        raise ValueError("到货记录必须是对象")
    receipt_id = _identifier(row.get("到货记录编号") or ("PO-RCV-" + uuid.uuid4().hex[:16].upper()), "到货记录编号")
    line_id = _identifier(row.get("明细编号"), "明细编号")
    line = line_map.get(line_id.casefold())
    if line is None:
        raise ValueError(f"到货记录引用了不存在的采购明细：{line_id}")
    receipt_date = parse_date(row.get("到货日期", ""), "到货日期", today=today)
    if date.fromisoformat(receipt_date) < date.fromisoformat(line["下单日期"]):
        raise ValueError("到货日期不能早于下单日期")
    good = parse_decimal(row.get("合格数量"), "合格数量")
    damaged = parse_decimal(row.get("破损数量"), "破损数量")
    rejected = parse_decimal(row.get("拒收数量"), "拒收数量")
    if Decimal(good) + Decimal(damaged) + Decimal(rejected) <= 0:
        raise ValueError("合格、破损和拒收数量之和必须大于 0")
    note = _bounded_text(row.get("处理备注"), "处理备注", 500)
    return {"到货记录编号": receipt_id, "明细编号": line["明细编号"], "到货日期": receipt_date, "合格数量": good, "破损数量": damaged, "拒收数量": rejected, "处理备注": note}


def validate_state(raw_lines, raw_receipts):
    if not isinstance(raw_lines, list) or len(raw_lines) > MAX_LINES:
        raise ValueError(f"采购明细缺失或超过 {MAX_LINES} 条安全上限")
    if not isinstance(raw_receipts, list) or len(raw_receipts) > MAX_RECEIPTS:
        raise ValueError(f"到货记录缺失或超过 {MAX_RECEIPTS} 条安全上限")
    lines = [normalize_line(row) for row in raw_lines]
    line_ids = [row["明细编号"].casefold() for row in lines]
    if len(line_ids) != len(set(line_ids)):
        raise ValueError("采购明细编号重复（不区分大小写）")
    line_map = {row["明细编号"].casefold(): row for row in lines}
    headers = {}
    for row in lines:
        key = row["采购单号"].casefold()
        header = (row["供应商"].casefold(), row["下单日期"], row["预计到货日期"], row["采购员"].casefold())
        previous = headers.setdefault(key, header)
        if previous != header:
            raise ValueError("同一采购单号的供应商、下单日期、预计到货日期和采购员必须一致")
    receipts = [normalize_receipt(row, line_map) for row in raw_receipts]
    receipt_ids = [row["到货记录编号"].casefold() for row in receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError("到货记录编号重复（不区分大小写）")
    totals = {}
    for row in receipts:
        key = row["明细编号"].casefold()
        totals[key] = totals.get(key, Decimal("0")) + sum((Decimal(row[field]) for field in ("合格数量", "破损数量", "拒收数量")), Decimal("0"))
        if totals[key] > MAX_QUANTITY:
            raise ValueError("同一采购明细累计到货数量超过安全上限")
    return lines, receipts


def read_csv_rows(path, expected_fields, max_rows):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV 文件超过 25 MiB 安全上限")
    raw = source.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = raw.decode("gb18030")
        except UnicodeDecodeError:
            raise ValueError("CSV 编码不受支持，请另存为 UTF-8 或 GB18030") from None
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if reader.fieldnames != expected_fields:
        raise ValueError("CSV 表头不匹配，请使用本软件导出的模板")
    rows = []
    for line_number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV 第 {line_number} 行的列数不匹配")
        if not any(str(value or "").strip() for value in row.values()):
            continue
        rows.append({key: restore_spreadsheet_safe_cell(value) for key, value in row.items()})
        if len(rows) > max_rows:
            raise ValueError("CSV 行数超过安全上限")
    return rows


class PurchaseOrderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        self.receipts = []
        self.load()

    @staticmethod
    def _payload(lines, receipts):
        body = {"格式": FORMAT, "版本": VERSION, "采购明细": json.loads(canonical(lines)), "到货记录": json.loads(canonical(receipts))}
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("采购台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("采购台账 SHA256 校验失败")
        return validate_state(body.get("采购明细"), body.get("到货记录"))

    def load(self):
        if not self.path.exists():
            self.lines, self.receipts = [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("采购台账超过 100 MiB 安全上限")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"采购台账无法读取：{exc}") from exc
        self.lines, self.receipts = self.decode(payload)

    def _commit(self, lines, receipts):
        normalized_lines, normalized_receipts = validate_state(lines, receipts)
        data = canonical(self._payload(normalized_lines, normalized_receipts)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("采购台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.lines, self.receipts = normalized_lines, normalized_receipts

    def _line_map(self):
        return {row["明细编号"].casefold(): row for row in self.lines}

    def add_line(self, row):
        line = normalize_line(row)
        if any(item["明细编号"].casefold() == line["明细编号"].casefold() for item in self.lines):
            raise ValueError("采购明细编号已存在")
        if len(self.lines) >= MAX_LINES:
            raise ValueError(f"采购明细不能超过 {MAX_LINES} 条")
        self._commit(self.lines + [line], self.receipts)
        return line["明细编号"]

    def update_line(self, line_id, row):
        current = next((item for item in self.lines if item["明细编号"].casefold() == str(line_id).casefold()), None)
        if current is None:
            raise ValueError("未找到要修改的采购明细")
        line = normalize_line(row)
        if line["明细编号"].casefold() != current["明细编号"].casefold():
            raise ValueError("已有采购明细不能直接修改明细编号")
        updated = [line if item["明细编号"].casefold() == current["明细编号"].casefold() else item for item in self.lines]
        self._commit(updated, self.receipts)
        return line["明细编号"]

    def record_receipt(self, row):
        receipt = normalize_receipt(row, self._line_map())
        if any(item["到货记录编号"].casefold() == receipt["到货记录编号"].casefold() for item in self.receipts):
            raise ValueError("到货记录编号已存在")
        if len(self.receipts) >= MAX_RECEIPTS:
            raise ValueError(f"到货记录不能超过 {MAX_RECEIPTS} 条")
        self._commit(self.lines, self.receipts + [receipt])
        return receipt["到货记录编号"]

    def search_lines(self, keyword=""):
        needle = str(keyword or "").strip().casefold()
        if not needle:
            return list(self.lines)
        fields = ("明细编号", "采购单号", "供应商", "SKU", "商品名称", "采购员", "备注")
        return [row for row in self.lines if needle in " ".join(str(row.get(field, "")) for field in fields).casefold()]

    def calculate_line(self, line, *, today=None):
        records = [row for row in self.receipts if row["明细编号"].casefold() == line["明细编号"].casefold()]
        good = sum((Decimal(row["合格数量"]) for row in records), Decimal("0"))
        damaged = sum((Decimal(row["破损数量"]) for row in records), Decimal("0"))
        rejected = sum((Decimal(row["拒收数量"]) for row in records), Decimal("0"))
        ordered = Decimal(line["订购数量"])
        price = Decimal(line["采购单价"])
        remaining = max(ordered - good, Decimal("0"))
        over = max(good - ordered, Decimal("0"))
        expected = date.fromisoformat(line["预计到货日期"])
        current_day = today or date.today()
        if remaining <= 0:
            status = "已到齐"
        elif expected < current_day:
            status = "逾期部分到货" if good > 0 else "逾期未到货"
        elif good > 0:
            status = "部分到货"
        else:
            status = "待到货"
        physical = good + damaged + rejected
        last_receipt = max((row["到货日期"] for row in records), default="")
        return {
            **line, "到货总量": decimal_text(physical), "合格到货": decimal_text(good),
            "破损数量": decimal_text(damaged), "拒收数量": decimal_text(rejected),
            "剩余待到货": decimal_text(remaining), "超出订购": decimal_text(over),
            "已验收金额": decimal_text(good * price, places=2),
            "待到货金额": decimal_text(remaining * price, places=2),
            "最后到货日期": last_receipt, "状态": status,
        }

    def report_rows(self, *, today=None):
        return [self.calculate_line(row, today=today) for row in self.lines]

    def summary(self, *, today=None):
        rows = self.report_rows(today=today)
        orders = {row["采购单号"].casefold() for row in self.lines}
        total = lambda field: sum((Decimal(row[field]) for row in rows), Decimal("0"))
        return {
            "采购单数": len(orders), "采购明细数": len(rows),
            "逾期未齐明细": sum(row["状态"].startswith("逾期") for row in rows),
            "部分到货明细": sum(row["状态"] in ("部分到货", "逾期部分到货") for row in rows),
            "待到货数量": decimal_text(total("剩余待到货")),
            "待到货金额": decimal_text(total("待到货金额"), places=2),
            "合格到货数量": decimal_text(total("合格到货")),
            "破损数量": decimal_text(total("破损数量")),
            "拒收数量": decimal_text(total("拒收数量")),
            "已验收金额": decimal_text(total("已验收金额"), places=2),
        }

    def supplier_summary_rows(self, *, today=None):
        groups = {}
        source_map = {
            "待到货数量": "剩余待到货", "待到货金额": "待到货金额",
            "合格到货数量": "合格到货", "破损数量": "破损数量",
            "拒收数量": "拒收数量", "已验收金额": "已验收金额",
        }
        for row in self.report_rows(today=today):
            key = row["供应商"].casefold()
            group = groups.setdefault(key, {
                "供应商": row["供应商"], "_orders": set(), "采购明细数": 0,
                "逾期未齐明细": 0, "部分到货明细": 0,
                **{field: Decimal("0") for field in source_map},
            })
            group["_orders"].add(row["采购单号"].casefold())
            group["采购明细数"] += 1
            group["逾期未齐明细"] += int(row["状态"].startswith("逾期"))
            group["部分到货明细"] += int(row["状态"] in ("部分到货", "逾期部分到货"))
            for field, source in source_map.items():
                group[field] += Decimal(row[source])
        result = []
        for group in groups.values():
            result.append({
                "供应商": group["供应商"], "采购单数": len(group["_orders"]),
                "采购明细数": group["采购明细数"],
                "逾期未齐明细": group["逾期未齐明细"],
                "部分到货明细": group["部分到货明细"],
                "待到货数量": decimal_text(group["待到货数量"]),
                "待到货金额": decimal_text(group["待到货金额"], places=2),
                "合格到货数量": decimal_text(group["合格到货数量"]),
                "破损数量": decimal_text(group["破损数量"]),
                "拒收数量": decimal_text(group["拒收数量"]),
                "已验收金额": decimal_text(group["已验收金额"], places=2),
            })
        return sorted(result, key=lambda row: (-Decimal(row["待到货金额"]), row["供应商"].casefold()))

    @staticmethod
    def _write_csv(path, fields, rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: spreadsheet_safe_cell(row.get(field, "")) for field in fields})
        atomic_write(path, buffer.getvalue().encode("utf-8-sig"))

    def import_lines_csv(self, path):
        incoming = [normalize_line(row) for row in read_csv_rows(path, LINE_FIELDS, MAX_LINES)]
        existing = {row["明细编号"].casefold() for row in self.lines}
        keys = [row["明细编号"].casefold() for row in incoming]
        if len(keys) != len(set(keys)) or existing.intersection(keys):
            raise ValueError("导入采购明细存在重复编号；本次导入已取消")
        if len(self.lines) + len(incoming) > MAX_LINES:
            raise ValueError(f"采购明细不能超过 {MAX_LINES} 条")
        if incoming:
            self._commit(self.lines + incoming, self.receipts)
        return len(incoming)

    def import_receipts_csv(self, path):
        incoming = [normalize_receipt(row, self._line_map()) for row in read_csv_rows(path, RECEIPT_FIELDS, MAX_RECEIPTS)]
        existing = {row["到货记录编号"].casefold() for row in self.receipts}
        keys = [row["到货记录编号"].casefold() for row in incoming]
        if len(keys) != len(set(keys)) or existing.intersection(keys):
            raise ValueError("导入到货记录存在重复编号；本次导入已取消")
        if len(self.receipts) + len(incoming) > MAX_RECEIPTS:
            raise ValueError(f"到货记录不能超过 {MAX_RECEIPTS} 条")
        if incoming:
            self._commit(self.lines, self.receipts + incoming)
        return len(incoming)

    def export_lines_csv(self, path):
        self._write_csv(path, LINE_FIELDS, self.lines)

    def export_receipts_csv(self, path):
        self._write_csv(path, RECEIPT_FIELDS, self.receipts)

    def export_report_csv(self, path, *, today=None):
        self._write_csv(path, REPORT_FIELDS, self.report_rows(today=today))

    def export_supplier_summary_csv(self, path, *, today=None):
        self._write_csv(path, SUPPLIER_SUMMARY_FIELDS, self.supplier_summary_rows(today=today))

    def backup(self, path):
        data = canonical(self._payload(self.lines, self.receipts)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)
        return hashlib.sha256(data).hexdigest()

    def restore(self, path):
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件不存在或超过 100 MiB 安全上限")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"备份文件无法读取：{exc}") from exc
        lines, receipts = self.decode(payload)
        self._commit(lines, receipts)
        return len(lines), len(receipts)


def self_test():
    from tempfile import TemporaryDirectory
    from datetime import timedelta
    today = date.today()
    with TemporaryDirectory() as directory:
        store = PurchaseOrderStore(Path(directory) / "purchase-orders.json")
        store.add_line({
            "明细编号": "PO-LINE-DEMO", "采购单号": "PO-DEMO-001",
            "供应商": "演示供应商", "下单日期": today.isoformat(),
            "预计到货日期": (today + timedelta(days=3)).isoformat(),
            "SKU": "DEMO-001", "商品名称": "演示商品",
            "订购数量": "10", "采购单价": "2.50",
        })
        store.record_receipt({
            "到货记录编号": "PO-RCV-DEMO", "明细编号": "PO-LINE-DEMO",
            "到货日期": today.isoformat(), "合格数量": "4",
            "破损数量": "1", "拒收数量": "0",
        })
        row = store.report_rows()[0]
        assert row["剩余待到货"] == "6" and row["状态"] == "部分到货"
        backup = Path(directory) / "backup.json"
        store.backup(backup)
        restored = PurchaseOrderStore(Path(directory) / "restored.json")
        assert restored.restore(backup) == (1, 1)
        assert restored.report_rows() == store.report_rows()


if __name__ == "__main__":
    self_test()
    print("SELF_TEST_OK")
