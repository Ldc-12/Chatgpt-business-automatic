"""Offline Xianyu listing lifecycle ledger with local CSV and backup support."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse

FORMAT = "mainland-xianyu-listing-ledger"
BACKUP_FORMAT = "mainland-xianyu-listing-ledger-backup"
VERSION = 1
RULESET_VERSION = "XY-LISTING-2026.11"
MAX_ROWS = 50000
MAX_DATA_BYTES = 50 * 1024 * 1024
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64

CATEGORIES = (
    "手机数码", "电脑办公", "家用电器", "家具家居",
    "运动户外", "母婴用品", "服饰鞋包", "工具设备", "其他",
)
CONDITIONS = ("全新未拆封", "近全新", "9成新", "8成新", "7成新", "明显瑕疵")
STATUSES = ("草稿", "待上架", "已上架", "已暂停", "已售出", "已下架")
STATUS_TRANSITIONS = {
    "草稿": {"草稿", "待上架", "已下架"},
    "待上架": {"待上架", "草稿", "已上架", "已下架"},
    "已上架": {"已上架", "已暂停", "已售出", "已下架"},
    "已暂停": {"已暂停", "已上架", "已售出", "已下架"},
    "已下架": {"已下架", "待上架", "已售出"},
    "已售出": {"已售出"},
}
FIELDS = (
    "商品编号", "商品名称", "品类", "成色", "SKU/库存位",
    "标价(元)", "最低接受价(元)", "库存数量", "上架状态",
    "计划上架日期", "实际上架日期", "最后刷新日期", "刷新间隔(天)",
    "商品链接", "瑕疵/配件说明", "备注",
)
TEXT_FIELDS = {
    "商品编号", "商品名称", "品类", "成色", "SKU/库存位",
    "上架状态", "计划上架日期", "实际上架日期", "最后刷新日期",
    "商品链接", "瑕疵/配件说明", "备注",
}


def _decimal(value, label: str, allow_blank: bool = False) -> Decimal | None:
    raw = str(value if value is not None else "").strip()
    raw = raw.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    if not raw:
        if allow_blank:
            return None
        raise ValueError(f"{label}不能为空")
    if len(raw) > MAX_NUMERIC_TEXT_LENGTH:
        raise ValueError(f"{label}输入过长")
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not result.is_finite() or abs(result) > MAX_NUMERIC_ABS:
        raise ValueError(f"{label}超出支持范围")
    return result


def _money(value: Decimal, label: str) -> str:
    try:
        return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出人民币分位精度范围") from exc


def _optional_date(value, label: str, today: date, allow_future: bool = False) -> str:
    raw = str(value if value is not None else "").strip()
    if not raw:
        return ""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式")
    if not allow_future and parsed > today:
        raise ValueError(f"{label}不能晚于今天")
    return parsed.isoformat()


def normalize_row(row: dict, today: date | None = None) -> dict:
    if not isinstance(row, dict):
        raise ValueError("商品记录必须是对象")
    today = today or date.today()
    item = {
        field: str("" if row.get(field) is None else row.get(field, "")).strip()
        for field in FIELDS
    }
    for field in ("商品编号", "商品名称", "品类", "成色", "上架状态"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    limits = {
        "商品编号": 80, "商品名称": 120, "SKU/库存位": 120,
        "商品链接": 500, "瑕疵/配件说明": 2000, "备注": 2000,
    }
    for field, limit in limits.items():
        if len(item[field]) > limit:
            raise ValueError(f"{field}长度不能超过 {limit} 个字符")
    if item["品类"] not in CATEGORIES:
        raise ValueError("品类不在内置列表中")
    if item["成色"] not in CONDITIONS:
        raise ValueError("成色不在内置列表中")
    if item["上架状态"] not in STATUSES:
        raise ValueError("上架状态不在内置列表中")

    item["计划上架日期"] = _optional_date(
        item["计划上架日期"], "计划上架日期", today, allow_future=True
    )
    item["实际上架日期"] = _optional_date(
        item["实际上架日期"], "实际上架日期", today
    )
    item["最后刷新日期"] = _optional_date(
        item["最后刷新日期"], "最后刷新日期", today
    )
    if (
        item["实际上架日期"] and item["最后刷新日期"]
        and item["最后刷新日期"] < item["实际上架日期"]
    ):
        raise ValueError("最后刷新日期不能早于实际上架日期")

    price = _decimal(item["标价(元)"], "标价")
    floor = _decimal(item["最低接受价(元)"], "最低接受价", allow_blank=True)
    floor = Decimal("0") if floor is None else floor
    if price <= 0:
        raise ValueError("标价必须大于 0")
    if floor < 0:
        raise ValueError("最低接受价不能为负数")
    if floor > price:
        raise ValueError("最低接受价不能高于标价")
    item["标价(元)"] = _money(price, "标价")
    item["最低接受价(元)"] = _money(floor, "最低接受价")

    quantity_raw = item["库存数量"] or "1"
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("库存数量必须是整数") from exc
    if str(quantity) != quantity_raw and quantity_raw not in (f"+{quantity}",):
        raise ValueError("库存数量必须是整数")
    if quantity < 0 or quantity > 100000:
        raise ValueError("库存数量必须在 0–100000 之间")
    item["库存数量"] = str(quantity)

    interval_raw = item["刷新间隔(天)"] or "7"
    try:
        interval = int(interval_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("刷新间隔必须是整数") from exc
    if str(interval) != interval_raw:
        raise ValueError("刷新间隔必须是整数")
    if interval < 1 or interval > 365:
        raise ValueError("刷新间隔必须在 1–365 天之间")
    item["刷新间隔(天)"] = str(interval)

    if item["商品链接"]:
        parsed = urlparse(item["商品链接"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("商品链接只接受完整的 http/https 地址")
    return item


def refresh_due_info(row: dict, as_of: date | None = None) -> dict:
    today = as_of or date.today()
    item = normalize_row(row, today=today)
    if item["上架状态"] != "已上架":
        return {"due": False, "next_refresh_date": "", "days_until": None}
    base = item["最后刷新日期"] or item["实际上架日期"]
    if not base:
        return {"due": False, "next_refresh_date": "", "days_until": None}
    next_date = date.fromisoformat(base) + timedelta(days=int(item["刷新间隔(天)"]))
    days_until = (next_date - today).days
    return {
        "due": days_until <= 0,
        "next_refresh_date": next_date.isoformat(),
        "days_until": days_until,
    }


def listing_summary(rows: list[dict], as_of: date | None = None) -> dict:
    today = as_of or date.today()
    counts = {status: 0 for status in STATUSES}
    due_items = []
    total_stock = 0
    listed_value = Decimal("0")
    for raw in rows:
        item = normalize_row(raw, today=today)
        counts[item["上架状态"]] += 1
        total_stock += int(item["库存数量"])
        if item["上架状态"] == "已上架":
            listed_value += Decimal(item["标价(元)"]) * int(item["库存数量"])
        info = refresh_due_info(item, as_of=today)
        if info["due"]:
            due_items.append({
                "商品编号": item["商品编号"],
                "商品名称": item["商品名称"],
                "下次刷新日期": info["next_refresh_date"],
            })
    due_items.sort(key=lambda row: (row["下次刷新日期"], row["商品编号"]))
    return {
        "商品总数": len(rows),
        "状态数量": counts,
        "库存总量": total_stock,
        "待刷新数量": len(due_items),
        "待刷新商品": due_items,
        "在售标价库存额(元)": _money(listed_value, "在售标价库存额"),
    }


def generate_listing_text(row: dict) -> str:
    item = normalize_row(row)
    lines = [
        f"【{item['商品名称']}】",
        f"品类：{item['品类']}｜成色：{item['成色']}",
        f"标价：¥{item['标价(元)']}",
        f"库存：{item['库存数量']} 件",
    ]
    if item["瑕疵/配件说明"]:
        lines.append("配件/瑕疵说明：" + item["瑕疵/配件说明"])
    lines.append("请按实物情况核对成色、配件、瑕疵和发货信息。")
    lines.append("本内容由卖家录入数据生成，请发布前人工检查。")
    return "\n".join(lines)


def _safe_csv_text(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
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


class ListingStore:
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
                raise ValueError("本地台账超过 50 MiB 安全上限")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
            ):
                raise ValueError("发布台账数据格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("本地台账超过 50000 条记录上限")
            rows = [normalize_row(row) for row in payload["items"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"发布台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        if len(items) > MAX_ROWS:
            raise ValueError("单个台账最多保存 50000 条商品记录")
        normalized = [normalize_row(row) for row in items]
        self.validate_rows(normalized)
        payload = {
            "format": FORMAT,
            "version": VERSION,
            "ruleset": RULESET_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "items": normalized,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_DATA_BYTES:
            raise ValueError("本地台账序列化后超过 50 MiB 安全上限")
        _atomic_write(self.path, data)

    def add(self, row):
        item = normalize_row(row)
        if any(old["商品编号"] == item["商品编号"] for old in self.rows):
            raise ValueError("商品编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, item_id, row):
        item = normalize_row(row)
        if item["商品编号"] != item_id:
            raise ValueError("商品编号不能修改")
        index = next(
            (i for i, old in enumerate(self.rows) if old["商品编号"] == item_id),
            None,
        )
        if index is None:
            raise ValueError("找不到要编辑的商品")
        current = self.rows[index]
        if item["上架状态"] != current["上架状态"]:
            if item["上架状态"] not in STATUS_TRANSITIONS[current["上架状态"]]:
                raise ValueError(
                    f"不允许从“{current['上架状态']}”变更为“{item['上架状态']}”"
                )
            if item["上架状态"] == "已上架" and not item["实际上架日期"]:
                item["实际上架日期"] = date.today().isoformat()
                item = normalize_row(item)
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

    def transition_status(self, item_id, new_status):
        row = next((item for item in self.rows if item["商品编号"] == item_id), None)
        if row is None:
            raise ValueError("找不到要变更状态的商品")
        if new_status not in STATUSES:
            raise ValueError("上架状态不在内置列表中")
        changed = dict(row, **{"上架状态": new_status})
        self.update(item_id, changed)

    def mark_refreshed(self, item_id, refreshed_on: date | None = None):
        row = next((item for item in self.rows if item["商品编号"] == item_id), None)
        if row is None:
            raise ValueError("找不到要刷新的商品")
        if row["上架状态"] != "已上架":
            raise ValueError("只有已上架商品才能记录刷新日期")
        changed = dict(
            row,
            **{"最后刷新日期": (refreshed_on or date.today()).isoformat()},
        )
        self.update(item_id, changed)

    def import_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_DATA_BYTES:
            raise ValueError("CSV 文件超过 50 MiB 安全上限")
        incoming = []
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(FIELDS):
                raise ValueError("CSV 表头必须与软件导出的字段和顺序完全一致")
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余字段")
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
                if len(incoming) > MAX_ROWS:
                    raise ValueError("单次最多导入 50000 条商品记录")
        self.validate_rows(incoming)
        existing = {row["商品编号"] for row in self.rows}
        duplicates = existing.intersection(row["商品编号"] for row in incoming)
        if duplicates:
            raise ValueError(
                "导入包含已存在商品编号，整批未导入：" + "、".join(sorted(duplicates))
            )
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
            raise ValueError("商品记录超过 50000 条，不能创建备份")
        items = [dict(row) for row in self.rows]
        canonical = json.dumps(
            items, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload = {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "ruleset": RULESET_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "items": items,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_DATA_BYTES:
            raise ValueError("备份序列化后超过 50 MiB 安全上限")
        _atomic_write(Path(path), data)

    def restore(self, path):
        try:
            backup_path = Path(path)
            if backup_path.stat().st_size > MAX_DATA_BYTES:
                raise ValueError("备份文件超过 50 MiB 安全上限")
            payload = json.loads(backup_path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
            ):
                raise ValueError("备份格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("备份超过 50000 条记录上限")
            canonical = json.dumps(
                payload["items"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            expected = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(str(payload.get("sha256", "")), expected):
                raise ValueError("备份 SHA256 校验失败")
            restored = [normalize_row(row) for row in payload["items"]]
            self.validate_rows(restored)
            self.save(restored)
            self.rows = restored
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"备份恢复失败，当前台账未替换：{exc}") from exc


def default_data_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or Path.home())
    return base / "MainlandBusinessTools" / "xianyu_listing_ledger.json"


def self_test() -> None:
    from tempfile import TemporaryDirectory

    today = date.today()
    sample = {
        "商品编号": "XY-L-SELF-001",
        "商品名称": "自检二手手机",
        "品类": "手机数码",
        "成色": "9成新",
        "SKU/库存位": "A-01",
        "标价(元)": "680",
        "最低接受价(元)": "500",
        "库存数量": "1",
        "上架状态": "已上架",
        "计划上架日期": "",
        "实际上架日期": (today - timedelta(days=8)).isoformat(),
        "最后刷新日期": (today - timedelta(days=8)).isoformat(),
        "刷新间隔(天)": "7",
        "商品链接": "",
        "瑕疵/配件说明": "含充电线",
        "备注": "仅用于自检",
    }
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = ListingStore(root / "items.json")
        store.add(sample)
        assert listing_summary(store.rows, as_of=today)["待刷新数量"] == 1
        csv_path = root / "items.csv"
        store.export_csv(csv_path)
        imported = ListingStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup_path = root / "items.backup.json"
        store.backup(backup_path)
        restored = ListingStore(root / "restored.json")
        restored.restore(backup_path)
        assert restored.rows == store.rows
        store.mark_refreshed("XY-L-SELF-001", refreshed_on=today)
        assert listing_summary(store.rows, as_of=today)["待刷新数量"] == 0
    print("SELF_TEST_OK", flush=True)
