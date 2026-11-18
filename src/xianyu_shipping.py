"""Offline Xianyu dispatch and delivery ledger with safe CSV and SHA256 backups."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-xianyu-shipping-ledger"
BACKUP_FORMAT = "mainland-xianyu-shipping-ledger-backup"
VERSION = 1
RULESET_VERSION = "XY-SHIPPING-2026.11"
MAX_ROWS = 50000
MAX_DATA_BYTES = 50 * 1024 * 1024
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64

CARRIERS = (
    "顺丰速运", "中通快递", "圆通速递", "申通快递", "韵达速递",
    "极兔速递", "中国邮政", "邮政EMS", "京东物流", "德邦快递", "其他",
)
STATUSES = ("待打包", "待揽收", "运输中", "派送中", "已签收", "异常", "已取消")
STATUS_TRANSITIONS = {
    "待打包": {"待打包", "待揽收", "异常", "已取消"},
    "待揽收": {"待揽收", "运输中", "异常", "已取消"},
    "运输中": {"运输中", "派送中", "已签收", "异常"},
    "派送中": {"派送中", "已签收", "异常"},
    "异常": {"异常", "待揽收", "运输中", "派送中", "已签收", "已取消"},
    "已签收": {"已签收"},
    "已取消": {"已取消"},
}
FIELDS = (
    "发货编号", "订单编号", "商品/SKU", "买家备注", "承运商", "运单号",
    "下单日期", "承诺发货日期", "实际发货日期", "揽收确认日期",
    "预计送达日期", "签收日期", "物流状态", "包裹重量(kg)",
    "运费(元)", "异常说明", "备注",
)
TEXT_FIELDS = {
    "发货编号", "订单编号", "商品/SKU", "买家备注", "承运商", "运单号",
    "下单日期", "承诺发货日期", "实际发货日期", "揽收确认日期",
    "预计送达日期", "签收日期", "物流状态", "异常说明", "备注",
}
PERFORMANCE_FIELDS = (
    "承运商", "发货单数", "已签收单数", "准时评估单数", "准时签收单数",
    "逾期签收单数", "未设置预计送达单数", "异常件数", "准时率(%)",
    "平均揽收到签收天数", "累计运费(元)", "已签收运费(元)",
)


def _decimal(value, label: str, *, allow_blank: bool = False) -> Decimal | None:
    raw = str(value if value is not None else "").strip()
    raw = raw.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    if not raw:
        if allow_blank:
            return None
        raise ValueError(f"{label}不能为空")
    if len(raw) > MAX_NUMERIC_TEXT_LENGTH:
        raise ValueError(f"{label}输入过长")
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not number.is_finite():
        raise ValueError(f"{label}必须是有效数字")
    if abs(number) > MAX_NUMERIC_ABS:
        raise ValueError(f"{label}超出支持范围")
    return number


def _money(value: Decimal, label: str) -> str:
    try:
        return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出金额精度范围") from exc


def _date(value, label: str, today: date, *, allow_future: bool = False) -> str:
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
        raise ValueError("发货记录必须是对象")
    today = today or date.today()
    item = {
        field: str("" if row.get(field) is None else row.get(field, "")).strip()
        for field in FIELDS
    }
    for field in ("发货编号", "订单编号", "商品/SKU", "承诺发货日期", "物流状态"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    limits = {
        "发货编号": 80, "订单编号": 120, "商品/SKU": 160,
        "买家备注": 500, "承运商": 60, "运单号": 120,
        "异常说明": 2000, "备注": 2000,
    }
    for field, limit in limits.items():
        if len(item[field]) > limit:
            raise ValueError(f"{field}长度不能超过 {limit} 个字符")
    if item["物流状态"] not in STATUSES:
        raise ValueError("物流状态不在内置列表中")
    if item["承运商"] and item["承运商"] not in CARRIERS and len(item["承运商"]) > 60:
        raise ValueError("承运商名称长度不能超过 60 个字符")

    item["下单日期"] = _date(item["下单日期"], "下单日期", today)
    item["承诺发货日期"] = _date(
        item["承诺发货日期"], "承诺发货日期", today, allow_future=True
    )
    for field in ("实际发货日期", "揽收确认日期", "签收日期"):
        item[field] = _date(item[field], field, today)
    item["预计送达日期"] = _date(
        item["预计送达日期"], "预计送达日期", today, allow_future=True
    )
    if item["下单日期"] and item["承诺发货日期"] < item["下单日期"]:
        raise ValueError("承诺发货日期不能早于下单日期")
    if item["实际发货日期"] and item["下单日期"] and item["实际发货日期"] < item["下单日期"]:
        raise ValueError("实际发货日期不能早于下单日期")
    if item["揽收确认日期"] and not item["实际发货日期"]:
        raise ValueError("揽收确认日期需要先填写实际发货日期")
    if item["揽收确认日期"] and item["揽收确认日期"] < item["实际发货日期"]:
        raise ValueError("揽收确认日期不能早于实际发货日期")
    delivery_base = item["揽收确认日期"] or item["实际发货日期"]
    if item["预计送达日期"] and delivery_base and item["预计送达日期"] < delivery_base:
        raise ValueError("预计送达日期不能早于发货或揽收日期")
    if item["签收日期"]:
        if not delivery_base:
            raise ValueError("签收日期需要先填写实际发货和揽收日期")
        if item["签收日期"] < delivery_base:
            raise ValueError("签收日期不能早于发货或揽收日期")

    status = item["物流状态"]
    if status in {"待揽收", "运输中", "派送中", "已签收"}:
        for field in ("承运商", "运单号", "实际发货日期"):
            if not item[field]:
                raise ValueError(f"{status}状态必须填写{field}")
    if status in {"运输中", "派送中", "已签收"} and not item["揽收确认日期"]:
        raise ValueError(f"{status}状态必须填写揽收确认日期")
    if status == "已签收" and not item["签收日期"]:
        raise ValueError("已签收状态必须填写签收日期")
    if status == "异常" and not item["异常说明"]:
        raise ValueError("异常状态必须填写异常说明")
    if status == "已取消" and (item["揽收确认日期"] or item["签收日期"]):
        raise ValueError("已揽收或已签收的包裹不能直接标记为已取消")

    weight = _decimal(item["包裹重量(kg)"], "包裹重量", allow_blank=True)
    weight = Decimal("0") if weight is None else weight
    if weight < 0 or weight > Decimal("1000"):
        raise ValueError("包裹重量必须在 0–1000 kg 之间")
    item["包裹重量(kg)"] = format(weight.quantize(Decimal("0.001")), "f").rstrip("0").rstrip(".") or "0"
    freight = _decimal(item["运费(元)"], "运费", allow_blank=True)
    freight = Decimal("0") if freight is None else freight
    if freight < 0:
        raise ValueError("运费不能为负数")
    item["运费(元)"] = _money(freight, "运费")
    return item


def shipping_risk(row: dict, as_of: date | None = None) -> dict:
    today = as_of or date.today()
    item = normalize_row(row, today=today)
    status = item["物流状态"]
    dispatch_due = (
        status == "待打包"
        and date.fromisoformat(item["承诺发货日期"]) <= today
    )
    awaiting_pickup = status == "待揽收"
    overdue_delivery = (
        status in {"运输中", "派送中"}
        and bool(item["预计送达日期"])
        and date.fromisoformat(item["预计送达日期"]) < today
    )
    late_days = (
        (today - date.fromisoformat(item["预计送达日期"])).days
        if overdue_delivery else 0
    )
    if dispatch_due:
        label = "发货逾期"
    elif awaiting_pickup:
        label = "等待揽收"
    elif overdue_delivery:
        label = f"预计送达逾期 {late_days} 天"
    elif status == "异常":
        label = "物流异常待处理"
    else:
        label = ""
    return {
        "发货逾期": dispatch_due,
        "等待揽收": awaiting_pickup,
        "送达逾期": overdue_delivery,
        "逾期天数": late_days,
        "提醒": label,
    }


def shipping_summary(rows: list[dict], as_of: date | None = None) -> dict:
    today = as_of or date.today()
    counts = {status: 0 for status in STATUSES}
    late_dispatch, awaiting_pickup, late_delivery, exceptions = [], [], [], []
    freight_total = Decimal("0")
    for raw in rows:
        item = normalize_row(raw, today=today)
        counts[item["物流状态"]] += 1
        freight_total += Decimal(item["运费(元)"])
        risk = shipping_risk(item, as_of=today)
        if risk["发货逾期"]:
            late_dispatch.append(item)
        if risk["等待揽收"]:
            awaiting_pickup.append(item)
        if risk["送达逾期"]:
            late_delivery.append(item)
        if item["物流状态"] == "异常":
            exceptions.append(item)
    sort_key = lambda item: (item["承诺发货日期"], item["订单编号"])
    late_dispatch.sort(key=sort_key)
    awaiting_pickup.sort(key=lambda item: (item["实际发货日期"], item["订单编号"]))
    late_delivery.sort(key=lambda item: (item["预计送达日期"], item["订单编号"]))
    return {
        "发货总数": len(rows),
        "状态数量": counts,
        "发货逾期数量": len(late_dispatch),
        "等待揽收数量": len(awaiting_pickup),
        "送达逾期数量": len(late_delivery),
        "异常件数量": len(exceptions),
        "累计运费(元)": _money(freight_total, "累计运费"),
        "发货逾期清单": late_dispatch,
        "等待揽收清单": awaiting_pickup,
        "送达逾期清单": late_delivery,
        "异常件清单": exceptions,
    }


def carrier_performance(rows: list[dict]) -> dict:
    """Summarize carrier performance from seller-entered, signed delivery records.

    On-time rate excludes signed records without an estimated delivery date.
    Transit duration is measured from pickup confirmation to signed date.
    """
    groups = {}
    unassigned = 0
    for raw in rows:
        item = normalize_row(raw)
        carrier = item["承运商"]
        if not carrier:
            unassigned += 1
            continue
        stat = groups.setdefault(carrier, {
            "承运商": carrier,
            "发货单数": 0,
            "已签收单数": 0,
            "准时评估单数": 0,
            "准时签收单数": 0,
            "逾期签收单数": 0,
            "未设置预计送达单数": 0,
            "异常件数": 0,
            "_累计运费": Decimal("0"),
            "_已签收运费": Decimal("0"),
            "_揽收到签收天数": 0,
        })
        stat["发货单数"] += 1
        stat["_累计运费"] += Decimal(item["运费(元)"])
        if item["物流状态"] == "异常":
            stat["异常件数"] += 1
        if item["物流状态"] != "已签收":
            continue
        stat["已签收单数"] += 1
        stat["_已签收运费"] += Decimal(item["运费(元)"])
        pickup = date.fromisoformat(item["揽收确认日期"])
        signed = date.fromisoformat(item["签收日期"])
        stat["_揽收到签收天数"] += (signed - pickup).days
        expected = item["预计送达日期"]
        if not expected:
            stat["未设置预计送达单数"] += 1
            continue
        stat["准时评估单数"] += 1
        if signed <= date.fromisoformat(expected):
            stat["准时签收单数"] += 1
        else:
            stat["逾期签收单数"] += 1

    details = []
    for carrier, stat in groups.items():
        assessed = stat["准时评估单数"]
        delivered = stat["已签收单数"]
        on_time_rate = ""
        if assessed:
            rate = (
                Decimal(stat["准时签收单数"]) * Decimal("100")
                / Decimal(assessed)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            on_time_rate = format(rate, "f")
        average_days = ""
        if delivered:
            average = (
                Decimal(stat["_揽收到签收天数"]) / Decimal(delivered)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            average_days = format(average, "f")
        details.append({
            "承运商": carrier,
            "发货单数": stat["发货单数"],
            "已签收单数": delivered,
            "准时评估单数": assessed,
            "准时签收单数": stat["准时签收单数"],
            "逾期签收单数": stat["逾期签收单数"],
            "未设置预计送达单数": stat["未设置预计送达单数"],
            "异常件数": stat["异常件数"],
            "准时率(%)": on_time_rate,
            "平均揽收到签收天数": average_days,
            "累计运费(元)": _money(stat["_累计运费"], "累计运费"),
            "已签收运费(元)": _money(stat["_已签收运费"], "已签收运费"),
        })
    details.sort(key=lambda item: (-item["发货单数"], item["承运商"]))
    return {
        "承运商数量": len(details),
        "未填写承运商单数": unassigned,
        "承运商明细": details,
    }


def export_carrier_performance_csv(rows: list[dict], path: str | Path) -> int:
    report = carrier_performance(rows)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PERFORMANCE_FIELDS, extrasaction="raise")
    writer.writeheader()
    for row in report["承运商明细"]:
        writer.writerow({
            field: _safe_csv_text(row[field]) if field == "承运商" else row[field]
            for field in PERFORMANCE_FIELDS
        })
    _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
    return len(report["承运商明细"])



ATTENTION_FIELDS = (
    "发货编号", "订单编号", "商品/SKU", "承运商", "运单号",
    "承诺发货日期", "实际发货日期", "揽收确认日期", "预计送达日期",
    "物流状态", "待处理类型", "提醒", "逾期天数", "异常说明",
)
ATTENTION_TEXT_FIELDS = set(ATTENTION_FIELDS) - {"逾期天数"}


def export_shipping_attention_csv(
    rows: list[dict], path: str | Path, as_of: date | None = None
) -> int:
    """Export only shipments that need seller follow-up, without changing source rows."""
    today = as_of or date.today()
    priority = {"发货逾期": 0, "物流异常": 1, "送达逾期": 2, "等待揽收": 3}
    attention = []
    for raw in rows:
        item = normalize_row(raw, today=today)
        risk = shipping_risk(item, as_of=today)
        if risk["发货逾期"]:
            kind = "发货逾期"
        elif risk["等待揽收"]:
            kind = "等待揽收"
        elif risk["送达逾期"]:
            kind = "送达逾期"
        elif item["物流状态"] == "异常":
            kind = "物流异常"
        else:
            continue
        record = {field: item[field] for field in ATTENTION_FIELDS}
        record["待处理类型"] = kind
        record["提醒"] = risk["提醒"]
        record["逾期天数"] = (
            (today - date.fromisoformat(item["承诺发货日期"])).days
            if kind == "发货逾期"
            else risk["逾期天数"] if kind == "送达逾期" else ""
        )
        attention.append(record)

    attention.sort(key=lambda row: (
        priority[row["待处理类型"]],
        row["承诺发货日期"] or row["预计送达日期"] or "9999-12-31",
        row["订单编号"],
    ))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=ATTENTION_FIELDS, extrasaction="raise")
    writer.writeheader()
    for row in attention:
        writer.writerow({
            field: _safe_csv_text(row[field])
            if field in ATTENTION_TEXT_FIELDS else row[field]
            for field in ATTENTION_FIELDS
        })
    _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
    return len(attention)


def _safe_csv_text(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    return "'" + text if probe[:1] in ("=", "+", "-", "@") else text


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


class ShippingStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def validate_rows(rows):
        ids = [row["发货编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("发货编号重复")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            if self.path.stat().st_size > MAX_DATA_BYTES:
                raise ValueError("本地发货台账超过 50 MiB 安全上限")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
            ):
                raise ValueError("发货台账数据格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("本地发货台账超过 50000 条记录上限")
            rows = [normalize_row(row) for row in payload["items"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"发货台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        if len(items) > MAX_ROWS:
            raise ValueError("单个台账最多保存 50000 条发货记录")
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
            raise ValueError("本地发货台账序列化后超过 50 MiB 安全上限")
        _atomic_write(self.path, data)

    def add(self, row):
        item = normalize_row(row)
        if any(old["发货编号"] == item["发货编号"] for old in self.rows):
            raise ValueError("发货编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, shipment_id, row, changed_on: date | None = None):
        index = next((i for i, old in enumerate(self.rows) if old["发货编号"] == shipment_id), None)
        if index is None:
            raise ValueError("找不到要编辑的发货记录")
        current = self.rows[index]
        candidate = dict(row)
        if str(candidate.get("发货编号", "")).strip() != shipment_id:
            raise ValueError("发货编号不能修改")
        new_status = str(candidate.get("物流状态", "")).strip()
        if new_status != current["物流状态"]:
            if new_status not in STATUS_TRANSITIONS[current["物流状态"]]:
                raise ValueError(f"不允许从“{current['物流状态']}”变更为“{new_status}”")
            today = (changed_on or date.today()).isoformat()
            if new_status == "待揽收" and not str(candidate.get("实际发货日期", "")).strip():
                candidate["实际发货日期"] = today
            if new_status in {"运输中", "派送中"} and not str(candidate.get("揽收确认日期", "")).strip():
                candidate["揽收确认日期"] = today
            if new_status == "已签收":
                if not str(candidate.get("实际发货日期", "")).strip():
                    candidate["实际发货日期"] = today
                if not str(candidate.get("揽收确认日期", "")).strip():
                    candidate["揽收确认日期"] = today
                if not str(candidate.get("签收日期", "")).strip():
                    candidate["签收日期"] = today
        item = normalize_row(candidate)
        updated = list(self.rows)
        updated[index] = item
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def delete(self, shipment_id):
        updated = [row for row in self.rows if row["发货编号"] != shipment_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的发货记录")
        self.save(updated)
        self.rows = updated

    def transition_status(self, shipment_id, new_status, changed_on: date | None = None):
        row = next((item for item in self.rows if item["发货编号"] == shipment_id), None)
        if row is None:
            raise ValueError("找不到要变更状态的发货记录")
        if new_status not in STATUSES:
            raise ValueError("物流状态不在内置列表中")
        if new_status not in STATUS_TRANSITIONS[row["物流状态"]]:
            raise ValueError(f"不允许从“{row['物流状态']}”变更为“{new_status}”")
        changed = dict(row, **{"物流状态": new_status})
        today = changed_on or date.today()
        if new_status == "待揽收" and not changed["实际发货日期"]:
            changed["实际发货日期"] = today.isoformat()
        if new_status in {"运输中", "派送中"} and not changed["揽收确认日期"]:
            changed["揽收确认日期"] = today.isoformat()
        if new_status == "已签收" and not changed["签收日期"]:
            if not changed["揽收确认日期"]:
                changed["揽收确认日期"] = today.isoformat()
            if not changed["实际发货日期"]:
                changed["实际发货日期"] = today.isoformat()
            changed["签收日期"] = today.isoformat()
        self.update(shipment_id, changed, changed_on=today)

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
                    raise ValueError("单次最多导入 50000 条发货记录")
        self.validate_rows(incoming)
        existing = {row["发货编号"] for row in self.rows}
        duplicates = existing.intersection(row["发货编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在发货编号，整批未导入：" + "、".join(sorted(duplicates)))
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
            canonical = json.dumps(payload["items"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
    return base / "MainlandBusinessTools" / "xianyu_shipping_ledger.json"


def self_test() -> None:
    from tempfile import TemporaryDirectory

    today = date.today()
    sample = {
        "发货编号": "XY-S-SELF-001", "订单编号": "ORDER-SELF-001",
        "商品/SKU": "自检二手手机", "买家备注": "", "承运商": "",
        "运单号": "", "下单日期": today.isoformat(),
        "承诺发货日期": today.isoformat(), "实际发货日期": "",
        "揽收确认日期": "", "预计送达日期": "", "签收日期": "",
        "物流状态": "待打包", "包裹重量(kg)": "0.5", "运费(元)": "0",
        "异常说明": "", "备注": "仅用于自检",
    }
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = ShippingStore(root / "shipping.json")
        store.add(sample)
        assert shipping_summary(store.rows, as_of=today)["发货逾期数量"] == 1
        prepared = dict(store.rows[0], **{"承运商": "顺丰速运", "运单号": "SF-SELF-001"})
        store.update("XY-S-SELF-001", prepared)
        store.transition_status("XY-S-SELF-001", "待揽收", changed_on=today)
        store.transition_status("XY-S-SELF-001", "运输中", changed_on=today)
        store.transition_status("XY-S-SELF-001", "派送中", changed_on=today)
        store.transition_status("XY-S-SELF-001", "已签收", changed_on=today)
        performance = carrier_performance(store.rows)
        assert performance["承运商明细"][0]["已签收单数"] == 1
        analysis_path = root / "carrier-performance.csv"
        assert export_carrier_performance_csv(store.rows, analysis_path) == 1
        csv_path = root / "shipping.csv"
        store.export_csv(csv_path)
        imported = ShippingStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup_path = root / "shipping.backup.json"
        store.backup(backup_path)
        restored = ShippingStore(root / "restored.json")
        restored.restore(backup_path)
        assert restored.rows == store.rows
    print("SELF_TEST_OK", flush=True)
