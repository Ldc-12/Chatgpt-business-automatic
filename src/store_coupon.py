"""Offline store coupon and campaign redemption ledger.

Records operator-entered campaign and redemption activity locally. It does not
issue platform vouchers, process payments, or connect to any online service.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-store-coupon-ledger"
VERSION = 1
MAX_CAMPAIGNS = 20000
MAX_COUPONS = 200000
MAX_EVENTS = 500000
MAX_ISSUE_BATCH = 5000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")
CAMPAIGN_STATUSES = {"启用", "停用"}
COUPON_STATUSES = {"未使用", "已核销", "已作废"}
CAMPAIGN_FIELDS = [
    "活动编号", "活动名称", "优惠金额", "最低消费金额",
    "开始日期", "结束日期", "发行上限", "状态", "备注",
]
COUPON_FIELDS = [
    "券编号", "活动编号", "活动名称", "优惠金额", "最低消费金额",
    "状态", "生成时间", "核销时间", "核销订单号", "实际消费金额",
    "实际优惠金额", "作废时间", "作废原因", "操作人", "备注",
]
REDEMPTION_FIELDS = [
    "券编号", "活动编号", "活动名称", "核销订单号", "核销时间",
    "实际消费金额", "实际优惠金额", "操作人", "备注",
]
CAMPAIGN_REPORT_FIELDS = [
    "活动编号", "活动名称", "活动状态", "发行数量", "已核销",
    "未使用", "已作废", "已过期", "实际优惠合计",
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def local_today():
    return date.today()


def local_now():
    return datetime.now().astimezone()


def parse_money(value, field="金额"):
    text = "" if value is None else str(value).strip()
    text = text.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "").replace("元", "").strip()
    if len(text) > 32:
        raise ValueError(f"{field}超出可接受长度")
    try:
        amount = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效数字") from None
    if not amount.is_finite() or amount < 0 or amount > MAX_AMOUNT:
        raise ValueError(f"{field}必须在 0 至 {MAX_AMOUNT} 之间")
    try:
        return format(amount.quantize(CENT, rounding=ROUND_HALF_UP), "f")
    except InvalidOperation:
        raise ValueError(f"{field}精度超出可接受范围") from None


def positive_integer(value, field, maximum):
    text = str(value).strip()
    if not re.fullmatch(r"[1-9]\d{0,8}", text):
        raise ValueError(f"{field}必须是正整数")
    number = int(text)
    if number > maximum:
        raise ValueError(f"{field}不能超过 {maximum}")
    return number


def parse_iso_date(value, field):
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


def parse_iso_datetime(value, field):
    try:
        return datetime.fromisoformat(str(value).strip()).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是有效 ISO 日期时间") from None


def csv_safe(value):
    text = "" if value is None else str(value)
    if re.fullmatch(r"-\d+(?:\.\d+)?", text):
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


def normalize_campaign(row):
    if not isinstance(row, dict):
        raise ValueError("活动资料必须是对象")
    campaign_id = str(row.get("活动编号", "") or "").strip() or ("C" + uuid.uuid4().hex[:20].upper())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", campaign_id):
        raise ValueError("活动编号只能包含 1–64 位字母、数字、下划线或连字符")
    name = str(row.get("活动名称", "") or "").strip()
    if not name or len(name) > 80:
        raise ValueError("活动名称不能为空且不能超过 80 个字符")
    discount = parse_money(row.get("优惠金额", ""), "优惠金额")
    minimum = parse_money(row.get("最低消费金额", ""), "最低消费金额")
    if Decimal(discount) <= 0:
        raise ValueError("优惠金额必须大于 0")
    if Decimal(minimum) < Decimal(discount):
        raise ValueError("最低消费金额不能小于优惠金额")
    start = parse_iso_date(row.get("开始日期", ""), "活动开始日期")
    end = parse_iso_date(row.get("结束日期", ""), "活动结束日期")
    if start > end:
        raise ValueError("活动开始日期不能晚于结束日期")
    issue_limit = positive_integer(row.get("发行上限", ""), "发行上限", MAX_COUPONS)
    status = str(row.get("状态", "启用") or "启用").strip()
    if status not in CAMPAIGN_STATUSES:
        raise ValueError("活动状态必须是启用或停用")
    note = str(row.get("备注", "") or "").strip()
    if len(note) > 500:
        raise ValueError("活动备注不能超过 500 个字符")
    return {
        "活动编号": campaign_id,
        "活动名称": name,
        "优惠金额": discount,
        "最低消费金额": minimum,
        "开始日期": start,
        "结束日期": end,
        "发行上限": issue_limit,
        "状态": status,
        "备注": note,
    }


def normalize_coupon(row, campaign_map):
    if not isinstance(row, dict):
        raise ValueError("优惠券记录必须是对象")
    coupon_id = str(row.get("券编号", "") or "").strip()
    campaign_id = str(row.get("活动编号", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", coupon_id):
        raise ValueError("优惠券编号格式无效")
    campaign = campaign_map.get(campaign_id)
    if campaign is None:
        raise ValueError(f"优惠券引用了不存在的活动：{campaign_id}")
    campaign_name = str(row.get("活动名称", "") or "").strip()
    discount = parse_money(row.get("优惠金额", ""), "优惠券优惠金额")
    minimum = parse_money(row.get("最低消费金额", ""), "优惠券最低消费金额")
    if campaign_name != campaign["活动名称"] or discount != campaign["优惠金额"] or minimum != campaign["最低消费金额"]:
        raise ValueError("优惠券活动快照与活动资料不一致")
    status = str(row.get("状态", "") or "").strip()
    if status not in COUPON_STATUSES:
        raise ValueError("优惠券状态必须是未使用、已核销或已作废")
    created_at = parse_iso_datetime(row.get("生成时间", ""), "优惠券生成时间")
    created_day = datetime.fromisoformat(created_at).date().isoformat()
    if not campaign["开始日期"] <= created_day <= campaign["结束日期"]:
        raise ValueError("优惠券生成日期不在活动有效期内")
    redeemed_at = str(row.get("核销时间", "") or "").strip()
    order_id = str(row.get("核销订单号", "") or "").strip()
    actual_spend = str(row.get("实际消费金额", "") or "").strip()
    actual_discount = str(row.get("实际优惠金额", "") or "").strip()
    voided_at = str(row.get("作废时间", "") or "").strip()
    void_reason = str(row.get("作废原因", "") or "").strip()
    operator = str(row.get("操作人", "") or "").strip() or "本机用户"
    note = str(row.get("备注", "") or "").strip()
    if len(operator) > 80 or len(note) > 500 or len(order_id) > 80 or len(void_reason) > 300:
        raise ValueError("操作人最多 80、订单号最多 80、作废原因最多 300、备注最多 500 个字符")
    if any(ord(ch) < 32 for ch in order_id):
        raise ValueError("核销订单号不能包含控制字符")
    if status == "未使用":
        if any((redeemed_at, order_id, actual_spend, actual_discount, voided_at, void_reason)):
            raise ValueError("未使用优惠券不能包含核销或作废信息")
    elif status == "已核销":
        redeemed_at = parse_iso_datetime(redeemed_at, "核销时间")
        redeemed_dt = datetime.fromisoformat(redeemed_at)
        created_dt = datetime.fromisoformat(created_at)
        redeemed_day = redeemed_dt.date().isoformat()
        if redeemed_dt < created_dt or not campaign["开始日期"] <= redeemed_day <= campaign["结束日期"]:
            raise ValueError("核销日期不在活动有效期或早于优惠券生成时间")
        if not order_id:
            raise ValueError("已核销优惠券必须填写核销订单号")
        actual_spend = parse_money(actual_spend, "实际消费金额")
        actual_discount = parse_money(actual_discount, "实际优惠金额")
        if Decimal(actual_spend) < Decimal(minimum):
            raise ValueError("实际消费金额未达到活动最低消费金额")
        if Decimal(actual_discount) <= 0 or Decimal(actual_discount) > Decimal(discount):
            raise ValueError("实际优惠金额必须大于 0 且不能超过券面优惠金额")
        if Decimal(actual_discount) > Decimal(actual_spend):
            raise ValueError("实际优惠金额不能超过实际消费金额")
        if voided_at or void_reason:
            raise ValueError("已核销优惠券不能包含作废信息")
    else:
        voided_at = parse_iso_datetime(voided_at, "作废时间")
        if datetime.fromisoformat(voided_at) < datetime.fromisoformat(created_at):
            raise ValueError("作废时间不能早于优惠券生成时间")
        if not void_reason:
            raise ValueError("已作废优惠券必须填写作废原因")
        if any((redeemed_at, order_id, actual_spend, actual_discount)):
            raise ValueError("已作废优惠券不能包含核销信息")
    return {
        "券编号": coupon_id,
        "活动编号": campaign_id,
        "活动名称": campaign_name,
        "优惠金额": discount,
        "最低消费金额": minimum,
        "状态": status,
        "生成时间": created_at,
        "核销时间": redeemed_at,
        "核销订单号": order_id,
        "实际消费金额": actual_spend,
        "实际优惠金额": actual_discount,
        "作废时间": voided_at,
        "作废原因": void_reason,
        "操作人": operator,
        "备注": note,
    }


def append_event(events, action, reference="", actor="本机用户", reason=""):
    previous = events[-1]["hash"] if events else ""
    body = {
        "seq": len(events) + 1,
        "timestamp": local_now().isoformat(timespec="seconds"),
        "action": str(action),
        "reference": str(reference or ""),
        "actor": str(actor or "本机用户").strip()[:80],
        "reason": str(reason or "").strip()[:500],
        "previous_hash": previous,
    }
    return events + [{**body, "hash": hashlib.sha256(canonical(body)).hexdigest()}]


def verify_audit(events):
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError("操作日志格式无效或超过安全上限")
    previous = ""
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != index or event.get("previous_hash") != previous:
            raise ValueError("操作日志顺序或前序摘要无效")
        body = {key: value for key, value in event.items() if key != "hash"}
        digest = hashlib.sha256(canonical(body)).hexdigest()
        if event.get("hash") != digest:
            raise ValueError("操作日志 SHA256 校验失败")
        previous = digest
    return True


def validate_state(raw_campaigns, raw_coupons):
    if not isinstance(raw_campaigns, list) or len(raw_campaigns) > MAX_CAMPAIGNS:
        raise ValueError("活动资料缺失或超过 20000 条安全上限")
    if not isinstance(raw_coupons, list) or len(raw_coupons) > MAX_COUPONS:
        raise ValueError("优惠券记录缺失或超过 200000 条安全上限")
    campaigns = [normalize_campaign(item) for item in raw_campaigns]
    campaign_ids = [item["活动编号"] for item in campaigns]
    if len(campaign_ids) != len(set(campaign_ids)):
        raise ValueError("活动编号重复")
    campaign_map = {item["活动编号"]: item for item in campaigns}
    coupons = [normalize_coupon(item, campaign_map) for item in raw_coupons]
    coupon_ids = [item["券编号"] for item in coupons]
    if len(coupon_ids) != len(set(coupon_ids)):
        raise ValueError("优惠券编号重复")
    counts = {}
    redeemed_orders = set()
    for coupon in coupons:
        campaign_id = coupon["活动编号"]
        counts[campaign_id] = counts.get(campaign_id, 0) + 1
        if coupon["状态"] == "已核销":
            order_key = coupon["核销订单号"].casefold()
            if order_key in redeemed_orders:
                raise ValueError("同一订单不能重复核销多张优惠券")
            redeemed_orders.add(order_key)
    for campaign_id, count in counts.items():
        if count > campaign_map[campaign_id]["发行上限"]:
            raise ValueError(f"活动 {campaign_id} 的优惠券数量超过发行上限")
    return campaigns, coupons


def filter_coupon_rows(coupons, keyword="", status="全部"):
    """Filter coupon rows by text and state without mutating the source list."""
    allowed_statuses = {"全部", *COUPON_STATUSES}
    if status not in allowed_statuses:
        raise ValueError("优惠券筛选状态无效")
    needle = str(keyword or "").strip().casefold()
    rows = []
    for coupon in coupons:
        if status != "全部" and coupon.get("状态") != status:
            continue
        if needle:
            searchable = " ".join(
                str(coupon.get(field, "") or "")
                for field in ("券编号", "活动编号", "活动名称", "核销订单号", "操作人", "备注")
            ).casefold()
            if needle not in searchable:
                continue
        rows.append(coupon)
    return rows


def paginate_coupon_rows(rows, page, page_size=100):
    """Return one bounded page and clamp stale page numbers after filtering."""
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("每页数量必须是正整数")
    if isinstance(page, bool):
        raise ValueError("页码必须是正整数")
    try:
        requested_page = int(page)
    except (TypeError, ValueError):
        raise ValueError("页码必须是正整数") from None
    if requested_page < 1:
        requested_page = 1
    items = list(rows)
    total = len(items)
    page_count = max(1, (total + page_size - 1) // page_size)
    current_page = min(requested_page, page_count)
    start = (current_page - 1) * page_size
    return items[start:start + page_size], current_page, page_count, total


class CouponStore:
    def __init__(self, path):
        self.path = Path(path)
        self.campaigns = []
        self.coupons = []
        self.events = []
        self.load()

    @staticmethod
    def _payload(campaigns, coupons, events):
        body = {
            "格式": FORMAT,
            "版本": VERSION,
            "活动": campaigns,
            "优惠券": coupons,
            "操作日志": events,
        }
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("优惠券台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("优惠券台账 SHA256 校验失败")
        campaigns, coupons = validate_state(body.get("活动"), body.get("优惠券"))
        events = body.get("操作日志")
        verify_audit(events)
        return campaigns, coupons, events

    def load(self):
        if not self.path.exists():
            self.campaigns, self.coupons, self.events = [], [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("本地优惠券台账超过 100 MiB，已拒绝加载且原文件未修改")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.campaigns, self.coupons, self.events = self.decode(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"本地优惠券台账无法读取，原文件未修改：{exc}") from exc

    def _commit(self, campaigns, coupons, events):
        normalized_campaigns, normalized_coupons = validate_state(campaigns, coupons)
        verify_audit(events)
        data = json.dumps(
            self._payload(normalized_campaigns, normalized_coupons, events),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("优惠券台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.campaigns = normalized_campaigns
        self.coupons = normalized_coupons
        self.events = events

    def _campaign(self, campaign_id):
        item = next((row for row in self.campaigns if row["活动编号"] == campaign_id), None)
        if item is None:
            raise ValueError("活动不存在")
        return item

    def _coupon(self, coupon_id):
        item = next((row for row in self.coupons if row["券编号"] == coupon_id), None)
        if item is None:
            raise ValueError("优惠券不存在")
        return item

    def create_campaign(self, row, actor="本机用户"):
        campaign = normalize_campaign(row)
        if any(item["活动编号"] == campaign["活动编号"] for item in self.campaigns):
            raise ValueError("活动编号已存在")
        if len(self.campaigns) >= MAX_CAMPAIGNS:
            raise ValueError("活动数量超过安全上限")
        events = append_event(self.events, "新增营销活动", campaign["活动编号"], actor)
        self._commit(self.campaigns + [campaign], self.coupons, events)
        return campaign["活动编号"]

    def set_campaign_status(self, campaign_id, status, actor="本机用户", reason=""):
        if status not in CAMPAIGN_STATUSES:
            raise ValueError("活动状态必须是启用或停用")
        current = self._campaign(campaign_id)
        updated = dict(current)
        updated["状态"] = status
        campaigns = [updated if item["活动编号"] == campaign_id else item for item in self.campaigns]
        events = append_event(self.events, "修改活动状态", campaign_id, actor, reason)
        self._commit(campaigns, self.coupons, events)

    def issue_coupons(self, campaign_id, count, actor="本机用户", note=""):
        campaign = self._campaign(campaign_id)
        if campaign["状态"] != "启用":
            raise ValueError("停用活动不能发行优惠券")
        today = local_today().isoformat()
        if not campaign["开始日期"] <= today <= campaign["结束日期"]:
            raise ValueError("当前日期不在活动发行有效期内")
        quantity = positive_integer(count, "发行数量", MAX_ISSUE_BATCH)
        issued = sum(1 for item in self.coupons if item["活动编号"] == campaign_id)
        if issued + quantity > campaign["发行上限"]:
            raise ValueError("发行数量会超过活动发行上限")
        if len(self.coupons) + quantity > MAX_COUPONS:
            raise ValueError("优惠券总数超过 200000 条安全上限")
        created_at = local_now().isoformat(timespec="seconds")
        new_coupons = []
        for _ in range(quantity):
            new_coupons.append({
                "券编号": "CP" + uuid.uuid4().hex[:20].upper(),
                "活动编号": campaign_id,
                "活动名称": campaign["活动名称"],
                "优惠金额": campaign["优惠金额"],
                "最低消费金额": campaign["最低消费金额"],
                "状态": "未使用",
                "生成时间": created_at,
                "核销时间": "",
                "核销订单号": "",
                "实际消费金额": "",
                "实际优惠金额": "",
                "作废时间": "",
                "作废原因": "",
                "操作人": str(actor or "本机用户").strip()[:80],
                "备注": str(note or "").strip()[:500],
            })
        events = append_event(self.events, "发行优惠券", campaign_id, actor, f"发行 {quantity} 张")
        self._commit(self.campaigns, self.coupons + new_coupons, events)
        return [item["券编号"] for item in new_coupons]

    def redeem(self, coupon_id, order_id, actual_spend, actor="本机用户", note=""):
        coupon = self._coupon(coupon_id)
        if coupon["状态"] != "未使用":
            raise ValueError("优惠券不是未使用状态，不能再次核销")
        campaign = self._campaign(coupon["活动编号"])
        if campaign["状态"] != "启用":
            raise ValueError("活动已停用，不能核销")
        today = local_today().isoformat()
        if not campaign["开始日期"] <= today <= campaign["结束日期"]:
            raise ValueError("当前日期不在活动核销有效期内")
        order = str(order_id or "").strip()
        if not order or len(order) > 80 or any(ord(ch) < 32 for ch in order):
            raise ValueError("核销订单号不能为空、不能超过 80 个字符或包含控制字符")
        if any(item["状态"] == "已核销" and item["核销订单号"].casefold() == order.casefold() for item in self.coupons):
            raise ValueError("同一订单不能重复核销多张优惠券")
        spend = parse_money(actual_spend, "实际消费金额")
        if Decimal(spend) < Decimal(campaign["最低消费金额"]):
            raise ValueError("实际消费金额未达到活动最低消费金额")
        discount = campaign["优惠金额"]
        updated = dict(coupon)
        updated.update({
            "状态": "已核销",
            "核销时间": local_now().isoformat(timespec="seconds"),
            "核销订单号": order,
            "实际消费金额": spend,
            "实际优惠金额": discount,
            "操作人": str(actor or "本机用户").strip()[:80],
            "备注": str(note or "").strip()[:500],
        })
        coupons = [updated if item["券编号"] == coupon_id else item for item in self.coupons]
        events = append_event(self.events, "核销优惠券", coupon_id, actor, f"订单 {order}")
        self._commit(self.campaigns, coupons, events)
        return coupon_id

    def void_coupon(self, coupon_id, reason, actor="本机用户"):
        coupon = self._coupon(coupon_id)
        if coupon["状态"] != "未使用":
            raise ValueError("只有未使用优惠券可以作废")
        text = str(reason or "").strip()
        if not text or len(text) > 300:
            raise ValueError("作废原因不能为空且不能超过 300 个字符")
        updated = dict(coupon)
        updated.update({
            "状态": "已作废",
            "作废时间": local_now().isoformat(timespec="seconds"),
            "作废原因": text,
            "操作人": str(actor or "本机用户").strip()[:80],
        })
        coupons = [updated if item["券编号"] == coupon_id else item for item in self.coupons]
        events = append_event(self.events, "作废优惠券", coupon_id, actor, text)
        self._commit(self.campaigns, coupons, events)

    def import_campaigns_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("活动 CSV 超过 25 MiB 安全上限")
        incoming = []
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != CAMPAIGN_FIELDS:
                raise ValueError("活动 CSV 表头与本软件模板不一致")
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"活动 CSV 第 {line} 行列数不正确")
                try:
                    incoming.append(normalize_campaign(row))
                except ValueError as exc:
                    raise ValueError(f"活动 CSV 第 {line} 行：{exc}") from exc
                if len(incoming) > MAX_CAMPAIGNS:
                    raise ValueError("单次导入活动数量超过 20000 条安全上限")
        ids = [item["活动编号"] for item in incoming]
        existing = {item["活动编号"] for item in self.campaigns}
        if len(ids) != len(set(ids)) or existing.intersection(ids):
            raise ValueError("导入批次存在重复活动编号或与本地活动编号冲突")
        if len(self.campaigns) + len(incoming) > MAX_CAMPAIGNS:
            raise ValueError("导入后活动总数超过 20000 条安全上限")
        if not incoming:
            return 0
        events = append_event(self.events, "批量导入活动", "", "本机用户", f"导入 {len(incoming)} 个活动")
        self._commit(self.campaigns + incoming, self.coupons, events)
        return len(incoming)

    @staticmethod
    def _write_csv(path, fields, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe(row.get(key, "")) for key in fields})
        atomic_write(path, output.getvalue().encode("utf-8-sig"))

    def export_campaigns_csv(self, path):
        self._write_csv(path, CAMPAIGN_FIELDS, self.campaigns)

    def export_coupons_csv(self, path):
        self._write_csv(path, COUPON_FIELDS, self.coupons)

    def export_redemptions_csv(self, path):
        rows = [item for item in self.coupons if item["状态"] == "已核销"]
        self._write_csv(path, REDEMPTION_FIELDS, rows)

    def export_campaign_report_csv(self, path):
        self._write_csv(path, CAMPAIGN_REPORT_FIELDS, self.campaign_report())

    def campaign_report(self):
        today = local_today()
        report = []
        for campaign in self.campaigns:
            rows = [item for item in self.coupons if item["活动编号"] == campaign["活动编号"]]
            redeemed = [item for item in rows if item["状态"] == "已核销"]
            unused = [item for item in rows if item["状态"] == "未使用"]
            voided = [item for item in rows if item["状态"] == "已作废"]
            expired = [
                item for item in unused
                if date.fromisoformat(campaign["结束日期"]) < today
            ]
            discount_total = sum((Decimal(item["实际优惠金额"]) for item in redeemed), Decimal("0.00"))
            report.append({
                "活动编号": campaign["活动编号"],
                "活动名称": campaign["活动名称"],
                "活动状态": campaign["状态"],
                "发行数量": len(rows),
                "已核销": len(redeemed),
                "未使用": len(unused),
                "已作废": len(voided),
                "已过期": len(expired),
                "实际优惠合计": format(discount_total.quantize(CENT), "f"),
            })
        return report

    def summary(self):
        redeemed = [item for item in self.coupons if item["状态"] == "已核销"]
        unused = [item for item in self.coupons if item["状态"] == "未使用"]
        voided = [item for item in self.coupons if item["状态"] == "已作废"]
        expired = sum(
            1 for item in unused
            if date.fromisoformat(self._campaign(item["活动编号"])["结束日期"]) < local_today()
        )
        discount_total = sum((Decimal(item["实际优惠金额"]) for item in redeemed), Decimal("0.00"))
        return {
            "活动数量": len(self.campaigns),
            "发行优惠券": len(self.coupons),
            "已核销": len(redeemed),
            "未使用": len(unused),
            "已作废": len(voided),
            "已过期": expired,
            "实际优惠合计": format(discount_total.quantize(CENT), "f"),
        }

    def backup(self, path):
        data = json.dumps(
            self._payload(self.campaigns, self.coupons, self.events),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        campaigns, coupons, events = self.decode(payload)
        events = append_event(events, "恢复备份", "", "本机用户", "从备份文件恢复")
        self._commit(campaigns, coupons, events)

    def audit_summary(self):
        verify_audit(self.events)
        latest = self.events[-1] if self.events else {}
        return {
            "事件数": len(self.events),
            "最后操作": latest.get("action", ""),
            "最后操作时间": latest.get("timestamp", ""),
            "最新摘要": latest.get("hash", ""),
        }


def self_test():
    import tempfile
    from datetime import timedelta

    with tempfile.TemporaryDirectory() as folder:
        today = local_today()
        store = CouponStore(Path(folder) / "coupons.json")
        campaign_id = store.create_campaign({
            "活动名称": "自检活动",
            "优惠金额": "10",
            "最低消费金额": "50",
            "开始日期": today.isoformat(),
            "结束日期": (today + timedelta(days=7)).isoformat(),
            "发行上限": "2",
        })
        codes = store.issue_coupons(campaign_id, 2)
        store.redeem(codes[0], "SELF-TEST-ORDER", "80")
        store.void_coupon(codes[1], "自检作废")
        backup = Path(folder) / "backup.json"
        store.backup(backup)
        restored = CouponStore(Path(folder) / "restored.json")
        restored.restore(backup)
        assert restored.summary()["已核销"] == 1
        assert restored.summary()["已作废"] == 1
        assert restored.audit_summary()["事件数"] >= 1
    if __import__("sys").stdout is not None:
        print("SELF_TEST_OK", flush=True)
