"""Offline rental rent, payment and deposit ledger with deterministic checks."""
import calendar
import copy
import csv
import io
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-rental-ledger"
VERSION = 1
AUDIT_LIMIT = 5000

LEASE_FIELDS = [
    "租约编号", "房产/房间", "租客", "联系电话", "起租日期", "退租日期",
    "月租金(元)", "每月缴租日", "应收押金(元)", "状态", "备注",
]
CHARGE_FIELDS = [
    "账单编号", "租约编号", "账期(月)", "应收日期", "应收金额(元)", "备注",
]
PAYMENT_FIELDS = [
    "收款编号", "账单编号", "收款日期", "金额(元)", "方式", "流水号", "备注",
]
DEPOSIT_FIELDS = [
    "押金流水号", "租约编号", "日期", "类型", "金额(元)", "说明",
]
AUDIT_FIELDS = ["时间", "类别", "编号", "操作", "说明"]
LEASE_STATUSES = ["有效", "已退租", "已终止"]
DEPOSIT_TYPES = ["收取", "扣除", "退还"]


def _text(value):
    return str(value if value is not None else "").strip()


def _decimal(value, field, allow_negative=False):
    try:
        number = Decimal(str(value if value is not None else "0").replace(",", "").replace("，", "").strip() or "0")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field}必须是有效数字") from exc
    if not number.is_finite() or (not allow_negative and number < 0):
        raise ValueError(f"{field}不能为负数或非有限数")
    return number


def money(value, field="金额", allow_negative=False):
    number = _decimal(value, field, allow_negative=allow_negative)
    try:
        return format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    except InvalidOperation as exc:
        raise ValueError(f"{field}超出可处理金额范围") from exc


def _date(value, field, required=False):
    raw = _text(value)
    if not raw:
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式")
    return raw


def _month(value):
    raw = _text(value)
    try:
        parsed = datetime.strptime(raw, "%Y-%m")
    except ValueError as exc:
        raise ValueError("账期必须使用 YYYY-MM 格式") from exc
    if parsed.strftime("%Y-%m") != raw:
        raise ValueError("账期必须使用 YYYY-MM 格式")
    return parsed.year, parsed.month


def _month_iter(start_month, end_month):
    sy, sm = _month(start_month)
    ey, em = _month(end_month)
    if (ey, em) < (sy, sm):
        raise ValueError("结束月份不能早于开始月份")
    year, month = sy, sm
    while (year, month) <= (ey, em):
        yield f"{year:04d}-{month:02d}"
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def _atomic_write(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(content, encoding="utf-8", newline="")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()

def normalize_lease(row):
    if not isinstance(row, dict):
        raise ValueError("租约记录格式错误")
    item = {field: _text(row.get(field, "")) for field in LEASE_FIELDS}
    for field in ("租约编号", "房产/房间", "租客"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["起租日期"] = _date(item["起租日期"], "起租日期", required=True)
    item["退租日期"] = _date(item["退租日期"], "退租日期")
    if item["退租日期"] and item["退租日期"] < item["起租日期"]:
        raise ValueError("退租日期不能早于起租日期")
    if item["状态"] not in LEASE_STATUSES:
        raise ValueError("租约状态不正确")
    if item["状态"] != "有效" and not item["退租日期"]:
        raise ValueError("已退租或已终止的租约必须填写退租日期")
    item["月租金(元)"] = money(item["月租金(元)"], "月租金")
    if Decimal(item["月租金(元)"]) <= 0:
        raise ValueError("月租金必须大于 0")
    due = _decimal(item["每月缴租日"], "每月缴租日")
    if due != due.to_integral_value() or not 1 <= int(due) <= 28:
        raise ValueError("每月缴租日必须是 1 到 28 的整数")
    item["每月缴租日"] = str(int(due))
    item["应收押金(元)"] = money(item["应收押金(元)"], "应收押金")
    return item


def charge_for_month(lease, period):
    year, month = _month(period)
    lease_start = date.fromisoformat(lease["起租日期"])
    lease_end = date.fromisoformat(lease["退租日期"]) if lease["退租日期"] else date.max
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    occupied_start = max(lease_start, month_start)
    occupied_end = min(lease_end, month_end)
    if occupied_start > occupied_end:
        return None
    occupied_days = (occupied_end - occupied_start).days + 1
    month_days = (month_end - month_start).days + 1
    amount = (
        Decimal(lease["月租金(元)"]) * Decimal(occupied_days) / Decimal(month_days)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    due_day = min(int(lease["每月缴租日"]), month_days)
    due = date(year, month, due_day)
    if due < occupied_start:
        due = occupied_start
    if due > occupied_end:
        due = occupied_end
    return {
        "账单编号": f"{lease['租约编号']}:{period}",
        "租约编号": lease["租约编号"],
        "账期(月)": period,
        "应收日期": due.isoformat(),
        "应收金额(元)": format(amount, "f"),
        "备注": "",
    }


def normalize_charge(row, lease):
    if not isinstance(row, dict):
        raise ValueError("租金账单记录格式错误")
    item = {field: _text(row.get(field, "")) for field in CHARGE_FIELDS}
    for field in ("账单编号", "租约编号", "账期(月)"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if item["租约编号"] != lease["租约编号"]:
        raise ValueError("账单引用的租约编号不匹配")
    expected = charge_for_month(lease, item["账期(月)"])
    if expected is None:
        raise ValueError("账期不在租约有效日期范围内")
    if item["账单编号"] != expected["账单编号"]:
        raise ValueError("账单编号与租约及账期不匹配")
    supplied_amount = item["应收金额(元)"]
    if supplied_amount and money(supplied_amount, "应收金额") != expected["应收金额(元)"]:
        raise ValueError("应收金额与按日折算规则计算结果不一致")
    supplied_due = item["应收日期"]
    if supplied_due and _date(supplied_due, "应收日期", required=True) != expected["应收日期"]:
        raise ValueError("应收日期与租约缴租规则不一致")
    return {**expected, "备注": item["备注"]}


def normalize_payment(row, charge_map):
    if not isinstance(row, dict):
        raise ValueError("收款记录格式错误")
    item = {field: _text(row.get(field, "")) for field in PAYMENT_FIELDS}
    for field in ("收款编号", "账单编号", "收款日期", "方式"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["收款日期"] = _date(item["收款日期"], "收款日期", required=True)
    item["金额(元)"] = money(item["金额(元)"], "收款金额")
    if Decimal(item["金额(元)"]) <= 0:
        raise ValueError("收款金额必须大于 0")
    if item["账单编号"] not in charge_map:
        raise ValueError("收款记录引用了不存在的租金账单")
    return item


def normalize_deposit(row, lease_map):
    if not isinstance(row, dict):
        raise ValueError("押金流水记录格式错误")
    item = {field: _text(row.get(field, "")) for field in DEPOSIT_FIELDS}
    for field in ("押金流水号", "租约编号", "日期", "类型", "说明"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["日期"] = _date(item["日期"], "押金日期", required=True)
    if item["租约编号"] not in lease_map:
        raise ValueError("押金流水引用了不存在的租约")
    if item["类型"] not in DEPOSIT_TYPES:
        raise ValueError("押金流水类型不正确")
    item["金额(元)"] = money(item["金额(元)"], "押金金额")
    if Decimal(item["金额(元)"]) <= 0:
        raise ValueError("押金流水金额必须大于 0")
    return item


class RentalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.leases = []
        self.charges = []
        self.payments = []
        self.deposits = []
        self.audit = []
        self.load()

    def _payload(self):
        return {
            "format": FORMAT, "version": VERSION,
            "leases": self.leases, "charges": self.charges,
            "payments": self.payments, "deposits": self.deposits,
            "audit": self.audit,
        }

    def _validate_all(self, leases, charges, payments, deposits, audit):
        if not all(isinstance(value, list) for value in (leases, charges, payments, deposits, audit)):
            raise ValueError("租约、账单、收款、押金和操作记录必须都是数组")
        normalized_leases = [normalize_lease(row) for row in leases]
        lease_ids = [row["租约编号"] for row in normalized_leases]
        if len(lease_ids) != len(set(lease_ids)):
            raise ValueError("租约编号重复")
        lease_map = {row["租约编号"]: row for row in normalized_leases}

        normalized_charges = []
        for row in charges:
            lease = lease_map.get(_text(row.get("租约编号")) if isinstance(row, dict) else "")
            if lease is None:
                raise ValueError("租金账单引用了不存在的租约")
            normalized_charges.append(normalize_charge(row, lease))
        charge_ids = [row["账单编号"] for row in normalized_charges]
        if len(charge_ids) != len(set(charge_ids)):
            raise ValueError("账单编号重复")
        charge_map = {row["账单编号"]: row for row in normalized_charges}

        normalized_payments = [normalize_payment(row, charge_map) for row in payments]
        payment_ids = [row["收款编号"] for row in normalized_payments]
        if len(payment_ids) != len(set(payment_ids)):
            raise ValueError("收款编号重复")
        paid_by_charge = {}
        for row in normalized_payments:
            paid_by_charge[row["账单编号"]] = (
                paid_by_charge.get(row["账单编号"], Decimal("0")) + Decimal(row["金额(元)"])
            )
        for charge_id, paid in paid_by_charge.items():
            if paid > Decimal(charge_map[charge_id]["应收金额(元)"]):
                raise ValueError(f"账单 {charge_id} 的累计收款超过应收金额，请拆分到正确账期")

        normalized_deposits = [normalize_deposit(row, lease_map) for row in deposits]
        deposit_ids = [row["押金流水号"] for row in normalized_deposits]
        if len(deposit_ids) != len(set(deposit_ids)):
            raise ValueError("押金流水号重复")
        running = {}
        for row in sorted(
            normalized_deposits,
            key=lambda x: (x["租约编号"], x["日期"], 0 if x["类型"] == "收取" else 1, x["押金流水号"]),
        ):
            lease_id = row["租约编号"]
            delta = Decimal(row["金额(元)"]) if row["类型"] == "收取" else -Decimal(row["金额(元)"])
            running[lease_id] = running.get(lease_id, Decimal("0")) + delta
            if running[lease_id] < 0:
                raise ValueError(f"租约 {lease_id} 的押金扣除/退还超过当时可用余额")

        if not isinstance(audit, list):
            raise ValueError("操作记录必须是数组")
        normalized_audit = []
        for event in audit[-AUDIT_LIMIT:]:
            if not isinstance(event, dict):
                raise ValueError("操作记录格式错误")
            normalized_audit.append({field: _text(event.get(field, "")) for field in AUDIT_FIELDS})
        return normalized_leases, normalized_charges, normalized_payments, normalized_deposits, normalized_audit

    def load(self):
        if not self.path.exists():
            self.leases, self.charges, self.payments, self.deposits, self.audit = [], [], [], [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != FORMAT:
                raise ValueError("租赁数据文件格式不受支持")
            if type(payload.get("version")) is not int or payload["version"] != VERSION:
                raise ValueError("租赁数据文件版本不受支持")
            validated = self._validate_all(
                payload.get("leases"), payload.get("charges"), payload.get("payments"),
                payload.get("deposits"), payload.get("audit"),
            )
            self.leases, self.charges, self.payments, self.deposits, self.audit = validated
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"租赁数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        validated = self._validate_all(
            self.leases, self.charges, self.payments, self.deposits, self.audit
        )
        self.leases, self.charges, self.payments, self.deposits, self.audit = validated
        _atomic_write(self.path, json.dumps(self._payload(), ensure_ascii=False, indent=2))

    def _mutate(self, category, record_id, action, description, operation):
        snapshot = (
            copy.deepcopy(self.leases), copy.deepcopy(self.charges),
            copy.deepcopy(self.payments), copy.deepcopy(self.deposits),
            copy.deepcopy(self.audit),
        )
        try:
            operation()
            self.audit.append({
                "时间": datetime.now().isoformat(timespec="seconds"),
                "类别": category, "编号": record_id, "操作": action, "说明": description,
            })
            self.audit = self.audit[-AUDIT_LIMIT:]
            self.save()
        except Exception:
            self.leases, self.charges, self.payments, self.deposits, self.audit = snapshot
            raise

    def _lease(self, lease_id):
        lease = next((row for row in self.leases if row["租约编号"] == lease_id), None)
        if lease is None:
            raise ValueError("找不到租约：" + str(lease_id))
        return lease

    def add_lease(self, row):
        item = normalize_lease(row)
        if any(x["租约编号"] == item["租约编号"] for x in self.leases):
            raise ValueError("租约编号已存在")
        self._mutate("租约", item["租约编号"], "新增", item["房产/房间"], lambda: self.leases.append(item))
        return item["租约编号"]

    def update_lease(self, old_id, row):
        item = normalize_lease(row)
        if item["租约编号"] != old_id:
            raise ValueError("租约编号创建后不能修改")
        index = next((i for i, x in enumerate(self.leases) if x["租约编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的租约")
        self._mutate("租约", old_id, "修改", item["房产/房间"], lambda: self.leases.__setitem__(index, item))

    def delete_lease(self, lease_id):
        if any(x["租约编号"] == lease_id for x in self.charges) or any(
            x["租约编号"] == lease_id for x in self.deposits
        ) or any(
            next((c for c in self.charges if c["账单编号"] == p["账单编号"]), {}).get("租约编号") == lease_id
            for p in self.payments
        ):
            raise ValueError("租约仍有关联账单、收款或押金流水，不能删除")
        index = next((i for i, x in enumerate(self.leases) if x["租约编号"] == lease_id), None)
        if index is None:
            raise ValueError("找不到要删除的租约")
        self._mutate("租约", lease_id, "删除", "删除租约", lambda: self.leases.pop(index))

    def generate_charges(self, lease_id, through_month):
        lease = self._lease(lease_id)
        start_month = date.fromisoformat(lease["起租日期"]).strftime("%Y-%m")
        end_month = through_month
        if lease["退租日期"]:
            end_month = min(end_month, date.fromisoformat(lease["退租日期"]).strftime("%Y-%m"))
        incoming = []
        existing = {x["账单编号"] for x in self.charges}
        for period in _month_iter(start_month, end_month):
            row = charge_for_month(lease, period)
            if row and row["账单编号"] not in existing:
                incoming.append(row)
        if incoming:
            self._mutate("租金账单", lease_id, "生成", f"新增 {len(incoming)} 期账单",
                         lambda: self.charges.extend(incoming))
        return len(incoming)

    def delete_charge(self, charge_id):
        if any(x["账单编号"] == charge_id for x in self.payments):
            raise ValueError("账单已有收款记录，不能删除")
        index = next((i for i, x in enumerate(self.charges) if x["账单编号"] == charge_id), None)
        if index is None:
            raise ValueError("找不到要删除的账单")
        self._mutate("租金账单", charge_id, "删除", "删除账单", lambda: self.charges.pop(index))

    def add_payment(self, row):
        item = normalize_payment(row, {x["账单编号"]: x for x in self.charges})
        if any(x["收款编号"] == item["收款编号"] for x in self.payments):
            raise ValueError("收款编号已存在")
        self._mutate("收款", item["收款编号"], "新增", item["账单编号"], lambda: self.payments.append(item))
        return item["收款编号"]

    def update_payment(self, old_id, row):
        item = normalize_payment(row, {x["账单编号"]: x for x in self.charges})
        if item["收款编号"] != old_id:
            raise ValueError("收款编号创建后不能修改")
        index = next((i for i, x in enumerate(self.payments) if x["收款编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的收款")
        self._mutate("收款", old_id, "修改", item["账单编号"], lambda: self.payments.__setitem__(index, item))

    def delete_payment(self, payment_id):
        index = next((i for i, x in enumerate(self.payments) if x["收款编号"] == payment_id), None)
        if index is None:
            raise ValueError("找不到要删除的收款")
        self._mutate("收款", payment_id, "删除", "删除收款", lambda: self.payments.pop(index))

    def add_deposit(self, row):
        item = normalize_deposit(row, {x["租约编号"]: x for x in self.leases})
        if any(x["押金流水号"] == item["押金流水号"] for x in self.deposits):
            raise ValueError("押金流水号已存在")
        self._mutate("押金", item["押金流水号"], "新增", item["类型"], lambda: self.deposits.append(item))
        return item["押金流水号"]

    def update_deposit(self, old_id, row):
        item = normalize_deposit(row, {x["租约编号"]: x for x in self.leases})
        if item["押金流水号"] != old_id:
            raise ValueError("押金流水号创建后不能修改")
        index = next((i for i, x in enumerate(self.deposits) if x["押金流水号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的押金流水")
        self._mutate("押金", old_id, "修改", item["类型"], lambda: self.deposits.__setitem__(index, item))

    def delete_deposit(self, deposit_id):
        index = next((i for i, x in enumerate(self.deposits) if x["押金流水号"] == deposit_id), None)
        if index is None:
            raise ValueError("找不到要删除的押金流水")
        self._mutate("押金", deposit_id, "删除", "删除押金流水", lambda: self.deposits.pop(index))

    def deposit_balance(self, lease_id):
        balance = Decimal("0")
        events = sorted(
            (x for x in self.deposits if x["租约编号"] == lease_id),
            key=lambda x: (x["日期"], 0 if x["类型"] == "收取" else 1, x["押金流水号"]),
        )
        for row in events:
            amount = Decimal(row["金额(元)"])
            balance += amount if row["类型"] == "收取" else -amount
        return money(balance, "押金余额")

    def rent_rows(self, today=None):
        today = today or date.today()
        if isinstance(today, str):
            today = date.fromisoformat(_date(today, "检查日期", required=True))
        result = []
        for charge in self.charges:
            paid = sum(
                (Decimal(x["金额(元)"]) for x in self.payments if x["账单编号"] == charge["账单编号"]),
                Decimal("0"),
            )
            due = Decimal(charge["应收金额(元)"])
            outstanding = due - paid
            due_date = date.fromisoformat(charge["应收日期"])
            if outstanding <= 0:
                status = "已结清"
            elif due_date < today:
                status = "逾期"
            elif paid > 0:
                status = "部分收款"
            else:
                status = "待收"
            result.append({
                **charge,
                "已收金额(元)": money(paid),
                "未收金额(元)": money(outstanding),
                "状态": status,
            })
        return sorted(result, key=lambda x: (x["应收日期"], x["账单编号"]))

    def risk_findings(self, today=None):
        today = today or date.today()
        if isinstance(today, str):
            today = date.fromisoformat(_date(today, "检查日期", required=True))
        findings = []
        lease_map = {x["租约编号"]: x for x in self.leases}
        for lease in self.leases:
            lease_end = date.fromisoformat(lease["退租日期"]) if lease["退租日期"] else None
            if lease["状态"] == "有效" and lease_end:
                days_left = (lease_end - today).days
                if days_left < 0:
                    findings.append({"等级": "高", "规则编号": "ACTIVE_LEASE_PAST_END",
                                     "编号": lease["租约编号"], "说明": "租约已过退租日期但状态仍为有效"})
                elif days_left <= 30:
                    findings.append({"等级": "中", "规则编号": "LEASE_END_WITHIN_30_DAYS",
                                     "编号": lease["租约编号"], "说明": f"租约将在 {days_left} 天内到期"})
            balance = Decimal(self.deposit_balance(lease["租约编号"]))
            expected = Decimal(lease["应收押金(元)"])
            if lease["状态"] == "有效" and balance < expected:
                findings.append({"等级": "中", "规则编号": "DEPOSIT_BELOW_EXPECTED",
                                 "编号": lease["租约编号"], "说明": "当前押金余额低于租约约定应收押金"})
            if lease["状态"] != "有效" and balance > 0:
                findings.append({"等级": "中", "规则编号": "DEPOSIT_NOT_SETTLED",
                                 "编号": lease["租约编号"], "说明": "租约已结束但仍有押金余额，建议核对扣款与退还"})
        for row in self.rent_rows(today):
            outstanding = Decimal(row["未收金额(元)"])
            if outstanding > 0 and row["状态"] == "逾期":
                findings.append({"等级": "高", "规则编号": "RENT_OVERDUE",
                                 "编号": row["账单编号"], "说明": f"租金逾期未收 {row['未收金额(元)']} 元"})
            elif outstanding > 0 and (date.fromisoformat(row["应收日期"]) - today).days <= 7:
                findings.append({"等级": "中", "规则编号": "RENT_DUE_WITHIN_7_DAYS",
                                 "编号": row["账单编号"], "说明": f"租金将在 7 天内到期，未收 {row['未收金额(元)']} 元"})
        return findings

    def _read_csv(self, path, fields):
        rows = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(fields) or set(headers) != set(fields):
                raise ValueError("CSV 必须且只能包含全部规定字段：" + "、".join(fields))
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余列")
                rows.append(row)
        return rows

    def import_csv(self, kind, path):
        if kind == "leases":
            incoming = [normalize_lease(x) for x in self._read_csv(path, LEASE_FIELDS)]
            field, existing = "租约编号", {x["租约编号"] for x in self.leases}
            target = self.leases
        elif kind == "charges":
            raw = self._read_csv(path, CHARGE_FIELDS)
            lease_map = {x["租约编号"]: x for x in self.leases}
            incoming = []
            for row in raw:
                lease = lease_map.get(_text(row.get("租约编号")))
                if lease is None:
                    raise ValueError("导入账单引用了不存在的租约，整批未导入")
                incoming.append(normalize_charge(row, lease))
            field, existing = "账单编号", {x["账单编号"] for x in self.charges}
            target = self.charges
        elif kind == "payments":
            raw = self._read_csv(path, PAYMENT_FIELDS)
            charge_map = {x["账单编号"]: x for x in self.charges}
            incoming = [normalize_payment(x, charge_map) for x in raw]
            field, existing = "收款编号", {x["收款编号"] for x in self.payments}
            target = self.payments
        elif kind == "deposits":
            raw = self._read_csv(path, DEPOSIT_FIELDS)
            lease_map = {x["租约编号"]: x for x in self.leases}
            incoming = [normalize_deposit(x, lease_map) for x in raw]
            field, existing = "押金流水号", {x["押金流水号"] for x in self.deposits}
            target = self.deposits
        else:
            raise ValueError("未知 CSV 数据类别")
        ids = [x[field] for x in incoming]
        if len(ids) != len(set(ids)):
            raise ValueError("导入文件存在重复编号，整批未导入")
        if existing.intersection(ids):
            raise ValueError("导入包含已存在编号，整批未导入")
        self._mutate("CSV", kind, "批量导入", str(len(incoming)), lambda: target.extend(incoming))
        return len(incoming)

    def export_csv(self, kind, path):
        mapping = {
            "leases": (LEASE_FIELDS, self.leases),
            "charges": (CHARGE_FIELDS, self.charges),
            "payments": (PAYMENT_FIELDS, self.payments),
            "deposits": (DEPOSIT_FIELDS, self.deposits),
        }
        if kind not in mapping:
            raise ValueError("未知 CSV 数据类别")
        fields, rows = mapping[kind]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        _atomic_write(path, "\ufeff" + output.getvalue())

    def backup(self, path):
        payload = self._payload()
        payload["created_at"] = datetime.now().isoformat(timespec="seconds")
        _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def restore(self, path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"备份文件无法读取：{exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != FORMAT:
            raise ValueError("备份文件格式不受支持")
        if type(payload.get("version")) is not int or payload["version"] != VERSION:
            raise ValueError("备份文件版本不受支持")
        validated = self._validate_all(
            payload.get("leases"), payload.get("charges"), payload.get("payments"),
            payload.get("deposits"), payload.get("audit"),
        )
        snapshot = (self.leases, self.charges, self.payments, self.deposits, self.audit)
        self.leases, self.charges, self.payments, self.deposits, self.audit = validated
        try:
            self.save()
        except Exception:
            self.leases, self.charges, self.payments, self.deposits, self.audit = snapshot
            raise


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "rental_ledger.json"


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        store = RentalStore(Path(directory) / "rental.json")
        lease = {
            "租约编号": "R001", "房产/房间": "A-101", "租客": "测试租客",
            "联系电话": "", "起租日期": "2026-01-15", "退租日期": "2026-12-31",
            "月租金(元)": "3100", "每月缴租日": "5", "应收押金(元)": "3100",
            "状态": "有效", "备注": "",
        }
        store.add_lease(lease)
        assert store.generate_charges("R001", "2026-01") == 1
        assert store.charges[0]["应收金额(元)"] == "1700.00"
        store.add_payment({
            "收款编号": "P001", "账单编号": "R001:2026-01",
            "收款日期": "2026-01-20", "金额(元)": "1700",
            "方式": "银行转账", "流水号": "", "备注": "",
        })
        store.add_deposit({
            "押金流水号": "D001", "租约编号": "R001", "日期": "2026-01-15",
            "类型": "收取", "金额(元)": "3100", "说明": "押金",
        })
        assert store.deposit_balance("R001") == "3100.00"
        assert store.rent_rows("2026-01-21")[0]["状态"] == "已结清"
        backup = Path(directory) / "backup.json"
        store.backup(backup)
        restored = RentalStore(Path(directory) / "restored.json")
        restored.restore(backup)
        assert restored.leases == store.leases
        assert restored.charges == store.charges
        assert restored.payments == store.payments
        assert restored.deposits == store.deposits
    if os.getenv("MAINLAND_EXE_SELF_TEST") == "1" or __name__ == "__main__":
        print("SELF_TEST_OK", flush=True)
