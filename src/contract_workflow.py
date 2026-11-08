"""Offline contract fulfillment milestones, audit trail and deterministic risk rules."""
import csv
import json
import os
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

MILESTONE_FIELDS = ["节点编号", "合同编号", "节点名称", "节点类型", "计划日期", "金额", "状态", "完成日期", "备注"]
MILESTONE_TYPES = ["付款", "收款", "交付", "验收", "保证金", "续约", "其他"]
MILESTONE_STATUSES = ["待处理", "已完成", "已取消"]
AUDIT_FIELDS = ["时间", "合同编号", "节点编号", "操作", "说明"]
WORKFLOW_FORMAT = "mainland-contract-workflow"
WORKFLOW_VERSION = 1


def _money(value):
    try:
        amount = Decimal(str(value or "0").replace(",", "").strip()).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        raise ValueError("节点金额必须是有效数字")
    if not amount.is_finite() or amount < 0:
        raise ValueError("节点金额不能为负数或无效数值")
    return str(amount)


def _iso_date(value, field, optional=False):
    value = str(value or "").strip()
    if optional and not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 日期格式") from exc


def normalize_milestone(row):
    if not isinstance(row, dict):
        raise ValueError("履约节点必须是对象")
    item = {field: str(row.get(field, "")).strip() for field in MILESTONE_FIELDS}
    if not item["节点编号"] or not item["合同编号"] or not item["节点名称"]:
        raise ValueError("节点编号、合同编号和节点名称不能为空")
    if item["节点类型"] not in MILESTONE_TYPES:
        raise ValueError("节点类型无效")
    item["计划日期"] = _iso_date(item["计划日期"], "计划日期")
    item["金额"] = _money(item["金额"])
    if item["状态"] not in MILESTONE_STATUSES:
        raise ValueError("节点状态无效")
    item["完成日期"] = _iso_date(item["完成日期"], "完成日期", optional=True)
    if item["状态"] == "已完成" and not item["完成日期"]:
        raise ValueError("已完成节点必须填写完成日期")
    if item["状态"] != "已完成" and item["完成日期"]:
        raise ValueError("只有已完成节点可以填写完成日期")
    return item


def normalize_audit(row):
    if not isinstance(row, dict):
        raise ValueError("操作记录必须是对象")
    item = {field: str(row.get(field, "")).strip() for field in AUDIT_FIELDS}
    if not item["时间"] or not item["操作"]:
        raise ValueError("操作记录缺少时间或操作名称")
    try:
        datetime.fromisoformat(item["时间"])
    except ValueError as exc:
        raise ValueError("操作记录时间格式无效") from exc
    return item


class WorkflowStore:
    """Stores milestones and audit events separately from the legacy contracts.json list."""

    def __init__(self, path):
        self.path = Path(path)
        self.milestones = []
        self.audit = []
        self.load()

    @staticmethod
    def validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError("履约数据根对象必须是对象")
        if payload.get("format") != WORKFLOW_FORMAT:
            raise ValueError("履约数据格式不受支持")
        if type(payload.get("version")) is not int or payload.get("version") != WORKFLOW_VERSION:
            raise ValueError("履约数据版本不受支持")
        raw_milestones = payload.get("milestones")
        raw_audit = payload.get("audit")
        if not isinstance(raw_milestones, list) or not isinstance(raw_audit, list):
            raise ValueError("履约数据缺少节点或操作记录列表")
        milestones = [normalize_milestone(row) for row in raw_milestones]
        ids = [row["节点编号"] for row in milestones]
        if len(ids) != len(set(ids)):
            raise ValueError("履约节点编号重复")
        audit = [normalize_audit(row) for row in raw_audit]
        return milestones, audit

    def load(self):
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.milestones, self.audit = self.validate_payload(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"履约数据无法读取，原文件未修改：{exc}") from exc

    def payload(self):
        return {
            "format": WORKFLOW_FORMAT,
            "version": WORKFLOW_VERSION,
            "milestones": self.milestones,
            "audit": self.audit[-5000:],
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.payload(), ensure_ascii=False, indent=2)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _append_audit(self, contract_id, milestone_id, action, note=""):
        self.audit.append({
            "时间": datetime.now().isoformat(timespec="seconds"),
            "合同编号": str(contract_id),
            "节点编号": str(milestone_id),
            "操作": str(action),
            "说明": str(note),
        })
        self.audit = self.audit[-5000:]

    def record_action(self, contract_id, action, note=""):
        old = self.audit[:]
        self._append_audit(contract_id, "", action, note)
        try:
            self.save()
        except Exception:
            self.audit = old
            raise

    def add(self, contract_id, row):
        item = dict(row)
        item["节点编号"] = item.get("节点编号") or uuid.uuid4().hex[:12].upper()
        item["合同编号"] = str(contract_id)
        item = normalize_milestone(item)
        if any(existing["节点编号"] == item["节点编号"] for existing in self.milestones):
            raise ValueError("履约节点编号已存在")
        old_audit = self.audit[:]
        self.milestones.append(item)
        self._append_audit(contract_id, item["节点编号"], "新增节点", item["节点名称"])
        try:
            self.save()
        except Exception:
            self.milestones.pop()
            self.audit = old_audit
            raise
        return item

    def update(self, milestone_id, row, action="修改节点"):
        index = next((i for i, item in enumerate(self.milestones) if item["节点编号"] == milestone_id), None)
        if index is None:
            raise ValueError("找不到履约节点")
        old = self.milestones[index]
        old_audit = self.audit[:]
        item = dict(row)
        item["节点编号"] = milestone_id
        item["合同编号"] = old["合同编号"]
        item = normalize_milestone(item)
        self.milestones[index] = item
        self._append_audit(item["合同编号"], milestone_id, action, item["节点名称"])
        try:
            self.save()
        except Exception:
            self.milestones[index] = old
            self.audit = old_audit
            raise
        return item

    def complete(self, milestone_id, completed_date=None):
        old = next((item for item in self.milestones if item["节点编号"] == milestone_id), None)
        if old is None:
            raise ValueError("找不到履约节点")
        if old["状态"] == "已取消":
            raise ValueError("已取消节点不能标记完成")
        row = dict(old)
        row["状态"] = "已完成"
        row["完成日期"] = _iso_date(completed_date or date.today().isoformat(), "完成日期")
        return self.update(milestone_id, row, action="标记完成")

    def delete(self, milestone_id):
        index = next((i for i, item in enumerate(self.milestones) if item["节点编号"] == milestone_id), None)
        if index is None:
            raise ValueError("找不到履约节点")
        old_audit = self.audit[:]
        old = self.milestones.pop(index)
        self._append_audit(old["合同编号"], milestone_id, "删除节点", old["节点名称"])
        try:
            self.save()
        except Exception:
            self.milestones.insert(index, old)
            self.audit = old_audit
            raise

    def import_csv(self, path, contract_ids):
        incoming = []
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(MILESTONE_FIELDS).issubset(reader.fieldnames):
                raise ValueError("CSV 缺少必要字段：" + "、".join(MILESTONE_FIELDS))
            for line, raw in enumerate(reader, 2):
                try:
                    item = normalize_milestone(raw)
                    if item["合同编号"] not in contract_ids:
                        raise ValueError(f"找不到合同 {item['合同编号']}")
                    incoming.append(item)
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        ids = [item["节点编号"] for item in incoming]
        existing = {item["节点编号"] for item in self.milestones}
        duplicates = existing.intersection(ids)
        if len(ids) != len(set(ids)) or duplicates:
            raise ValueError("导入包含重复节点编号，整批未导入")
        old_milestones = self.milestones[:]
        old_audit = self.audit[:]
        self.milestones.extend(incoming)
        for item in incoming:
            self._append_audit(item["合同编号"], item["节点编号"], "CSV导入", item["节点名称"])
        try:
            self.save()
        except Exception:
            self.milestones = old_milestones
            self.audit = old_audit
            raise
        return len(incoming)

    def export_csv(self, path, rows=None):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MILESTONE_FIELDS)
            writer.writeheader()
            writer.writerows(self.milestones if rows is None else rows)

    def restore_payload(self, payload):
        milestones, audit = self.validate_payload(payload)
        old_milestones, old_audit = self.milestones[:], self.audit[:]
        self.milestones, self.audit = milestones, audit[-5000:]
        try:
            self.save()
        except Exception:
            self.milestones, self.audit = old_milestones, old_audit
            raise


def risk_findings(contracts, milestones, today=None):
    """Deterministic operational checks; these are not legal opinions."""
    today = today or date.today()
    contract_map = {row["合同编号"]: row for row in contracts}
    grouped = {}
    findings = []

    def add(severity, code, contract_id, message, action):
        findings.append({
            "等级": severity,
            "规则编号": code,
            "合同编号": contract_id,
            "风险说明": message,
            "建议动作": action,
        })

    for item in milestones:
        grouped.setdefault(item["合同编号"], []).append(item)

    for contract_id, contract in contract_map.items():
        active = contract.get("状态") in ("执行中", "待续约")
        if active and (not contract.get("甲方/客户") or not contract.get("乙方/供应商")):
            add("中", "PARTY_MISSING", contract_id, "合同一方信息不完整", "核对合同原件并补齐双方主体信息")
        if active and Decimal(contract.get("合同金额", "0")) == 0:
            add("低", "AMOUNT_ZERO", contract_id, "合同金额为 0，请确认是否为无偿或未录入", "核对合同金额及币种")
        if active and date.fromisoformat(contract["到期日期"]) < today:
            add("高", "CONTRACT_EXPIRED", contract_id, "执行中合同已超过登记到期日", "核实续签、终止或状态是否需要更新")

        rows = [m for m in grouped.get(contract_id, []) if m["状态"] != "已取消"]
        if active and Decimal(contract.get("合同金额", "0")) > 0 and not rows:
            add("低", "NO_MILESTONES", contract_id, "尚未建立付款、交付或验收等履约节点", "按合同约定拆分履约节点")

        totals = {"付款": Decimal("0"), "收款": Decimal("0")}
        for milestone in rows:
            due = date.fromisoformat(milestone["计划日期"])
            if due < date.fromisoformat(contract["生效日期"]) or due > date.fromisoformat(contract["到期日期"]):
                add("中", "MILESTONE_OUTSIDE_TERM", contract_id,
                    f"节点“{milestone['节点名称']}”计划日期不在合同期限内", "核对合同期限或节点日期")
            if milestone["状态"] == "待处理":
                days = (due - today).days
                if days < 0:
                    add("高", "MILESTONE_OVERDUE", contract_id,
                        f"履约节点“{milestone['节点名称']}”已逾期 {abs(days)} 天", "联系责任人核实进度并记录处理结果")
                elif days <= 7:
                    add("中", "MILESTONE_DUE_SOON", contract_id,
                        f"履约节点“{milestone['节点名称']}”将在 {days} 天内到期", "提前安排付款、交付或验收")
            if milestone["节点类型"] in totals:
                totals[milestone["节点类型"]] += Decimal(milestone["金额"])
        contract_amount = Decimal(contract.get("合同金额", "0"))
        for kind, total in totals.items():
            if total > contract_amount:
                code_name = "PAYMENT" if kind == "付款" else "RECEIPT"
                add("高", f"{code_name}_PLAN_EXCEEDS_AMOUNT", contract_id,
                    f"{kind}节点合计 {total:.2f}，超过合同金额 {contract_amount:.2f}", "核对节点金额、重复录入及合同变更")

    for milestone in milestones:
        if milestone["合同编号"] not in contract_map:
            add("高", "ORPHAN_MILESTONE", milestone["合同编号"],
                f"节点“{milestone['节点名称']}”关联的合同不存在", "恢复合同记录或删除无效节点")

    order = {"高": 0, "中": 1, "低": 2}
    return sorted(findings, key=lambda item: (order[item["等级"]], item["合同编号"], item["规则编号"], item["风险说明"]))


def finance_summary(milestones):
    totals = {
        "待付款": Decimal("0"), "待收款": Decimal("0"),
        "已完成付款": Decimal("0"), "已完成收款": Decimal("0"),
    }
    for item in milestones:
        if item["状态"] == "已取消":
            continue
        if item["节点类型"] == "付款":
            key = "已完成付款" if item["状态"] == "已完成" else "待付款"
            totals[key] += Decimal(item["金额"])
        elif item["节点类型"] == "收款":
            key = "已完成收款" if item["状态"] == "已完成" else "待收款"
            totals[key] += Decimal(item["金额"])
    return {key: f"{value:.2f}" for key, value in totals.items()}
