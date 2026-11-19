"""Offline Xianyu return/refund follow-up ledger with safe CSV and SHA256 backups."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-xianyu-return-followup"
BACKUP_FORMAT = "mainland-xianyu-return-followup-backup"
VERSION = 1
RULESET_VERSION = "XY-RETURN-2026.11"
MAX_ROWS = 50000
MAX_DATA_BYTES = 50 * 1024 * 1024
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_NUMERIC_TEXT_LENGTH = 64

CASE_TYPES = ("仅退款", "退货退款", "换货", "部分退款", "补偿")
RESPONSIBILITIES = ("买家", "卖家", "物流", "平台", "待核实")
FREIGHT_PAYER = ("卖家", "买家", "平台", "待确认", "不涉及")
STATUSES = (
    "待沟通", "待买家寄回", "待卖家验收", "待退款",
    "待换货", "待平台处理", "已完成", "已关闭",
)
TERMINAL_STATUSES = {"已完成", "已关闭"}
RETURN_TYPES = {"退货退款", "换货"}
STATUS_TRANSITIONS = {
    "待沟通": {"待沟通", "待买家寄回", "待卖家验收", "待退款", "待换货", "待平台处理", "已关闭"},
    "待买家寄回": {"待买家寄回", "待卖家验收", "待平台处理", "已关闭"},
    "待卖家验收": {"待卖家验收", "待退款", "待换货", "待平台处理", "已关闭"},
    "待退款": {"待退款", "已完成", "待平台处理", "已关闭"},
    "待换货": {"待换货", "已完成", "待平台处理", "已关闭"},
    "待平台处理": {"待平台处理", "待沟通", "待买家寄回", "待卖家验收", "待退款", "待换货", "已完成", "已关闭"},
    "已完成": {"已完成"},
    "已关闭": {"已关闭"},
}
FIELDS = (
    "记录编号", "订单编号", "商品/SKU", "售后类型", "申请日期",
    "订单成交金额(元)", "申请金额(元)", "实际退款金额(元)",
    "补偿金额(元)", "退货运费(元)", "运费承担方", "责任归属",
    "处理状态", "处理截止日期", "下次跟进日期", "下一步动作", "买家寄回运单号",
    "买家寄回日期", "卖家收货日期", "退款完成日期",
    "本地证据目录", "处理摘要", "备注",
)
LEGACY_FIELDS = tuple(field for field in FIELDS if field != "下次跟进日期")
TEXT_FIELDS = set(FIELDS) - {
    "订单成交金额(元)", "申请金额(元)", "实际退款金额(元)",
    "补偿金额(元)", "退货运费(元)",
}
ACTION_FIELDS = (
    "记录编号", "订单编号", "商品/SKU", "售后类型", "处理状态",
    "处理截止日期", "下次跟进日期", "待处理类型", "提醒事项", "提醒日期", "逾期天数", "下一步动作",
    "责任归属", "实际退款金额(元)", "补偿金额(元)", "退货运费(元)", "备注",
)
ACTION_TEXT_FIELDS = set(ACTION_FIELDS) - {
    "逾期天数", "实际退款金额(元)", "补偿金额(元)", "退货运费(元)",
}


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
        raise ValueError("售后记录必须是对象")
    today = today or date.today()
    item = {
        field: str("" if row.get(field) is None else row.get(field, "")).strip()
        for field in FIELDS
    }
    for field in ("记录编号", "订单编号", "商品/SKU", "售后类型", "申请日期", "订单成交金额(元)", "处理状态"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")

    limits = {
        "记录编号": 80, "订单编号": 120, "商品/SKU": 160,
        "下一步动作": 300, "买家寄回运单号": 120,
        "本地证据目录": 1000, "处理摘要": 2000, "备注": 2000,
    }
    for field, limit in limits.items():
        if len(item[field]) > limit:
            raise ValueError(f"{field}长度不能超过 {limit} 个字符")
    if item["售后类型"] not in CASE_TYPES:
        raise ValueError("售后类型不在内置列表中")
    if item["责任归属"] and item["责任归属"] not in RESPONSIBILITIES:
        raise ValueError("责任归属不在内置列表中")
    if item["运费承担方"] and item["运费承担方"] not in FREIGHT_PAYER:
        raise ValueError("运费承担方不在内置列表中")
    if item["处理状态"] not in STATUSES:
        raise ValueError("处理状态不在内置列表中")

    item["申请日期"] = _date(item["申请日期"], "申请日期", today)
    item["处理截止日期"] = _date(
        item["处理截止日期"], "处理截止日期", today, allow_future=True
    )
    for field in ("买家寄回日期", "卖家收货日期", "退款完成日期"):
        item[field] = _date(item[field], field, today)
    item["下次跟进日期"] = _date(
        item["下次跟进日期"], "下次跟进日期", today, allow_future=True
    )

    amount_fields = (
        "订单成交金额(元)", "申请金额(元)", "实际退款金额(元)",
        "补偿金额(元)", "退货运费(元)",
    )
    for field in amount_fields:
        value = _decimal(item[field], field, allow_blank=(field != "订单成交金额(元)"))
        if value is None:
            value = Decimal("0")
        if value < 0:
            raise ValueError(f"{field}不能为负数")
        item[field] = _money(value, field)

    order_amount = Decimal(item["订单成交金额(元)"])
    requested = Decimal(item["申请金额(元)"])
    refunded = Decimal(item["实际退款金额(元)"])
    if requested > order_amount:
        raise ValueError("申请金额不能超过订单成交金额")
    if refunded > requested:
        raise ValueError("实际退款金额不能超过申请金额")
    if item["买家寄回日期"] and item["售后类型"] not in RETURN_TYPES:
        raise ValueError("仅退款或补偿案件不能填写买家寄回日期")
    if item["卖家收货日期"] and not item["买家寄回日期"]:
        raise ValueError("卖家收货日期需要先填写买家寄回日期")
    if item["退款完成日期"] and refunded <= 0:
        raise ValueError("退款完成日期需要填写大于 0 的实际退款金额")
    if item["处理状态"] == "已完成" and refunded > 0 and not item["退款完成日期"]:
        raise ValueError("已完成的退款案件必须填写退款完成日期")
    if item["处理状态"] == "待买家寄回" and item["售后类型"] not in RETURN_TYPES:
        raise ValueError("仅退款或补偿案件不能进入待买家寄回状态")
    if item["买家寄回日期"] and item["买家寄回日期"] < item["申请日期"]:
        raise ValueError("买家寄回日期不能早于申请日期")
    if item["下次跟进日期"] and item["下次跟进日期"] < item["申请日期"]:
        raise ValueError("下次跟进日期不能早于申请日期")
    if item["卖家收货日期"] and item["卖家收货日期"] < item["买家寄回日期"]:
        raise ValueError("卖家收货日期不能早于买家寄回日期")
    if item["退款完成日期"] and item["退款完成日期"] < item["申请日期"]:
        raise ValueError("退款完成日期不能早于申请日期")
    return item


def case_risk(row: dict, as_of: date | None = None) -> dict:
    today = as_of or date.today()
    item = normalize_row(row, today=today)
    empty = {
        "需要跟进": False,
        "待处理类型": "",
        "逾期天数": 0,
        "剩余天数": "",
        "提醒事项": "",
        "提醒日期": "",
    }
    if item["处理状态"] in TERMINAL_STATUSES:
        return empty

    candidates = []
    for label, field in (
        ("处理截止", "处理截止日期"),
        ("下次跟进", "下次跟进日期"),
    ):
        value = item[field]
        if not value:
            continue
        due = date.fromisoformat(value)
        delta = (today - due).days
        if delta > 0:
            kind, priority = "已逾期", 0
        elif delta == 0:
            kind, priority = "今日到期", 1
        elif delta >= -3:
            kind, priority = "3日内到期", 2
        else:
            continue
        candidates.append({
            "优先级": priority,
            "待处理类型": kind,
            "逾期天数": delta if delta > 0 else 0,
            "剩余天数": -delta if delta < 0 else 0,
            "提醒事项": label,
            "提醒日期": value,
        })

    if not candidates:
        return empty
    selected = min(
        candidates,
        key=lambda candidate: (
            candidate["优先级"],
            candidate["提醒日期"],
            0 if candidate["提醒事项"] == "处理截止" else 1,
        ),
    )
    return {
        "需要跟进": True,
        "待处理类型": selected["待处理类型"],
        "逾期天数": selected["逾期天数"],
        "剩余天数": selected["剩余天数"],
        "提醒事项": selected["提醒事项"],
        "提醒日期": selected["提醒日期"],
    }


def after_sales_summary(rows: list[dict], as_of: date | None = None) -> dict:
    today = as_of or date.today()
    counts = {status: 0 for status in STATUSES}
    overdue = 0
    pending_refund = 0
    pending_return = 0
    refund_total = Decimal("0")
    compensation_total = Decimal("0")
    seller_freight_total = Decimal("0")
    for raw in rows:
        item = normalize_row(raw, today=today)
        counts[item["处理状态"]] += 1
        risk = case_risk(item, as_of=today)
        if risk["待处理类型"] == "已逾期":
            overdue += 1
        if item["处理状态"] == "待退款":
            pending_refund += 1
        if item["处理状态"] in {"待买家寄回", "待卖家验收"}:
            pending_return += 1
        refund_total += Decimal(item["实际退款金额(元)"])
        compensation_total += Decimal(item["补偿金额(元)"])
        if item["运费承担方"] == "卖家":
            seller_freight_total += Decimal(item["退货运费(元)"])
    open_count = sum(
        count for status, count in counts.items() if status not in TERMINAL_STATUSES
    )
    cash_outflow = refund_total + compensation_total + seller_freight_total
    return {
        "案件总数": len(rows),
        "未结案件数": open_count,
        "逾期案件数": overdue,
        "待退款案件数": pending_refund,
        "待退货或验收案件数": pending_return,
        "平台处理中案件数": counts["待平台处理"],
        "状态数量": counts,
        "实际退款合计(元)": _money(refund_total, "实际退款合计"),
        "补偿合计(元)": _money(compensation_total, "补偿合计"),
        "卖家承担退货运费(元)": _money(seller_freight_total, "卖家承担退货运费"),
        "已登记售后支出(元)": _money(cash_outflow, "已登记售后支出"),
    }


def actionable_cases(rows: list[dict], as_of: date | None = None) -> list[dict]:
    today = as_of or date.today()
    results = []
    for raw in rows:
        item = normalize_row(raw, today=today)
        risk = case_risk(item, as_of=today)
        if not risk["需要跟进"]:
            continue
        results.append({
            **{field: item[field] for field in FIELDS},
            "待处理类型": risk["待处理类型"],
            "提醒事项": risk["提醒事项"],
            "提醒日期": risk["提醒日期"],
            "逾期天数": risk["逾期天数"],
        })
    priority = {"已逾期": 0, "今日到期": 1, "3日内到期": 2}
    results.sort(key=lambda row: (
        priority[row["待处理类型"]],
        row["提醒日期"],
        row["订单编号"],
    ))
    return results


def _safe_csv_text(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    return "'" + text if probe[:1] in ("=", "+", "-", "@") else text


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


class ReturnFollowupStore:
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
            if self.path.stat().st_size > MAX_DATA_BYTES:
                raise ValueError("本地售后台账超过 50 MiB 安全上限")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("items"), list)
            ):
                raise ValueError("售后台账数据格式或版本不受支持")
            if len(payload["items"]) > MAX_ROWS:
                raise ValueError("本地售后台账超过 50000 条记录上限")
            rows = [normalize_row(row) for row in payload["items"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"售后台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        if len(items) > MAX_ROWS:
            raise ValueError("单个台账最多保存 50000 条售后记录")
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
            raise ValueError("本地售后台账序列化后超过 50 MiB 安全上限")
        _atomic_write(self.path, data)

    def add(self, row):
        item = normalize_row(row)
        if any(old["记录编号"] == item["记录编号"] for old in self.rows):
            raise ValueError("记录编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, case_id, row):
        index = next(
            (i for i, old in enumerate(self.rows) if old["记录编号"] == case_id),
            None,
        )
        if index is None:
            raise ValueError("找不到要编辑的售后记录")
        candidate = dict(row)
        if str(candidate.get("记录编号", "")).strip() != case_id:
            raise ValueError("记录编号不能修改")
        current = self.rows[index]
        new_status = str(candidate.get("处理状态", "")).strip()
        if new_status != current["处理状态"]:
            if new_status not in STATUS_TRANSITIONS[current["处理状态"]]:
                raise ValueError(
                    f"不允许从“{current['处理状态']}”变更为“{new_status}”"
                )
        item = normalize_row(candidate)
        updated = list(self.rows)
        updated[index] = item
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def transition_status(self, case_id, new_status):
        row = next(
            (item for item in self.rows if item["记录编号"] == case_id),
            None,
        )
        if row is None:
            raise ValueError("找不到要变更状态的售后记录")
        if new_status not in STATUSES:
            raise ValueError("处理状态不在内置列表中")
        if new_status not in STATUS_TRANSITIONS[row["处理状态"]]:
            raise ValueError(
                f"不允许从“{row['处理状态']}”变更为“{new_status}”"
            )
        self.update(case_id, dict(row, **{"处理状态": new_status}))

    def delete(self, case_id):
        updated = [row for row in self.rows if row["记录编号"] != case_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的售后记录")
        self.save(updated)
        self.rows = updated

    def import_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_DATA_BYTES:
            raise ValueError("CSV 文件超过 50 MiB 安全上限")
        incoming = []
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames not in (list(FIELDS), list(LEGACY_FIELDS)):
                raise ValueError("CSV 表头必须与当前或旧版软件导出的字段和顺序完全一致")
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
                    raise ValueError("单次最多导入 50000 条售后记录")
        self.validate_rows(incoming)
        existing = {row["记录编号"] for row in self.rows}
        duplicates = existing.intersection(row["记录编号"] for row in incoming)
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

    def export_action_csv(self, path, as_of: date | None = None):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=ACTION_FIELDS, extrasaction="raise")
        writer.writeheader()
        cases = actionable_cases(self.rows, as_of=as_of)
        for row in cases:
            writer.writerow({
                field: _safe_csv_text(row[field])
                if field in ACTION_TEXT_FIELDS else row[field]
                for field in ACTION_FIELDS
            })
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
        return len(cases)

    def backup(self, path):
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
    return base / "MainlandBusinessTools" / "xianyu_return_followup.json"


def self_test() -> None:
    from tempfile import TemporaryDirectory

    today = date.today()
    sample = {
        "记录编号": "XY-R-SELF-001",
        "订单编号": "ORDER-SELF-001",
        "商品/SKU": "自检二手手机",
        "售后类型": "退货退款",
        "申请日期": today.isoformat(),
        "订单成交金额(元)": "100",
        "申请金额(元)": "80",
        "实际退款金额(元)": "50",
        "补偿金额(元)": "5",
        "退货运费(元)": "8",
        "运费承担方": "卖家",
        "责任归属": "待核实",
        "处理状态": "待退款",
        "处理截止日期": today.isoformat(),
        "下次跟进日期": today.isoformat(),
        "下一步动作": "核对退货商品后退款",
        "买家寄回运单号": "SF-SELF-001",
        "买家寄回日期": today.isoformat(),
        "卖家收货日期": "",
        "退款完成日期": "",
        "本地证据目录": "",
        "处理摘要": "仅用于自检",
        "备注": "不含真实订单",
    }
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = ReturnFollowupStore(root / "returns.json")
        store.add(sample)
        assert after_sales_summary(store.rows, as_of=today)["已登记售后支出(元)"] == "63.00"
        assert store.export_action_csv(root / "actions.csv", as_of=today) == 1
        store.export_csv(root / "returns.csv")
        imported = ReturnFollowupStore(root / "imported.json")
        assert imported.import_csv(root / "returns.csv") == 1
        backup = root / "returns.backup.json"
        store.backup(backup)
        restored = ReturnFollowupStore(root / "restored.json")
        restored.restore(backup)
        assert restored.rows == store.rows
        store.transition_status("XY-R-SELF-001", "待平台处理")
        assert store.rows[0]["处理状态"] == "待平台处理"
    if sys.stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    self_test()
