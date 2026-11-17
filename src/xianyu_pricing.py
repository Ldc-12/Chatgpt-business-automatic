"""Offline, versioned second-hand pricing rules and a local Xianyu listing ledger."""
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

FORMAT = "mainland-xianyu-used-pricing"
BACKUP_FORMAT = "mainland-xianyu-used-pricing-backup"
VERSION = 1
RULESET_VERSION = "XY-USED-PRICE-2026.11"
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64
MAX_DATA_BYTES = 100 * 1024 * 1024
MAX_ROWS = 100000

AGE_BANDS = (0, 6, 12, 24, 36, 60)
CATEGORIES = (
    "手机数码", "电脑办公", "家用电器", "家具家居",
    "运动户外", "母婴用品", "服饰鞋包", "工具设备", "其他",
)
# Internal reference coefficients, not market quotations or guaranteed resale values.
CATEGORY_DEPRECIATION = {
    "手机数码": (1.00, 0.88, 0.78, 0.58, 0.42, 0.28),
    "电脑办公": (1.00, 0.90, 0.80, 0.62, 0.46, 0.30),
    "家用电器": (1.00, 0.95, 0.88, 0.76, 0.62, 0.46),
    "家具家居": (1.00, 0.96, 0.90, 0.82, 0.70, 0.56),
    "运动户外": (1.00, 0.92, 0.84, 0.70, 0.55, 0.38),
    "母婴用品": (1.00, 0.90, 0.80, 0.62, 0.44, 0.27),
    "服饰鞋包": (1.00, 0.86, 0.74, 0.56, 0.38, 0.22),
    "工具设备": (1.00, 0.96, 0.91, 0.82, 0.70, 0.56),
    "其他": (1.00, 0.92, 0.82, 0.68, 0.52, 0.36),
}
CONDITIONS = ("全新未拆封", "近全新", "9成新", "8成新", "7成新", "明显瑕疵")
CONDITION_FACTORS = {
    "全新未拆封": Decimal("1.00"),
    "近全新": Decimal("0.93"),
    "9成新": Decimal("0.86"),
    "8成新": Decimal("0.75"),
    "7成新": Decimal("0.62"),
    "明显瑕疵": Decimal("0.45"),
}
STATUSES = ("待上架", "已上架", "已售出", "已下架")
FIELDS = (
    "商品编号", "商品名称", "品类", "购入日期", "原价(元)", "购入成本(元)",
    "成色", "配件/瑕疵扣减(元)", "整备费用(元)", "包装运费(元)",
    "售后预留(元)", "平台费率(%)", "平台固定费用(元)", "目标利润(元)",
    "议价空间(%)", "同类成交中位价(元)", "上架状态", "备注",
)
TEXT_FIELDS = {"商品编号", "商品名称", "品类", "购入日期", "成色", "上架状态", "备注"}
AMOUNT_FIELDS = (
    "原价(元)", "购入成本(元)", "配件/瑕疵扣减(元)", "整备费用(元)",
    "包装运费(元)", "售后预留(元)", "平台固定费用(元)", "目标利润(元)",
    "同类成交中位价(元)",
)


def _decimal(value, label: str, allow_blank: bool = False) -> Decimal | None:
    raw = str(value if value is not None else "").strip()
    raw = raw.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
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
        raise ValueError(f"{label}超出支持范围")
    return result


def _money(value: Decimal, label: str) -> str:
    try:
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出人民币分位精度范围") from exc
    return format(rounded, "f")


def _ceil_cent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _ceil_yuan(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_CEILING).quantize(Decimal("0.01"))


def age_in_months(purchase_date: str, as_of: date | None = None) -> int:
    try:
        purchased = date.fromisoformat(str(purchase_date))
    except ValueError as exc:
        raise ValueError("购入日期必须使用 YYYY-MM-DD 格式") from exc
    today = as_of or date.today()
    if purchased > today:
        raise ValueError("购入日期不能晚于估价日期")
    months = (today.year - purchased.year) * 12 + today.month - purchased.month
    if today.day < purchased.day:
        months -= 1
    return max(0, months)


def depreciation_factor(category: str, age_months: int) -> Decimal:
    if category not in CATEGORY_DEPRECIATION:
        raise ValueError("品类不在内置估值规则中")
    if age_months < 0:
        raise ValueError("商品使用月数不能为负数")
    factors = CATEGORY_DEPRECIATION[category]
    selected = factors[0]
    for boundary, factor in zip(AGE_BANDS, factors):
        if age_months >= boundary:
            selected = factor
        else:
            break
    return Decimal(str(selected))


def normalize_item_row(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("商品记录必须是对象")
    result = {
        field: str("" if row.get(field) is None else row.get(field, "")).strip()
        for field in FIELDS
    }
    for field in ("商品编号", "商品名称", "品类", "购入日期", "成色", "上架状态"):
        if not result[field]:
            raise ValueError(f"{field}不能为空")
        if len(result[field]) > 120:
            raise ValueError(f"{field}长度不能超过 120 个字符")
    if len(result["备注"]) > 2000:
        raise ValueError("备注不能超过 2000 个字符")
    if result["品类"] not in CATEGORIES:
        raise ValueError("品类不在内置列表中")
    if result["成色"] not in CONDITIONS:
        raise ValueError("成色不在内置列表中")
    if result["上架状态"] not in STATUSES:
        raise ValueError("上架状态不在内置列表中")
    try:
        parsed = date.fromisoformat(result["购入日期"])
    except ValueError as exc:
        raise ValueError("购入日期必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != result["购入日期"]:
        raise ValueError("购入日期必须使用 YYYY-MM-DD 格式")
    if parsed > date.today():
        raise ValueError("购入日期不能晚于今天")

    for field in AMOUNT_FIELDS:
        value = _decimal(result[field], field, allow_blank=True)
        value = Decimal("0") if value is None else value
        if value < 0:
            raise ValueError(f"{field}不能为负数")
        result[field] = _money(value, field)
    if Decimal(result["原价(元)"]) <= 0:
        raise ValueError("原价(元)必须大于 0")
    if Decimal(result["配件/瑕疵扣减(元)"]) > Decimal(result["原价(元)"]):
        raise ValueError("配件/瑕疵扣减不能超过原价")

    fee_rate = _decimal(result["平台费率(%)"], "平台费率", allow_blank=True)
    fee_rate = Decimal("0") if fee_rate is None else fee_rate
    if fee_rate < 0 or fee_rate >= 100:
        raise ValueError("平台费率必须在 0–100% 之间，且小于 100%")
    result["平台费率(%)"] = _money(fee_rate, "平台费率")

    buffer = _decimal(result["议价空间(%)"], "议价空间", allow_blank=True)
    buffer = Decimal("8") if buffer is None else buffer
    if buffer < 0 or buffer > 50:
        raise ValueError("议价空间必须在 0–50% 之间")
    result["议价空间(%)"] = _money(buffer, "议价空间")
    return result


def calculate_price(row: dict, as_of: date | None = None) -> dict:
    item = normalize_item_row(row)
    months = age_in_months(item["购入日期"], as_of=as_of)
    depreciation = depreciation_factor(item["品类"], months)
    condition = CONDITION_FACTORS[item["成色"]]
    original = Decimal(item["原价(元)"])
    deduction = Decimal(item["配件/瑕疵扣减(元)"])
    model_value = max(Decimal("0"), original * depreciation * condition - deduction)

    comparable = Decimal(item["同类成交中位价(元)"])
    if comparable > 0:
        reference_value = model_value * Decimal("0.40") + comparable * Decimal("0.60")
        source = "版本化折旧模型 40% + 手工录入同类成交中位价 60%"
    else:
        reference_value = model_value
        source = f"版本化折旧规则 {RULESET_VERSION}；未录入同类成交价"

    purchase_cost = Decimal(item["购入成本(元)"])
    refurbishment = Decimal(item["整备费用(元)"])
    packing_shipping = Decimal(item["包装运费(元)"])
    after_sales_reserve = Decimal(item["售后预留(元)"])
    fixed_fee = Decimal(item["平台固定费用(元)"])
    target_profit = Decimal(item["目标利润(元)"])
    fee_rate = Decimal(item["平台费率(%)"]) / Decimal("100")
    fixed_cost = purchase_cost + refurbishment + packing_shipping + after_sales_reserve + fixed_fee
    denominator = Decimal("1") - fee_rate
    if denominator <= 0:
        raise ValueError("平台费率导致保本价格无效")
    minimum_price = _ceil_cent((fixed_cost + target_profit) / denominator)
    if minimum_price > MAX_NUMERIC_ABS:
        raise ValueError("最低接受价超出支持范围，请检查成本和平台费率")
    negotiation = Decimal(item["议价空间(%)"]) / Decimal("100")
    listing_price = _ceil_yuan(max(reference_value, minimum_price) * (Decimal("1") + negotiation))
    if listing_price > MAX_NUMERIC_ABS:
        raise ValueError("建议标价超出支持范围")
    listing_profit = listing_price * denominator - fixed_cost
    floor_profit = minimum_price * denominator - fixed_cost
    margin = (
        listing_profit / listing_price * Decimal("100")
        if listing_price > 0 else Decimal("0")
    )
    return {
        "规则版本": RULESET_VERSION,
        "使用月数": months,
        "折旧系数": format(depreciation, "f"),
        "成色系数": format(condition, "f"),
        "折旧模型估值(元)": _money(model_value, "折旧模型估值"),
        "估值基准(元)": _money(reference_value, "估值基准"),
        "估值口径": source,
        "建议标价(元)": _money(listing_price, "建议标价"),
        "最低接受价(元)": _money(minimum_price, "最低接受价"),
        "标价预计净利润(元)": _money(listing_profit, "标价预计净利润"),
        "最低价预计净利润(元)": _money(floor_profit, "最低价预计净利润"),
        "标价预计净利率(%)": _money(margin, "标价预计净利率"),
    }


def generate_listing_text(row: dict, as_of: date | None = None) -> str:
    item = normalize_item_row(row)
    result = calculate_price(item, as_of=as_of)
    return (
        f"【{item['商品名称']}】\n"
        f"品类：{item['品类']}｜成色：{item['成色']}\n"
        f"参考标价：¥{result['建议标价(元)']}\n"
        "请在发布前如实补充配件、瑕疵、保修和发货说明。\n"
        "以上为卖家自行录入数据的定价参考，不代表平台估价或实时成交行情。"
    )


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


class PriceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def validate_rows(rows):
        ids = [row["商品编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("商品编号重复")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            if self.path.stat().st_size > MAX_DATA_BYTES:
                raise ValueError("本地台账超过 100 MiB 安全上限")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
            ):
                raise ValueError("定价台账数据格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("本地台账超过 100000 条记录上限")
            rows = [normalize_item_row(item) for item in payload["items"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"定价台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        if len(items) > MAX_ROWS:
            raise ValueError("单个台账最多保存 100000 条商品记录")
        normalized = [normalize_item_row(row) for row in items]
        self.validate_rows(normalized)
        payload = {
            "format": FORMAT,
            "version": VERSION,
            "ruleset": RULESET_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "items": normalized,
        }
        _atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def add(self, row):
        item = normalize_item_row(row)
        if any(old["商品编号"] == item["商品编号"] for old in self.rows):
            raise ValueError("商品编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, item_id, row):
        item = normalize_item_row(row)
        if item["商品编号"] != item_id:
            raise ValueError("商品编号不能修改")
        index = next((i for i, old in enumerate(self.rows) if old["商品编号"] == item_id), None)
        if index is None:
            raise ValueError("找不到要编辑的商品")
        updated = list(self.rows)
        updated[index] = item
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def delete(self, item_id):
        updated = [row for row in self.rows if row["商品编号"] != item_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的商品")
        self.save(updated)
        self.rows = updated

    def import_csv(self, path):
        incoming = []
        if Path(path).stat().st_size > MAX_DATA_BYTES:
            raise ValueError("CSV 文件超过 100 MiB 安全上限")
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
                    incoming.append(normalize_item_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
                if len(incoming) > MAX_ROWS:
                    raise ValueError("单次最多导入 100000 条商品记录")
        self.validate_rows(incoming)
        existing = {row["商品编号"] for row in self.rows}
        duplicates = existing.intersection(row["商品编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在商品编号，整批未导入：" + "、".join(sorted(duplicates)))
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
        if len(self.rows) > MAX_ROWS:
            raise ValueError("商品记录超过 100000 条，不能创建备份")
        items = [dict(row) for row in self.rows]
        canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload = {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "ruleset": RULESET_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "items": items,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }
        _atomic_write(Path(path), json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def restore(self, path):
        try:
            backup_path = Path(path)
            if backup_path.stat().st_size > MAX_DATA_BYTES:
                raise ValueError("备份文件超过 100 MiB 安全上限")
            payload = json.loads(backup_path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
                or not isinstance(payload.get("sha256"), str)
            ):
                raise ValueError("备份文件格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("备份超过 100000 条记录上限")
            canonical = json.dumps(payload["items"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            actual = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(actual, payload["sha256"]):
                raise ValueError("备份 SHA256 校验失败，当前数据未修改")
            rows = [normalize_item_row(item) for item in payload["items"]]
            self.validate_rows(rows)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"恢复失败，当前数据未修改：{exc}") from exc
        self.save(rows)
        self.rows = rows


def category_summary(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        item = normalize_item_row(row)
        calc = calculate_price(item)
        bucket = grouped.setdefault(item["品类"], {
            "品类": item["品类"], "商品数": 0,
            "建议标价合计(元)": Decimal("0"),
            "最低接受价合计(元)": Decimal("0"),
        })
        bucket["商品数"] += 1
        bucket["建议标价合计(元)"] += Decimal(calc["建议标价(元)"])
        bucket["最低接受价合计(元)"] += Decimal(calc["最低接受价(元)"])
    return {
        key: {
            "品类": value["品类"],
            "商品数": value["商品数"],
            "建议标价合计(元)": _money(value["建议标价合计(元)"], "建议标价合计"),
            "最低接受价合计(元)": _money(value["最低接受价合计(元)"], "最低接受价合计"),
        }
        for key, value in grouped.items()
    }


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "xianyu_used_pricing.json"


def self_test():
    import tempfile

    sample = {
        "商品编号": "XY-P-TEST-001", "商品名称": "测试手机", "品类": "手机数码",
        "购入日期": "2025-11-17", "原价(元)": "1000", "购入成本(元)": "400",
        "成色": "9成新", "配件/瑕疵扣减(元)": "20", "整备费用(元)": "20",
        "包装运费(元)": "10", "售后预留(元)": "5", "平台费率(%)": "1",
        "平台固定费用(元)": "0.5", "目标利润(元)": "100", "议价空间(%)": "8",
        "同类成交中位价(元)": "600", "上架状态": "待上架", "备注": "",
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = PriceStore(root / "items.json")
        store.add(sample)
        result = calculate_price(sample, as_of=date(2026, 11, 17))
        assert result["折旧系数"] == "0.78"
        assert result["成色系数"] == "0.86"
        assert result["估值基准(元)"] == "620.32"
        assert result["最低价预计净利润(元)"] == "100.00"
        assert result["建议标价(元)"] == "670.00"
        csv_path = root / "items.csv"
        store.export_csv(csv_path)
        imported = PriceStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup = root / "items-backup.json"
        store.backup(backup)
        restored = PriceStore(root / "restored.json")
        restored.restore(backup)
        assert restored.rows == store.rows
    print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    self_test()
