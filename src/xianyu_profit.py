"""Offline Xianyu order profit, fee estimate and after-sales cost ledger."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-xianyu-order-profit"
BACKUP_FORMAT = "mainland-xianyu-order-profit-backup"
VERSION = 1
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64
STATUSES = ("交易中", "已完成", "售后中", "已退款", "已关闭")
FIELDS = (
    "记录编号", "订单编号", "成交日期", "商品/SKU", "买家备注",
    "买家实付金额(元)", "商品成本(元)", "包装成本(元)", "发货运费(元)",
    "平台费率(%)", "平台固定费用(元)", "实际平台费用(元)",
    "推广费用(元)", "售后退款(元)", "售后补偿(元)", "退货运费(元)",
    "售后回收金额(元)", "订单状态", "备注",
)
TEXT_FIELDS = {"记录编号", "订单编号", "成交日期", "商品/SKU", "买家备注", "订单状态", "备注"}
AMOUNT_FIELDS = (
    "买家实付金额(元)", "商品成本(元)", "包装成本(元)", "发货运费(元)",
    "平台固定费用(元)", "实际平台费用(元)", "推广费用(元)",
    "售后退款(元)", "售后补偿(元)", "退货运费(元)", "售后回收金额(元)",
)


def _decimal(value, label: str, allow_blank: bool = False) -> Decimal | None:
    raw = str(value if value is not None else "").strip().replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    if not raw:
        if allow_blank:
            return None
        raise ValueError(f"{label}不能为空")
    if len(raw) > MAX_NUMERIC_TEXT_LENGTH:
        raise ValueError(f"{label}输入过长，最多 {MAX_NUMERIC_TEXT_LENGTH} 个字符")
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not result.is_finite():
        raise ValueError(f"{label}不能是 NaN 或无穷大")
    if abs(result) > MAX_NUMERIC_ABS:
        raise ValueError(f"{label}超出支持范围，绝对值不能超过 1,000,000,000")
    return result


def _money(value: Decimal, label: str) -> str:
    try:
        result = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出人民币分位精度范围") from exc
    if value > 0 and result <= 0:
        raise ValueError(f"{label}小于 0.01 元，无法准确核算")
    return format(result, "f")


def normalize_order_row(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("订单记录必须是对象")
    result = {field: str("" if row.get(field) is None else row.get(field, "")).strip() for field in FIELDS}
    required = ("记录编号", "订单编号", "成交日期", "商品/SKU", "订单状态")
    for field in required:
        if not result[field]:
            raise ValueError(f"{field}不能为空")
        if len(result[field]) > 120:
            raise ValueError(f"{field}长度不能超过 120 个字符")
    if len(result["买家备注"]) > 200:
        raise ValueError("买家备注不能超过 200 个字符")
    if len(result["备注"]) > 2000:
        raise ValueError("备注不能超过 2000 个字符")
    try:
        parsed_date = date.fromisoformat(result["成交日期"])
    except ValueError as exc:
        raise ValueError("成交日期必须使用 YYYY-MM-DD 格式") from exc
    if parsed_date.isoformat() != result["成交日期"]:
        raise ValueError("成交日期必须使用 YYYY-MM-DD 格式")
    if result["订单状态"] not in STATUSES:
        raise ValueError("订单状态不在内置列表中")
    if not result["买家实付金额(元)"]:
        raise ValueError("买家实付金额(元)不能为空")
    if not result["商品成本(元)"]:
        raise ValueError("商品成本(元)不能为空")

    for field in AMOUNT_FIELDS:
        raw = result[field]
        if field == "实际平台费用(元)" and not raw:
            result[field] = ""
            continue
        value = _decimal(raw, field, allow_blank=True)
        if value is None:
            value = Decimal("0")
        if value < 0:
            raise ValueError(f"{field}不能为负数")
        result[field] = _money(value, field)

    rate = _decimal(result["平台费率(%)"], "平台费率", allow_blank=True)
    rate = Decimal("0") if rate is None else rate
    if rate < 0 or rate >= 100:
        raise ValueError("平台费率必须在 0–100% 之间，且小于 100%")
    try:
        rounded_rate = rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("平台费率超出支持精度范围") from exc
    if rate > 0 and rounded_rate <= 0:
        raise ValueError("平台费率小于 0.01%，无法准确核算")
    result["平台费率(%)"] = format(rounded_rate, "f")

    if Decimal(result["售后退款(元)"]) > Decimal(result["买家实付金额(元)"]):
        raise ValueError("售后退款不能超过买家实付金额")
    return result


def calculate_order(row: dict) -> dict:
    item = normalize_order_row(row)
    gross = Decimal(item["买家实付金额(元)"])
    refund = Decimal(item["售后退款(元)"])
    net_revenue = gross - refund
    rate = Decimal(item["平台费率(%)"])
    fixed_fee = Decimal(item["平台固定费用(元)"])
    estimated_fee = (gross * rate / Decimal("100") + fixed_fee).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if item["实际平台费用(元)"]:
        platform_fee = Decimal(item["实际平台费用(元)"])
        fee_source = "实际"
    else:
        platform_fee = estimated_fee
        fee_source = "按本单费率估算"

    expenses = sum(
        (
            Decimal(item["商品成本(元)"]),
            Decimal(item["包装成本(元)"]),
            Decimal(item["发货运费(元)"]),
            platform_fee,
            Decimal(item["推广费用(元)"]),
            Decimal(item["售后补偿(元)"]),
            Decimal(item["退货运费(元)"]),
        ),
        Decimal("0"),
    )
    recovery = Decimal(item["售后回收金额(元)"])
    profit = net_revenue - expenses + recovery
    margin = None if net_revenue <= 0 else (
        profit / net_revenue * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "买家实付金额(元)": _money(gross, "买家实付金额"),
        "售后退款(元)": _money(refund, "售后退款"),
        "订单净收入(元)": _money(net_revenue, "订单净收入"),
        "平台费用(元)": _money(platform_fee, "平台费用"),
        "平台费用口径": fee_source,
        "成本支出(元)": _money(expenses, "成本支出"),
        "售后回收金额(元)": _money(recovery, "售后回收金额"),
        "净利润(元)": _money(abs(profit), "净利润") if profit >= 0 else "-" + _money(abs(profit), "净利润"),
        "净利率(%)": "" if margin is None else format(margin, "f"),
    }


def break_even_price(non_platform_costs, fee_rate_pct, fixed_fee=0) -> str:
    costs = _decimal(non_platform_costs, "平台费前成本")
    rate = _decimal(fee_rate_pct, "平台费率")
    fixed = _decimal(fixed_fee, "平台固定费用")
    if costs < 0 or fixed < 0:
        raise ValueError("成本和固定费用不能为负数")
    if rate < 0 or rate >= 100:
        raise ValueError("平台费率必须在 0–100% 之间，且小于 100%")
    denominator = Decimal("1") - rate / Decimal("100")
    price = (costs + fixed) / denominator
    try:
        rounded = price.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    except InvalidOperation as exc:
        raise ValueError("保本售价超出支持精度范围") from exc
    return format(rounded, "f")


def _safe_csv_text(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class OrderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def validate_rows(rows):
        ids = [row["记录编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("记录编号重复")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("orders"), list)
            ):
                raise ValueError("订单台账数据格式或版本不受支持")
            rows = [normalize_order_row(item) for item in payload["orders"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"订单台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        normalized = [normalize_order_row(row) for row in items]
        self.validate_rows(normalized)
        payload = {
            "format": FORMAT,
            "version": VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "orders": normalized,
        }
        _atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def add(self, row):
        item = normalize_order_row(row)
        if any(old["记录编号"] == item["记录编号"] for old in self.rows):
            raise ValueError("记录编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, record_id, row):
        item = normalize_order_row(row)
        if item["记录编号"] != record_id:
            raise ValueError("记录编号不能修改")
        index = next((i for i, old in enumerate(self.rows) if old["记录编号"] == record_id), None)
        if index is None:
            raise ValueError("找不到要编辑的订单记录")
        updated = list(self.rows)
        updated[index] = item
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def delete(self, record_id):
        updated = [row for row in self.rows if row["记录编号"] != record_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的订单记录")
        self.save(updated)
        self.rows = updated

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(FIELDS):
                raise ValueError("CSV 表头必须与软件导出的字段和顺序完全一致")
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余字段")
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_order_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
                if len(incoming) > 100000:
                    raise ValueError("单次最多导入 100000 条订单记录")
        self.validate_rows(incoming)
        existing = {row["记录编号"] for row in self.rows}
        duplicates = existing.intersection(row["记录编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在记录编号，整批未导入：" + "、".join(sorted(duplicates)))
        updated = self.rows + incoming
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated
        return len(incoming)

    def export_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({
                field: _safe_csv_text(row[field]) if field in TEXT_FIELDS else row[field]
                for field in FIELDS
            })
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))

    def backup(self, path):
        orders = [dict(row) for row in self.rows]
        canonical = json.dumps(orders, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload = {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "orders": orders,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }
        _atomic_write(Path(path), json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def restore(self, path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("orders"), list)
                or not isinstance(payload.get("sha256"), str)
            ):
                raise ValueError("备份文件格式或版本不受支持")
            canonical = json.dumps(payload["orders"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            actual = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(actual, payload["sha256"]):
                raise ValueError("备份 SHA256 校验失败，当前数据未修改")
            rows = [normalize_order_row(item) for item in payload["orders"]]
            self.validate_rows(rows)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"恢复失败，当前数据未修改：{exc}") from exc
        self.save(rows)
        self.rows = rows


def monthly_summary(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        item = normalize_order_row(row)
        calc = calculate_order(item)
        key = item["成交日期"][:7]
        bucket = grouped.setdefault(key, {
            "月份": key,
            "_order_ids": set(),
            "_after_sales_order_ids": set(),
            "买家实付(元)": Decimal("0"),
            "售后退款(元)": Decimal("0"),
            "净收入(元)": Decimal("0"),
            "成本支出(元)": Decimal("0"),
            "售后回收(元)": Decimal("0"),
            "净利润(元)": Decimal("0"),
        })
        # A single Xianyu order may contain several SKU/detail rows.
        # Count the order once while still summing every detail's money.
        bucket["_order_ids"].add(item["订单编号"])
        bucket["买家实付(元)"] += Decimal(calc["买家实付金额(元)"])
        bucket["售后退款(元)"] += Decimal(calc["售后退款(元)"])
        bucket["净收入(元)"] += Decimal(calc["订单净收入(元)"])
        bucket["成本支出(元)"] += Decimal(calc["成本支出(元)"])
        bucket["售后回收(元)"] += Decimal(calc["售后回收金额(元)"])
        bucket["净利润(元)"] += Decimal(calc["净利润(元)"])
        if item["订单状态"] in ("售后中", "已退款") or Decimal(item["售后退款(元)"]) > 0:
            bucket["_after_sales_order_ids"].add(item["订单编号"])
    money_fields = ("买家实付(元)", "售后退款(元)", "净收入(元)", "成本支出(元)", "售后回收(元)", "净利润(元)")
    return {
        key: {
            "月份": value["月份"],
            "订单数": len(value["_order_ids"]),
            "售后订单数": len(value["_after_sales_order_ids"]),
            **{field: _money(value[field], field) for field in money_fields},
        }
        for key, value in grouped.items()
    }


def sku_summary(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        item = normalize_order_row(row)
        calc = calculate_order(item)
        key = item["商品/SKU"]
        bucket = grouped.setdefault(key, {
            "商品/SKU": key,
            "_order_ids": set(),
            "_net_revenue": Decimal("0"),
            "_net_profit": Decimal("0"),
        })
        # Multiple detail rows for the same SKU in one order are still one
        # SKU-order relationship, not multiple orders.
        bucket["_order_ids"].add(item["订单编号"])
        bucket["_net_revenue"] += Decimal(calc["订单净收入(元)"])
        bucket["_net_profit"] += Decimal(calc["净利润(元)"])
    return {
        key: {
            "商品/SKU": value["商品/SKU"],
            "订单数": len(value["_order_ids"]),
            "净收入(元)": _money(value["_net_revenue"], "SKU净收入"),
            "净利润(元)": _money(value["_net_profit"], "SKU净利润"),
        }
        for key, value in grouped.items()
    }

def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "xianyu_order_profit.json"


def self_test():
    import tempfile

    sample = {
        "记录编号": "XY-TEST-001", "订单编号": "XY-ORDER-001", "成交日期": "2026-11-01",
        "商品/SKU": "测试蓝牙耳机", "买家备注": "", "买家实付金额(元)": "100",
        "商品成本(元)": "40", "包装成本(元)": "2", "发货运费(元)": "5",
        "平台费率(%)": "1", "平台固定费用(元)": "0.5", "实际平台费用(元)": "",
        "推广费用(元)": "3", "售后退款(元)": "10", "售后补偿(元)": "2",
        "退货运费(元)": "1", "售后回收金额(元)": "5", "订单状态": "已完成", "备注": "",
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = OrderStore(root / "orders.json")
        store.add(sample)
        assert calculate_order(sample)["净利润(元)"] == "40.50"
        assert break_even_price("50", "1", "0.5") == "51.02"
        assert monthly_summary(store.rows)["2026-11"]["订单数"] == 1
        csv_path = root / "orders.csv"
        store.export_csv(csv_path)
        imported = OrderStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup = root / "orders-backup.json"
        store.backup(backup)
        restored = OrderStore(root / "restored.json")
        restored.restore(backup)
        assert restored.rows == store.rows
    if __import__("sys").stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    self_test()
