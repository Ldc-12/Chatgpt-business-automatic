"""Offline store replenishment planner with local sales history and auditable formulas."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-store-replenishment"
VERSION = 1
MAX_ITEMS = 20000
MAX_SALES = 500000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_QUANTITY = Decimal("999999999.999")
MAX_MONEY = Decimal("999999999999.99")
QUANTITY_UNIT = Decimal("0.001")
CENT = Decimal("0.01")

ITEM_FIELDS = [
    "SKU", "商品名称", "当前库存", "已预留", "采购提前期天数",
    "安全库存天数", "目标覆盖天数", "整箱数量", "最低起订量",
    "采购单价", "供应商", "备注",
]
SALES_FIELDS = ["销售编号", "SKU", "日期", "销量", "备注"]
PLAN_FIELDS = [
    "SKU", "商品名称", "当前库存", "已预留", "可用库存", "日均销量",
    "采购提前期天数", "安全库存天数", "补货触发库存", "目标库存",
    "建议采购量", "采购单价", "预计采购金额", "建议状态", "供应商",
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decimal_text(value, places=3):
    quantum = QUANTITY_UNIT if places == 3 else CENT
    rendered = format(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP), "f")
    return rendered if places == 2 else (rendered.rstrip("0").rstrip(".") if "." in rendered else rendered)


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


def bounded_days(value, field, *, minimum=0, maximum=365):
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,3}", text):
        raise ValueError(f"{field}必须是 {minimum} 至 {maximum} 的整数")
    number = int(text)
    if number < minimum or number > maximum:
        raise ValueError(f"{field}必须是 {minimum} 至 {maximum} 的整数")
    return number


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


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


def normalize_item(row):
    if not isinstance(row, dict):
        raise ValueError("商品资料必须是对象")
    sku = str(row.get("SKU", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", sku):
        raise ValueError("SKU 只能包含 1–64 位字母、数字、点、下划线或连字符")
    name = str(row.get("商品名称", "") or "").strip()
    if not name or len(name) > 80:
        raise ValueError("商品名称不能为空且不能超过 80 个字符")
    stock = parse_decimal(row.get("当前库存", ""), "当前库存")
    reserved = parse_decimal(row.get("已预留", "0"), "已预留")
    lead = bounded_days(row.get("采购提前期天数", "0"), "采购提前期天数")
    safety = bounded_days(row.get("安全库存天数", "0"), "安全库存天数")
    target = bounded_days(row.get("目标覆盖天数", "7"), "目标覆盖天数", minimum=1)
    pack = parse_decimal(row.get("整箱数量", "1"), "整箱数量", minimum=QUANTITY_UNIT)
    moq = parse_decimal(row.get("最低起订量", "0"), "最低起订量")
    price = parse_decimal(row.get("采购单价", "0"), "采购单价", maximum=MAX_MONEY, places=2)
    supplier = str(row.get("供应商", "") or "").strip()
    note = str(row.get("备注", "") or "").strip()
    if len(supplier) > 80 or len(note) > 500:
        raise ValueError("供应商最多 80 个字符，备注最多 500 个字符")
    if any(ord(ch) < 32 for ch in supplier + note):
        raise ValueError("供应商和备注不能包含控制字符")
    return {
        "SKU": sku, "商品名称": name, "当前库存": stock, "已预留": reserved,
        "采购提前期天数": lead, "安全库存天数": safety, "目标覆盖天数": target,
        "整箱数量": pack, "最低起订量": moq, "采购单价": price,
        "供应商": supplier, "备注": note,
    }


def normalize_sale(row, item_map, *, today=None):
    if not isinstance(row, dict):
        raise ValueError("销量记录必须是对象")
    sale_id = str(row.get("销售编号", "") or "").strip() or ("S" + uuid.uuid4().hex[:20].upper())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sale_id):
        raise ValueError("销售编号格式无效")
    sku = str(row.get("SKU", "") or "").strip()
    item = item_map.get(sku.casefold())
    if item is None:
        raise ValueError(f"销量记录引用了不存在的 SKU：{sku}")
    sale_day = parse_date(row.get("日期", ""), "销售日期")
    if date.fromisoformat(sale_day) > (today or date.today()):
        raise ValueError("销售日期不能晚于今天")
    quantity = parse_decimal(row.get("销量", ""), "销量")
    note = str(row.get("备注", "") or "").strip()
    if len(note) > 300 or any(ord(ch) < 32 for ch in note):
        raise ValueError("销量备注最多 300 个字符且不能包含控制字符")
    return {"销售编号": sale_id, "SKU": item["SKU"], "日期": sale_day, "销量": quantity, "备注": note}


def validate_state(raw_items, raw_sales):
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        raise ValueError(f"商品资料缺失或超过 {MAX_ITEMS} 条安全上限")
    if not isinstance(raw_sales, list) or len(raw_sales) > MAX_SALES:
        raise ValueError(f"销量记录缺失或超过 {MAX_SALES} 条安全上限")
    items = [normalize_item(item) for item in raw_items]
    sku_keys = [item["SKU"].casefold() for item in items]
    if len(sku_keys) != len(set(sku_keys)):
        raise ValueError("SKU 重复（不区分大小写）")
    item_map = {item["SKU"].casefold(): item for item in items}
    sales = [normalize_sale(row, item_map) for row in raw_sales]
    sale_ids = [row["销售编号"] for row in sales]
    if len(sale_ids) != len(set(sale_ids)):
        raise ValueError("销售编号重复")
    return items, sales


def read_csv_rows(path, expected_fields):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV 文件超过 25 MiB 安全上限")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            raise ValueError("CSV 表头不匹配，请使用本软件导出的模板")
        rows = list(reader)
    if len(rows) > MAX_SALES:
        raise ValueError("CSV 行数超过安全上限")
    return rows


class ReplenishmentStore:
    def __init__(self, path):
        self.path = Path(path)
        self.items = []
        self.sales = []
        self.load()

    @staticmethod
    def _payload(items, sales):
        body = {"格式": FORMAT, "版本": VERSION, "商品": items, "销量": sales}
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("补货台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("补货台账 SHA256 校验失败")
        return validate_state(body.get("商品"), body.get("销量"))

    def load(self):
        if not self.path.exists():
            self.items, self.sales = [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("补货台账超过 100 MiB 安全上限")
        self.items, self.sales = self.decode(json.loads(self.path.read_text(encoding="utf-8")))

    def _commit(self, items, sales):
        normalized_items, normalized_sales = validate_state(items, sales)
        data = canonical(self._payload(normalized_items, normalized_sales)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("补货台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.items, self.sales = normalized_items, normalized_sales

    def _item_map(self):
        return {item["SKU"].casefold(): item for item in self.items}

    def add_item(self, row):
        item = normalize_item(row)
        if any(value["SKU"].casefold() == item["SKU"].casefold() for value in self.items):
            raise ValueError("SKU 已存在")
        if len(self.items) >= MAX_ITEMS:
            raise ValueError(f"商品数量不能超过 {MAX_ITEMS}")
        self._commit(self.items + [item], self.sales)
        return item["SKU"]

    def update_item(self, sku, row):
        current = next((value for value in self.items if value["SKU"].casefold() == str(sku).casefold()), None)
        if current is None:
            raise ValueError("未找到要修改的 SKU")
        item = normalize_item(row)
        if item["SKU"].casefold() != current["SKU"].casefold():
            raise ValueError("已有商品不能直接修改 SKU")
        updated = [item if value["SKU"].casefold() == current["SKU"].casefold() else value for value in self.items]
        self._commit(updated, self.sales)
        return item["SKU"]

    def record_sale(self, row):
        sale = normalize_sale(row, self._item_map())
        if any(value["销售编号"] == sale["销售编号"] for value in self.sales):
            raise ValueError("销售编号重复")
        if len(self.sales) >= MAX_SALES:
            raise ValueError(f"销量记录不能超过 {MAX_SALES}")
        self._commit(self.items, self.sales + [sale])
        return sale["销售编号"]

    def plan(self, lookback_days=30, *, today=None):
        lookback = bounded_days(lookback_days, "统计天数", minimum=1, maximum=365)
        current_day = today or date.today()
        start_day = current_day - timedelta(days=lookback - 1)
        sales_by_sku = {}
        for sale in self.sales:
            sale_day = date.fromisoformat(sale["日期"])
            if start_day <= sale_day <= current_day:
                sales_by_sku.setdefault(sale["SKU"].casefold(), []).append(sale)
        rows = []
        for item in self.items:
            records = sales_by_sku.get(item["SKU"].casefold(), [])
            total = sum((Decimal(value["销量"]) for value in records), Decimal("0"))
            average = total / Decimal(lookback)
            available = Decimal(item["当前库存"]) - Decimal(item["已预留"])
            lead = item["采购提前期天数"]
            safety = item["安全库存天数"]
            target_days = item["目标覆盖天数"]
            trigger = average * Decimal(lead + safety)
            target = average * Decimal(lead + safety + target_days)
            order_quantity = Decimal("0")
            if not records:
                status = "缺少销量数据"
            elif average <= 0:
                status = "无销量需求"
            elif available <= trigger:
                raw_quantity = max(target - available, Decimal("0"))
                pack = Decimal(item["整箱数量"])
                order_quantity = (raw_quantity / pack).to_integral_value(rounding=ROUND_CEILING) * pack
                minimum = Decimal(item["最低起订量"])
                if order_quantity > 0 and order_quantity < minimum:
                    order_quantity = (minimum / pack).to_integral_value(rounding=ROUND_CEILING) * pack
                status = "建议补货" if order_quantity > 0 else "无需补货"
            else:
                status = "库存充足"
            cost = order_quantity * Decimal(item["采购单价"])
            rows.append({
                "SKU": item["SKU"], "商品名称": item["商品名称"],
                "当前库存": item["当前库存"], "已预留": item["已预留"],
                "可用库存": decimal_text(available), "日均销量": decimal_text(average),
                "采购提前期天数": lead, "安全库存天数": safety,
                "补货触发库存": decimal_text(trigger), "目标库存": decimal_text(target),
                "建议采购量": decimal_text(order_quantity), "采购单价": item["采购单价"],
                "预计采购金额": decimal_text(cost, places=2), "建议状态": status,
                "供应商": item["供应商"],
            })
        return rows

    def summary(self, lookback_days=30, *, today=None):
        rows = self.plan(lookback_days, today=today)
        suggested = [row for row in rows if row["建议状态"] == "建议补货"]
        budget = sum((Decimal(row["预计采购金额"]) for row in suggested), Decimal("0"))
        return {
            "商品 SKU": len(self.items),
            "建议补货 SKU": len(suggested),
            "缺少销量数据 SKU": sum(row["建议状态"] == "缺少销量数据" for row in rows),
            "预计采购金额": decimal_text(budget, places=2),
        }

    def search_items(self, keyword=""):
        needle = str(keyword or "").strip().casefold()
        if not needle:
            return list(self.items)
        return [
            item for item in self.items
            if needle in " ".join(str(item.get(field, "")) for field in ("SKU", "商品名称", "供应商", "备注")).casefold()
        ]

    @staticmethod
    def paginate(rows, page, page_size=100):
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ValueError("每页数量必须是正整数")
        try:
            requested = int(page)
        except (TypeError, ValueError):
            raise ValueError("页码必须是正整数") from None
        if requested < 1:
            requested = 1
        values = list(rows)
        pages = max(1, (len(values) + page_size - 1) // page_size)
        current = min(requested, pages)
        start = (current - 1) * page_size
        return values[start:start + page_size], current, pages, len(values)

    @staticmethod
    def _write_csv(path, fields, rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe(row.get(field, "")) for field in fields})
        atomic_write(path, buffer.getvalue().encode("utf-8-sig"))

    def import_items_csv(self, path):
        incoming = [normalize_item(row) for row in read_csv_rows(path, ITEM_FIELDS)]
        existing = {item["SKU"].casefold() for item in self.items}
        keys = [item["SKU"].casefold() for item in incoming]
        if len(keys) != len(set(keys)) or existing.intersection(keys):
            raise ValueError("导入商品存在重复 SKU；本次导入已取消")
        if len(self.items) + len(incoming) > MAX_ITEMS:
            raise ValueError(f"商品数量不能超过 {MAX_ITEMS}")
        if incoming:
            self._commit(self.items + incoming, self.sales)
        return len(incoming)

    def import_sales_csv(self, path):
        incoming = [normalize_sale(row, self._item_map()) for row in read_csv_rows(path, SALES_FIELDS)]
        existing = {row["销售编号"] for row in self.sales}
        keys = [row["销售编号"] for row in incoming]
        if len(keys) != len(set(keys)) or existing.intersection(keys):
            raise ValueError("导入销量存在重复销售编号；本次导入已取消")
        if len(self.sales) + len(incoming) > MAX_SALES:
            raise ValueError(f"销量记录不能超过 {MAX_SALES}")
        if incoming:
            self._commit(self.items, self.sales + incoming)
        return len(incoming)

    def export_items_csv(self, path):
        self._write_csv(path, ITEM_FIELDS, self.items)

    def export_sales_csv(self, path):
        self._write_csv(path, SALES_FIELDS, self.sales)

    def export_plan_csv(self, path, lookback_days=30, *, today=None):
        self._write_csv(path, PLAN_FIELDS, self.plan(lookback_days, today=today))

    def backup(self, path):
        data = canonical(self._payload(self.items, self.sales)) + b"\n"
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)
        return hashlib.sha256(data).hexdigest()

    def restore(self, path):
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件不存在或超过 100 MiB 安全上限")
        items, sales = self.decode(json.loads(source.read_text(encoding="utf-8")))
        self._commit(items, sales)
        return len(items), len(sales)


def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        store = ReplenishmentStore(Path(directory) / "replenishment.json")
        store.add_item({
            "SKU": "DEMO-001", "商品名称": "测试商品", "当前库存": "0",
            "已预留": "0", "采购提前期天数": "2", "安全库存天数": "1",
            "目标覆盖天数": "7", "整箱数量": "1", "最低起订量": "0",
            "采购单价": "2.50",
        })
        store.record_sale({"SKU": "DEMO-001", "日期": date.today().isoformat(), "销量": "2"})
        assert store.plan(7)[0]["建议状态"] == "建议补货"
        assert ReplenishmentStore(store.path).items == store.items
    print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    self_test()
