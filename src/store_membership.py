"""Offline member stored-value and points ledger with immutable transactions.

This module intentionally avoids payment gateways and platform integrations. It
records operator-entered transactions locally; it does not process real payments.
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
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-store-membership-ledger"
VERSION = 1
MAX_MEMBERS = 50000
MAX_TRANSACTIONS = 200000
MAX_EVENTS = 500000
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")
MAX_POINTS = 1_000_000_000
MEMBER_STATUSES = {"正常", "停用"}
TRANSACTION_TYPES = {"充值", "消费", "退款", "积分兑换"}
MEMBER_FIELDS = ["会员编号", "会员姓名", "联系电话", "入会日期", "状态", "备注"]
TRANSACTION_FIELDS = [
    "流水编号", "会员编号", "会员姓名", "交易类型", "交易金额", "积分变动",
    "关联消费流水", "发生时间", "操作人", "备注", "储值余额", "积分余额",
]
BALANCE_FIELDS = ["会员编号", "会员姓名", "联系电话", "状态", "储值余额", "积分余额", "入会日期"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def money_value(value, field="金额"):
    text = "" if value is None else str(value).strip().replace(",", "").replace("，", "")
    text = text.replace("￥", "").replace("¥", "").replace("元", "").strip()
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


def signed_points(value, field="积分变动"):
    text = str(value).strip()
    if not re.fullmatch(r"-?\d{1,10}", text):
        raise ValueError(f"{field}必须是整数")
    number = int(text)
    if abs(number) > MAX_POINTS:
        raise ValueError(f"{field}超出安全范围")
    return number


def csv_safe(value):
    text = "" if value is None else str(value)
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


def normalize_member(row):
    if not isinstance(row, dict):
        raise ValueError("会员资料必须是对象")
    member_id = str(row.get("会员编号", "") or "").strip() or ("M" + uuid.uuid4().hex[:20].upper())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", member_id):
        raise ValueError("会员编号只能包含 1–64 位字母、数字、下划线或连字符")
    name = str(row.get("会员姓名", "") or "").strip()
    phone = str(row.get("联系电话", "") or "").strip()
    note = str(row.get("备注", "") or "").strip()
    if not name or len(name) > 80:
        raise ValueError("会员姓名不能为空且不能超过 80 个字符")
    if len(phone) > 40 or len(note) > 500:
        raise ValueError("联系电话最多 40 个字符，备注最多 500 个字符")
    joined = str(row.get("入会日期", "") or date.today().isoformat()).strip()
    try:
        joined = date.fromisoformat(joined).isoformat()
    except (TypeError, ValueError):
        raise ValueError("入会日期必须使用 YYYY-MM-DD 格式") from None
    status = str(row.get("状态", "正常") or "正常").strip()
    if status not in MEMBER_STATUSES:
        raise ValueError("会员状态必须是正常或停用")
    return {
        "会员编号": member_id,
        "会员姓名": name,
        "联系电话": phone,
        "入会日期": joined,
        "状态": status,
        "备注": note,
    }


def normalize_transaction(row, member_ids):
    if not isinstance(row, dict):
        raise ValueError("交易流水必须是对象")
    transaction_id = str(row.get("流水编号", "") or "").strip()
    member_id = str(row.get("会员编号", "") or "").strip()
    kind = str(row.get("交易类型", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", transaction_id):
        raise ValueError("流水编号格式无效")
    if member_id not in member_ids:
        raise ValueError(f"交易流水引用了不存在的会员：{member_id}")
    if kind not in TRANSACTION_TYPES:
        raise ValueError(f"不支持的交易类型：{kind}")
    amount = money_value(row.get("交易金额", "0"), "交易金额")
    points_delta = signed_points(row.get("积分变动", "0"))
    reference = str(row.get("关联消费流水", "") or "").strip()
    if reference and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reference):
        raise ValueError("关联消费流水编号格式无效")
    created_at = str(row.get("发生时间", "") or "").strip()
    try:
        datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        raise ValueError("发生时间必须是有效 ISO 日期时间") from None
    operator = str(row.get("操作人", "") or "").strip() or "本机用户"
    note = str(row.get("备注", "") or "").strip()
    member_name = str(row.get("会员姓名", "") or "").strip()
    if len(operator) > 80 or len(note) > 1000 or len(member_name) > 80:
        raise ValueError("操作人最多 80、流水备注最多 1000、会员姓名最多 80 个字符")
    balance_after = money_value(row.get("储值余额", "0"), "流水后储值余额")
    points_after = signed_points(row.get("积分余额", "0"), "流水后积分余额")
    return {
        "流水编号": transaction_id,
        "会员编号": member_id,
        "会员姓名": member_name,
        "交易类型": kind,
        "交易金额": amount,
        "积分变动": points_delta,
        "关联消费流水": reference,
        "发生时间": created_at,
        "操作人": operator,
        "备注": note,
        "储值余额": balance_after,
        "积分余额": points_after,
    }


def append_event(events, action, reference="", actor="本机用户", reason=""):
    previous = events[-1]["hash"] if events else ""
    body = {
        "seq": len(events) + 1,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "action": str(action),
        "reference": str(reference or ""),
        "actor": str(actor or "本机用户").strip(),
        "reason": str(reason or "").strip(),
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


def replay_transactions(members, raw_transactions):
    member_map = {item["会员编号"]: item for item in members}
    if len(raw_transactions) > MAX_TRANSACTIONS:
        raise ValueError("交易流水超过 200000 条安全上限")
    states = {member_id: {"balance": Decimal("0.00"), "points": 0} for member_id in member_map}
    normalized = []
    by_id = {}
    member_ids = set(member_map)
    consume_by_id = {}
    refund_totals = {}
    refund_points_reversed = {}

    for raw in raw_transactions:
        tx = normalize_transaction(raw, member_ids)
        txid = tx["流水编号"]
        if txid in by_id:
            raise ValueError("交易流水编号重复")
        member_id = tx["会员编号"]
        state = states[member_id]
        amount = Decimal(tx["交易金额"])
        points_delta = tx["积分变动"]
        reference = tx["关联消费流水"]

        if tx["交易类型"] == "充值":
            if amount <= 0 or points_delta != 0 or reference:
                raise ValueError("充值流水金额必须大于 0，且不能修改积分或关联消费")
            state["balance"] += amount
        elif tx["交易类型"] == "消费":
            if amount <= 0 or reference:
                raise ValueError("消费流水金额必须大于 0，且不能关联其他流水")
            if state["balance"] < amount:
                raise ValueError(f"消费流水 {txid} 会导致储值余额为负数")
            expected_points = int(amount)
            if points_delta != expected_points:
                raise ValueError("消费积分必须等于实付金额的整元数")
            state["balance"] -= amount
            state["points"] += points_delta
            consume_by_id[txid] = tx
            refund_totals[txid] = Decimal("0.00")
            refund_points_reversed[txid] = 0
        elif tx["交易类型"] == "退款":
            original = consume_by_id.get(reference)
            if original is None or original["会员编号"] != member_id:
                raise ValueError("退款必须关联同一会员此前的消费流水")
            if amount <= 0:
                raise ValueError("退款金额必须大于 0")
            cumulative = refund_totals[reference] + amount
            original_amount = Decimal(original["交易金额"])
            if cumulative > original_amount:
                raise ValueError("累计退款金额不能超过原消费金额")
            original_points = int(original_amount)
            target_reversed = (
                original_points if cumulative == original_amount
                else int((Decimal(original_points) * cumulative / original_amount).to_integral_value(rounding=ROUND_DOWN))
            )
            expected_delta = -(target_reversed - refund_points_reversed[reference])
            if points_delta != expected_delta:
                raise ValueError("退款积分冲回金额与原消费及累计退款比例不一致")
            refund_totals[reference] = cumulative
            refund_points_reversed[reference] = target_reversed
            state["balance"] += amount
            state["points"] += points_delta
        elif tx["交易类型"] == "积分兑换":
            if amount != 0 or points_delta >= 0 or reference:
                raise ValueError("积分兑换只能减少积分，交易金额必须为 0，且不能关联消费")
            if state["points"] + points_delta < 0:
                raise ValueError("积分余额不足，不能兑换")
            state["points"] += points_delta

        if tx["储值余额"] != format(state["balance"].quantize(CENT), "f"):
            raise ValueError(f"流水 {txid} 的储值余额快照与台账计算不一致")
        if tx["积分余额"] != state["points"]:
            raise ValueError(f"流水 {txid} 的积分余额快照与台账计算不一致")
        by_id[txid] = tx
        normalized.append(tx)

    return normalized, states


class MemberStore:
    def __init__(self, path):
        self.path = Path(path)
        self.members = []
        self.transactions = []
        self.events = []
        self.load()

    @staticmethod
    def _payload(members, transactions, events):
        body = {
            "格式": FORMAT,
            "版本": VERSION,
            "会员": members,
            "交易流水": transactions,
            "操作日志": events,
        }
        return {**body, "SHA256": hashlib.sha256(canonical(body)).hexdigest()}

    @staticmethod
    def decode(payload):
        if not isinstance(payload, dict) or payload.get("格式") != FORMAT or payload.get("版本") != VERSION:
            raise ValueError("会员台账文件格式或版本不受支持")
        body = {key: value for key, value in payload.items() if key != "SHA256"}
        if payload.get("SHA256") != hashlib.sha256(canonical(body)).hexdigest():
            raise ValueError("会员台账 SHA256 校验失败")
        raw_members = body.get("会员")
        raw_transactions = body.get("交易流水")
        events = body.get("操作日志")
        if not isinstance(raw_members, list) or len(raw_members) > MAX_MEMBERS:
            raise ValueError("会员资料缺失或超过 50000 条安全上限")
        if not isinstance(raw_transactions, list) or len(raw_transactions) > MAX_TRANSACTIONS:
            raise ValueError("交易流水缺失或超过 200000 条安全上限")
        members = [normalize_member(item) for item in raw_members]
        ids = [item["会员编号"] for item in members]
        if len(ids) != len(set(ids)):
            raise ValueError("会员编号重复")
        transactions, _ = replay_transactions(members, raw_transactions)
        verify_audit(events)
        return members, transactions, events

    def load(self):
        if not self.path.exists():
            self.members, self.transactions, self.events = [], [], []
            return
        if self.path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("本地会员台账超过 100 MiB，已拒绝加载且原文件未修改")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.members, self.transactions, self.events = self.decode(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"本地会员台账无法读取，原文件未修改：{exc}") from exc

    def _commit(self, members, transactions, events):
        normalized_members = [normalize_member(item) for item in members]
        if len(normalized_members) > MAX_MEMBERS:
            raise ValueError("会员资料超过 50000 条安全上限")
        ids = [item["会员编号"] for item in normalized_members]
        if len(ids) != len(set(ids)):
            raise ValueError("会员编号重复")
        normalized_transactions, _ = replay_transactions(normalized_members, transactions)
        verify_audit(events)
        data = json.dumps(
            self._payload(normalized_members, normalized_transactions, events),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("会员台账超过 100 MiB 安全上限")
        atomic_write(self.path, data)
        self.members = normalized_members
        self.transactions = normalized_transactions
        self.events = events

    def _member(self, member_id):
        item = next((row for row in self.members if row["会员编号"] == member_id), None)
        if item is None:
            raise ValueError("会员不存在")
        return item

    def _states(self):
        _, states = replay_transactions(self.members, self.transactions)
        return states

    def add_member(self, row, actor="本机用户"):
        member = normalize_member(row)
        if any(item["会员编号"] == member["会员编号"] for item in self.members):
            raise ValueError("会员编号已存在")
        events = append_event(self.events, "新增会员", member["会员编号"], actor)
        self._commit(self.members + [member], self.transactions, events)
        return member["会员编号"]

    def update_member(self, member_id, row, actor="本机用户"):
        existing = self._member(member_id)
        values = dict(row)
        values["会员编号"] = member_id
        if not values.get("入会日期"):
            values["入会日期"] = existing["入会日期"]
        normalized = normalize_member(values)
        candidate = [normalized if item["会员编号"] == member_id else item for item in self.members]
        events = append_event(self.events, "更新会员资料", member_id, actor)
        self._commit(candidate, self.transactions, events)

    def set_member_status(self, member_id, status, actor="本机用户", reason=""):
        if status not in MEMBER_STATUSES:
            raise ValueError("会员状态必须是正常或停用")
        existing = self._member(member_id)
        values = dict(existing)
        values["状态"] = status
        candidate = [normalize_member(values) if item["会员编号"] == member_id else item for item in self.members]
        events = append_event(self.events, "修改会员状态", member_id, actor, reason)
        self._commit(candidate, self.transactions, events)

    def _append_transaction(self, member, kind, amount, points_delta, reference="", operator="本机用户", note=""):
        states = self._states()
        state = states[member["会员编号"]]
        balance = state["balance"]
        points = state["points"]
        value = Decimal(money_value(amount, "交易金额"))
        if kind == "充值":
            balance += value
        elif kind == "消费":
            if balance < value:
                raise ValueError("储值余额不足，不能消费")
            balance -= value
        elif kind == "退款":
            balance += value
        elif kind == "积分兑换":
            if points + points_delta < 0:
                raise ValueError("积分余额不足，不能兑换")
        points += points_delta
        tx = {
            "流水编号": "T" + uuid.uuid4().hex[:24].upper(),
            "会员编号": member["会员编号"],
            "会员姓名": member["会员姓名"],
            "交易类型": kind,
            "交易金额": format(value.quantize(CENT), "f"),
            "积分变动": points_delta,
            "关联消费流水": reference,
            "发生时间": datetime.now().astimezone().isoformat(timespec="seconds"),
            "操作人": str(operator or "本机用户").strip()[:80],
            "备注": str(note or "").strip()[:1000],
            "储值余额": format(balance.quantize(CENT), "f"),
            "积分余额": points,
        }
        events = append_event(self.events, kind, tx["流水编号"], operator, note)
        self._commit(self.members, self.transactions + [tx], events)
        return tx["流水编号"]

    def _active_member(self, member_id):
        member = self._member(member_id)
        if member["状态"] != "正常":
            raise ValueError("停用会员不能办理新交易")
        return member

    def recharge(self, member_id, amount, operator="本机用户", note=""):
        member = self._active_member(member_id)
        value = Decimal(money_value(amount, "充值金额"))
        if value <= 0:
            raise ValueError("充值金额必须大于 0")
        return self._append_transaction(member, "充值", value, 0, operator=operator, note=note)

    def consume(self, member_id, amount, operator="本机用户", note=""):
        member = self._active_member(member_id)
        value = Decimal(money_value(amount, "消费金额"))
        if value <= 0:
            raise ValueError("消费金额必须大于 0")
        points = int(value)
        return self._append_transaction(member, "消费", value, points, operator=operator, note=note)

    def refund(self, member_id, amount, reference_id, operator="本机用户", note=""):
        member = self._active_member(member_id)
        original = next((tx for tx in self.transactions if tx["流水编号"] == reference_id), None)
        if original is None or original["交易类型"] != "消费" or original["会员编号"] != member_id:
            raise ValueError("退款必须选择该会员此前的一笔消费流水")
        value = Decimal(money_value(amount, "退款金额"))
        if value <= 0:
            raise ValueError("退款金额必须大于 0")
        prior_refunds = [
            tx for tx in self.transactions
            if tx["交易类型"] == "退款" and tx["关联消费流水"] == reference_id
        ]
        refunded = sum((Decimal(tx["交易金额"]) for tx in prior_refunds), Decimal("0.00"))
        cumulative = refunded + value
        original_amount = Decimal(original["交易金额"])
        if cumulative > original_amount:
            raise ValueError("累计退款金额不能超过原消费金额")
        original_points = int(original_amount)
        target_reversed = (
            original_points if cumulative == original_amount
            else int((Decimal(original_points) * cumulative / original_amount).to_integral_value(rounding=ROUND_DOWN))
        )
        prior_reversed = -sum(tx["积分变动"] for tx in prior_refunds)
        delta = -(target_reversed - prior_reversed)
        return self._append_transaction(member, "退款", value, delta, reference=reference_id, operator=operator, note=note)

    def redeem_points(self, member_id, points, operator="本机用户", note=""):
        member = self._active_member(member_id)
        value = signed_points(points, "兑换积分")
        if value <= 0:
            raise ValueError("兑换积分必须是正整数")
        state = self._states()[member_id]
        if state["points"] < value:
            raise ValueError("积分余额不足，不能兑换")
        return self._append_transaction(member, "积分兑换", "0", -value, operator=operator, note=note)

    def get_balance(self, member_id):
        self._member(member_id)
        state = self._states()[member_id]
        return {"储值余额": format(state["balance"].quantize(CENT), "f"), "积分余额": state["points"]}

    def list_refundable_transactions(self, member_id):
        self._member(member_id)
        refunded = {}
        for tx in self.transactions:
            if tx["交易类型"] == "退款":
                refunded[tx["关联消费流水"]] = refunded.get(tx["关联消费流水"], Decimal("0.00")) + Decimal(tx["交易金额"])
        result = []
        for tx in self.transactions:
            if tx["会员编号"] == member_id and tx["交易类型"] == "消费":
                remaining = Decimal(tx["交易金额"]) - refunded.get(tx["流水编号"], Decimal("0.00"))
                if remaining > 0:
                    result.append({**tx, "可退金额": format(remaining, "f")})
        return result

    def summary(self):
        states = self._states()
        return {
            "会员总数": len(self.members),
            "正常会员": sum(1 for item in self.members if item["状态"] == "正常"),
            "停用会员": sum(1 for item in self.members if item["状态"] == "停用"),
            "储值余额合计": format(sum((state["balance"] for state in states.values()), Decimal("0.00")).quantize(CENT), "f"),
            "积分余额合计": sum(state["points"] for state in states.values()),
            "交易流水数": len(self.transactions),
        }

    def import_members_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("会员 CSV 超过 25 MiB 安全上限")
        incoming = []
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != MEMBER_FIELDS:
                raise ValueError("会员 CSV 表头与本软件模板不一致")
            for line, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"会员 CSV 第 {line} 行列数不正确")
                incoming.append(normalize_member(row))
                if len(incoming) > MAX_MEMBERS:
                    raise ValueError("单次导入会员数量超过 50000 条安全上限")
        ids = [item["会员编号"] for item in incoming]
        existing = {item["会员编号"] for item in self.members}
        if len(ids) != len(set(ids)) or existing.intersection(ids):
            raise ValueError("导入批次存在重复会员编号或与本地会员编号冲突")
        if len(self.members) + len(incoming) > MAX_MEMBERS:
            raise ValueError("导入后会员总数超过 50000 条安全上限")
        if not incoming:
            return 0
        events = append_event(self.events, "批量导入会员", "", "本机用户", f"导入 {len(incoming)} 条")
        self._commit(self.members + incoming, self.transactions, events)
        return len(incoming)

    @staticmethod
    def _write_csv(path, fields, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe(row.get(key, "")) for key in fields})
        atomic_write(path, output.getvalue().encode("utf-8-sig"))

    def export_members_csv(self, path):
        self._write_csv(path, MEMBER_FIELDS, self.members)

    def export_transactions_csv(self, path):
        self._write_csv(path, TRANSACTION_FIELDS, self.transactions)

    def export_balances_csv(self, path):
        states = self._states()
        rows = []
        for member in self.members:
            state = states[member["会员编号"]]
            rows.append({
                **member,
                "储值余额": format(state["balance"].quantize(CENT), "f"),
                "积分余额": state["points"],
            })
        self._write_csv(path, BALANCE_FIELDS, rows)

    def backup(self, path):
        data = json.dumps(self._payload(self.members, self.transactions, self.events), ensure_ascii=False, indent=2).encode("utf-8")
        if len(data) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        atomic_write(path, data)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        members, transactions, events = self.decode(payload)
        events = append_event(events, "恢复备份", "", "本机用户", "从备份文件恢复")
        self._commit(members, transactions, events)

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

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "members.json"
        store = MemberStore(path)
        member_id = store.add_member({"会员姓名": "测试会员", "联系电话": "13800000000"})
        store.recharge(member_id, "100.00")
        consume_id = store.consume(member_id, "30.00")
        store.refund(member_id, "10.00", consume_id)
        store.redeem_points(member_id, 5)
        assert store.get_balance(member_id) == {"储值余额": "80.00", "积分余额": 15}
        backup = Path(folder) / "backup.json"
        store.backup(backup)
        restored = MemberStore(Path(folder) / "restored.json")
        restored.restore(backup)
        assert restored.get_balance(member_id) == store.get_balance(member_id)
        assert restored.audit_summary()["事件数"] >= 1
    if __import__("sys").stdout is not None:
        print("SELF_TEST_OK", flush=True)
