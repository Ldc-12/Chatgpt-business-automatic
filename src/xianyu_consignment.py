"""Offline Xianyu consignment and owner settlement ledger.

The tool stores only seller-entered records on the local Windows device. It does
not connect to Xianyu, publish listings, contact owners, or move money.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-xianyu-consignment-ledger"
BACKUP_FORMAT = "mainland-xianyu-consignment-ledger-backup"
VERSION = 1
MAX_ROWS = 50000
MAX_BYTES = 50 * 1024 * 1024
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64
STATUSES = ("待上架", "在售", "已售", "已退回", "已取消")
FIELDS = (
    "记录编号", "货主编号", "货主名称", "联系方式备注", "商品编号/SKU",
    "商品名称", "商品成色/瑕疵", "收货日期", "约定上架价(元)",
    "货主约定结算额(元)", "当前标价(元)", "商品状态", "成交日期",
    "实际成交金额(元)", "平台实际费用(元)", "发货运费(元)",
    "包装整备成本(元)", "已结算金额(元)", "结算期限", "最后结算日期",
    "退回日期", "备注",
)
TEXT_FIELDS = {
    "记录编号", "货主编号", "货主名称", "联系方式备注", "商品编号/SKU",
    "商品名称", "商品成色/瑕疵", "收货日期", "商品状态", "成交日期",
    "结算期限", "最后结算日期", "退回日期", "备注",
}
AMOUNT_FIELDS = (
    "约定上架价(元)", "货主约定结算额(元)", "当前标价(元)",
    "实际成交金额(元)", "平台实际费用(元)", "发货运费(元)",
    "包装整备成本(元)", "已结算金额(元)",
)
REQUIRED_AMOUNTS = {"约定上架价(元)", "货主约定结算额(元)"}
DATE_FIELDS = ("收货日期", "成交日期", "结算期限", "最后结算日期", "退回日期")


def _decimal(value, label: str, allow_blank: bool = False) -> Decimal | None:
    raw = str("" if value is None else value).strip()
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
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出人民币分位精度范围") from exc
    return format(rounded, "f")


def _signed_money(value: Decimal, label: str) -> str:
    return ("-" if value < 0 else "") + _money(abs(value), label)


def _date(value, label: str, allow_blank: bool = False) -> str:
    raw = str("" if value is None else value).strip()
    if not raw and allow_blank:
        return ""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式")
    return raw


def normalize_row(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("寄售记录必须是对象")
    row = {
        field: str("" if raw.get(field) is None else raw.get(field, "")).strip()
        for field in FIELDS
    }
    required = (
        "记录编号", "货主编号", "货主名称", "商品编号/SKU",
        "商品名称", "收货日期", "商品状态",
    )
    for field in required:
        if not row[field]:
            raise ValueError(f"{field}不能为空")
        if len(row[field]) > 160:
            raise ValueError(f"{field}长度不能超过 160 个字符")
    limits = {
        "联系方式备注": 240,
        "商品成色/瑕疵": 500,
        "备注": 2000,
    }
    for field, limit in limits.items():
        if len(row[field]) > limit:
            raise ValueError(f"{field}长度不能超过 {limit} 个字符")
    if row["商品状态"] not in STATUSES:
        raise ValueError("商品状态不在内置列表中")

    for field in DATE_FIELDS:
        row[field] = _date(row[field], field, allow_blank=field != "收货日期")

    for field in AMOUNT_FIELDS:
        value = _decimal(
            row[field],
            field,
            allow_blank=field not in REQUIRED_AMOUNTS,
        )
        value = Decimal("0") if value is None else value
        if value < 0:
            raise ValueError(f"{field}不能为负数")
        row[field] = _money(value, field)

    if Decimal(row["约定上架价(元)"]) <= 0:
        raise ValueError("约定上架价必须大于 0")
    if Decimal(row["货主约定结算额(元)"]) <= 0:
        raise ValueError("货主约定结算额必须大于 0")
    if row["商品状态"] == "在售" and Decimal(row["当前标价(元)"]) <= 0:
        raise ValueError("在售商品的当前标价必须大于 0")

    sold = row["商品状态"] == "已售"
    returned = row["商品状态"] == "已退回"
    sale_amount = Decimal(row["实际成交金额(元)"])
    settled = Decimal(row["已结算金额(元)"])
    agreed = Decimal(row["货主约定结算额(元)"])

    if sold:
        if not row["成交日期"] or sale_amount <= 0:
            raise ValueError("已售商品必须填写成交日期和大于 0 的实际成交金额")
        if row["成交日期"] < row["收货日期"]:
            raise ValueError("成交日期不能早于收货日期")
        if row["退回日期"]:
            raise ValueError("已售商品不能同时填写退回日期")
        if row["结算期限"] and row["结算期限"] < row["成交日期"]:
            raise ValueError("结算期限不能早于成交日期")
        if settled > agreed:
            raise ValueError("已结算金额不能超过货主约定结算额")
        if settled > 0:
            if not row["最后结算日期"]:
                raise ValueError("已发生结算时必须填写最后结算日期")
            if row["最后结算日期"] < row["成交日期"]:
                raise ValueError("最后结算日期不能早于成交日期")
        elif row["最后结算日期"]:
            raise ValueError("已结算金额为 0 时不能填写最后结算日期")
    else:
        if sale_amount > 0 or row["成交日期"]:
            raise ValueError("只有已售商品才能填写成交日期或实际成交金额")
        if settled > 0 or row["最后结算日期"]:
            raise ValueError("未售出商品不能登记货主结算")
        if row["结算期限"]:
            raise ValueError("未售出商品不能填写结算期限")

    if returned:
        if not row["退回日期"]:
            raise ValueError("已退回商品必须填写退回日期")
        if row["退回日期"] < row["收货日期"]:
            raise ValueError("退回日期不能早于收货日期")
    elif row["退回日期"]:
        raise ValueError("只有已退回商品才能填写退回日期")

    return row


def calculate_item(raw: dict) -> dict:
    row = normalize_row(raw)
    sold = row["商品状态"] == "已售"
    if sold:
        sale = Decimal(row["实际成交金额(元)"])
        fees = Decimal(row["平台实际费用(元)"])
        freight = Decimal(row["发货运费(元)"])
        preparation = Decimal(row["包装整备成本(元)"])
        agreed = Decimal(row["货主约定结算额(元)"])
        paid = Decimal(row["已结算金额(元)"])
    else:
        # Do not recognize selling costs or margin before an actual sale.
        sale = fees = freight = preparation = agreed = paid = Decimal("0")
    net_proceeds = sale - fees - freight - preparation
    due = agreed - paid
    margin = net_proceeds - agreed
    shortfall = max(Decimal("0"), -margin)
    if not sold:
        settlement_status = "未成交"
    elif due == 0:
        settlement_status = "已结清"
    elif paid > 0:
        settlement_status = "部分结算"
    else:
        settlement_status = "待结算"
    return {
        "商品状态": row["商品状态"],
        "成交净回款(元)": _signed_money(net_proceeds, "成交净回款"),
        "货主应结算金额(元)": _money(agreed, "货主应结算金额"),
        "已结算金额(元)": _money(paid, "已结算金额"),
        "待结算金额(元)": _money(due, "待结算金额"),
        "卖家毛利(元)": _signed_money(margin, "卖家毛利"),
        "回款缺口(元)": _money(shortfall, "回款缺口"),
        "结算状态": settlement_status,
    }


def owner_summary(rows: list[dict], as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    if not isinstance(as_of, date):
        raise ValueError("汇总日期必须是日期对象")
    grouped = {}
    for raw in rows:
        row = normalize_row(raw)
        bucket = grouped.setdefault(row["货主编号"], {
            "货主编号": row["货主编号"],
            "货主名称": row["货主名称"],
            "商品数": 0,
            "已售数": 0,
            "已退回数": 0,
            "应结算金额": Decimal("0"),
            "已结算金额": Decimal("0"),
            "待结算金额": Decimal("0"),
            "卖家毛利": Decimal("0"),
            "逾期待结算数": 0,
        })
        if bucket["货主名称"] != row["货主名称"]:
            raise ValueError(f"同一货主编号对应多个名称：{row['货主编号']}")
        bucket["商品数"] += 1
        bucket["已售数"] += int(row["商品状态"] == "已售")
        bucket["已退回数"] += int(row["商品状态"] == "已退回")
        calc = calculate_item(row)
        if row["商品状态"] == "已售":
            bucket["应结算金额"] += Decimal(calc["货主应结算金额(元)"])
            bucket["已结算金额"] += Decimal(calc["已结算金额(元)"])
            bucket["待结算金额"] += Decimal(calc["待结算金额(元)"])
            bucket["卖家毛利"] += Decimal(calc["卖家毛利(元)"])
            if (
                row["结算期限"]
                and date.fromisoformat(row["结算期限"]) < as_of
                and Decimal(calc["待结算金额(元)"]) > 0
            ):
                bucket["逾期待结算数"] += 1
    return {
        key: {
            "货主编号": value["货主编号"],
            "货主名称": value["货主名称"],
            "商品数": value["商品数"],
            "已售数": value["已售数"],
            "已退回数": value["已退回数"],
            "应结算金额(元)": _money(value["应结算金额"], "应结算金额"),
            "已结算金额(元)": _money(value["已结算金额"], "已结算金额"),
            "待结算金额(元)": _money(value["待结算金额"], "待结算金额"),
            "卖家毛利(元)": _signed_money(value["卖家毛利"], "卖家毛利"),
            "逾期待结算数": value["逾期待结算数"],
        }
        for key, value in grouped.items()
    }


def _is_formula_like_text(value: str) -> bool:
    probe = value.lstrip(" \t\r\n")
    while probe.startswith("'"):
        probe = probe[1:]
    probe = probe.lstrip(" \t\r\n")
    return bool(probe) and probe[0] in ("=", "+", "-", "@")


def _safe_csv_text(value) -> str:
    text = str("" if value is None else value)
    if _is_formula_like_text(text) or text.startswith("'"):
        return "'" + text
    return text


def _restore_csv_text(value) -> str:
    text = str("" if value is None else value)
    if text.startswith("''"):
        return text[1:]
    if text.startswith("'") and _is_formula_like_text(text[1:]):
        return text[1:]
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


class ConsignmentStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def validate_rows(rows):
        if len(rows) > MAX_ROWS:
            raise ValueError(f"单次最多保存 {MAX_ROWS} 条寄售记录")
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
                or not isinstance(payload.get("records"), list)
            ):
                raise ValueError("寄售台账数据格式或版本不受支持")
            rows = [normalize_row(item) for item in payload["records"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"寄售台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        normalized = [normalize_row(row) for row in items]
        self.validate_rows(normalized)
        payload = {
            "format": FORMAT,
            "version": VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "records": normalized,
        }
        _atomic_write(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def add(self, raw):
        row = normalize_row(raw)
        if any(item["记录编号"] == row["记录编号"] for item in self.rows):
            raise ValueError("记录编号已存在")
        updated = self.rows + [row]
        self.save(updated)
        self.rows = updated

    def update(self, record_id, raw):
        row = normalize_row(raw)
        if row["记录编号"] != record_id:
            raise ValueError("记录编号不能修改")
        index = next(
            (i for i, item in enumerate(self.rows) if item["记录编号"] == record_id),
            None,
        )
        if index is None:
            raise ValueError("找不到要编辑的寄售记录")
        updated = list(self.rows)
        updated[index] = row
        self.save(updated)
        self.rows = updated

    def delete(self, record_id):
        updated = [item for item in self.rows if item["记录编号"] != record_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的寄售记录")
        self.save(updated)
        self.rows = updated

    def import_csv(self, path):
        source = Path(path)
        raw_bytes = source.read_bytes()
        if len(raw_bytes) > MAX_BYTES:
            raise ValueError("CSV 文件超过 50 MiB，拒绝导入")
        try:
            csv_text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                csv_text = raw_bytes.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 编码不受支持，请使用 UTF-8 或 GB18030") from exc
        incoming = []
        reader = csv.DictReader(io.StringIO(csv_text, newline=""))
        if reader.fieldnames != list(FIELDS):
            raise ValueError("CSV 表头必须与软件导出的字段和顺序完全一致")
        for line, raw in enumerate(reader, start=2):
            if None in raw:
                raise ValueError(f"第 {line} 行包含多余字段")
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            try:
                restored = {
                    field: _restore_csv_text(raw.get(field, ""))
                    for field in FIELDS
                }
                incoming.append(normalize_row(restored))
            except ValueError as exc:
                raise ValueError(f"第 {line} 行：{exc}") from exc
            if len(incoming) > MAX_ROWS:
                raise ValueError(f"单次最多导入 {MAX_ROWS} 条记录")
        self.validate_rows(incoming)
        existing = {item["记录编号"] for item in self.rows}
        duplicates = existing.intersection(item["记录编号"] for item in incoming)
        if duplicates:
            raise ValueError(
                "导入包含已存在记录编号，整批未导入：" + "、".join(sorted(duplicates))
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
        return len(self.rows)

    def backup(self, path):
        records = [dict(row) for row in self.rows]
        canonical = json.dumps(
            records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload = {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "records": records,
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
                or not isinstance(payload.get("records"), list)
                or not isinstance(payload.get("sha256"), str)
            ):
                raise ValueError("备份文件格式或版本不受支持")
            canonical = json.dumps(
                payload["records"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            actual = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(actual, payload["sha256"]):
                raise ValueError("备份 SHA256 校验失败，当前数据未修改")
            rows = [normalize_row(item) for item in payload["records"]]
            self.validate_rows(rows)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"恢复失败，当前数据未修改：{exc}") from exc
        self.save(rows)
        self.rows = rows


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "xianyu_consignment.json"


def self_test():
    import tempfile

    sample = {
        "记录编号": "CY-TEST-001",
        "货主编号": "OWNER-001",
        "货主名称": "测试货主",
        "联系方式备注": "",
        "商品编号/SKU": "SKU-001",
        "商品名称": "二手蓝牙耳机",
        "商品成色/瑕疵": "九成新",
        "收货日期": "2026-11-01",
        "约定上架价(元)": "120",
        "货主约定结算额(元)": "70",
        "当前标价(元)": "120",
        "商品状态": "已售",
        "成交日期": "2026-11-10",
        "实际成交金额(元)": "100",
        "平台实际费用(元)": "1.5",
        "发货运费(元)": "5",
        "包装整备成本(元)": "2",
        "已结算金额(元)": "20",
        "结算期限": "2026-11-20",
        "最后结算日期": "2026-11-12",
        "退回日期": "",
        "备注": "",
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = ConsignmentStore(root / "records.json")
        store.add(sample)
        result = calculate_item(sample)
        assert result["待结算金额(元)"] == "50.00"
        assert result["卖家毛利(元)"] == "21.50"
        csv_path = root / "records.csv"
        store.export_csv(csv_path)
        imported = ConsignmentStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup = root / "backup.json"
        store.backup(backup)
        restored = ConsignmentStore(root / "restored.json")
        restored.restore(backup)
        assert restored.rows == store.rows
    print("SELF_TEST_OK", flush=True)
