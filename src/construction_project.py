"""Deterministic offline construction variation and progress-payment ledger."""
import csv
import copy
import hashlib
import io
import json
import os
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-construction-settlement"
VERSION = 1
AUDIT_LIMIT = 5000

PROJECT_FIELDS = [
    "项目编号", "项目名称", "甲方/客户", "施工方/乙方", "合同金额(元)",
    "开工日期", "合同竣工日期", "进度款支付比例(%)", "质保金比例(%)", "状态", "备注",
]
CHANGE_FIELDS = [
    "签证编号", "项目编号", "发生日期", "变更类型", "项目/工序", "计量方式",
    "数量", "长度(m)", "宽度(m)", "高度(m)", "单位", "综合单价(元)",
    "金额(元)", "状态", "签认日期", "证据文件", "证据SHA256", "备注",
]
CLAIM_FIELDS = [
    "期次编号", "项目编号", "申报日期", "累计完成产值(元)", "累计已付款(元)",
    "本期预付款抵扣(元)", "本期其他扣款(元)", "累计支付比例(%)",
    "累计质保金比例(%)", "本期应付金额(元)", "状态", "付款日期", "备注",
]
PROJECT_STATUSES = ["施工中", "已竣工", "已暂停", "已终止"]
CHANGE_TYPES = ["增项", "减项", "工期签证"]
MEASUREMENT_TYPES = ["数量×单价", "面积×单价", "体积×单价", "固定金额"]
CHANGE_STATUSES = ["待签认", "已签认", "已驳回"]
CLAIM_STATUSES = ["草稿", "已申报", "已付款", "已作废"]
AUDIT_FIELDS = ["时间", "类别", "编号", "操作", "说明"]


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


def percent(value, field):
    number = _decimal(value, field)
    if number > 100:
        raise ValueError(f"{field}必须在 0 到 100 之间")
    return format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


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


def _digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_project(row):
    if not isinstance(row, dict):
        raise ValueError("项目记录格式错误")
    item = {field: _text(row.get(field, "")) for field in PROJECT_FIELDS}
    for field in ("项目编号", "项目名称", "甲方/客户", "施工方/乙方"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["合同金额(元)"] = money(item["合同金额(元)"], "合同金额")
    if Decimal(item["合同金额(元)"]) <= 0:
        raise ValueError("合同金额必须大于 0")
    item["开工日期"] = _date(item["开工日期"], "开工日期", required=True)
    item["合同竣工日期"] = _date(item["合同竣工日期"], "合同竣工日期", required=True)
    if item["合同竣工日期"] < item["开工日期"]:
        raise ValueError("合同竣工日期不能早于开工日期")
    item["进度款支付比例(%)"] = percent(item["进度款支付比例(%)"], "进度款支付比例")
    item["质保金比例(%)"] = percent(item["质保金比例(%)"], "质保金比例")
    if Decimal(item["质保金比例(%)"]) > Decimal(item["进度款支付比例(%)"]):
        raise ValueError("质保金比例不能高于进度款支付比例")
    if item["状态"] not in PROJECT_STATUSES:
        raise ValueError("项目状态不正确")
    return item


def calculate_change_amount(row):
    method = _text(row.get("计量方式"))
    quantity = _decimal(row.get("数量", "1"), "数量")
    length = _decimal(row.get("长度(m)", "0"), "长度")
    width = _decimal(row.get("宽度(m)", "0"), "宽度")
    height = _decimal(row.get("高度(m)", "0"), "高度")
    unit_price = _decimal(row.get("综合单价(元)", "0"), "综合单价")
    if method == "数量×单价":
        if quantity <= 0:
            raise ValueError("数量×单价的数量必须大于 0")
        raw = quantity * unit_price
    elif method == "面积×单价":
        if quantity <= 0 or length <= 0 or width <= 0:
            raise ValueError("面积计量的数量、长度和宽度必须大于 0")
        raw = quantity * length * width * unit_price
    elif method == "体积×单价":
        if quantity <= 0 or length <= 0 or width <= 0 or height <= 0:
            raise ValueError("体积计量的数量、长、宽、高必须大于 0")
        raw = quantity * length * width * height * unit_price
    elif method == "固定金额":
        raw = unit_price
    else:
        raise ValueError("计量方式不正确")
    change_type = _text(row.get("变更类型"))
    if change_type == "减项":
        raw = -raw
    elif change_type == "工期签证":
        if unit_price != 0:
            raise ValueError("工期签证不计价，综合单价必须为 0")
        raw = Decimal("0")
    elif change_type != "增项":
        raise ValueError("变更类型不正确")
    return money(raw, "签证金额", allow_negative=True)


def normalize_change(row):
    if not isinstance(row, dict):
        raise ValueError("签证记录格式错误")
    item = {field: _text(row.get(field, "")) for field in CHANGE_FIELDS}
    for field in ("签证编号", "项目编号", "发生日期", "项目/工序", "单位"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["发生日期"] = _date(item["发生日期"], "发生日期", required=True)
    item["签认日期"] = _date(item["签认日期"], "签认日期")
    if item["状态"] not in CHANGE_STATUSES:
        raise ValueError("签证状态不正确")
    if item["状态"] == "已签认" and not item["签认日期"]:
        raise ValueError("已签认签证必须填写签认日期")
    if item["状态"] != "已签认" and item["签认日期"]:
        raise ValueError("只有已签认签证可以填写签认日期")
    for field in ("数量", "长度(m)", "宽度(m)", "高度(m)"):
        item[field] = format(_decimal(item[field] or ("1" if field == "数量" else "0"), field), "f")
    item["综合单价(元)"] = money(item["综合单价(元)"], "综合单价")
    item["金额(元)"] = calculate_change_amount(item)
    evidence = item["证据文件"]
    supplied_hash = item["证据SHA256"].upper()
    if supplied_hash and not re.fullmatch(r"[0-9A-F]{64}", supplied_hash):
        raise ValueError("证据 SHA256 必须是 64 位十六进制字符串")
    if evidence and Path(evidence).is_file() and not supplied_hash:
        supplied_hash = _digest_file(evidence)
    item["证据SHA256"] = supplied_hash
    return item


def calculate_progress_payment(completed_value, paid_to_date, advance_recovery,
                               other_deductions, payment_rate, retention_rate):
    completed = _decimal(completed_value, "累计完成产值")
    paid = _decimal(paid_to_date, "累计已付款")
    advance = _decimal(advance_recovery, "预付款抵扣")
    deductions = _decimal(other_deductions, "其他扣款")
    rate = _decimal(payment_rate, "累计支付比例")
    retention = _decimal(retention_rate, "累计质保金比例")
    if rate > 100 or retention > rate:
        raise ValueError("支付比例或质保金比例设置不合理")
    earned = completed * rate / Decimal("100")
    retained = completed * retention / Decimal("100")
    raw = earned - retained - paid - advance - deductions
    payable = max(Decimal("0"), raw)
    return {
        "本期应付金额(元)": money(payable, "本期应付金额"),
        "累计支付上限(元)": money(earned - retained, "累计支付上限"),
        "超付金额(元)": money(max(Decimal("0"), -raw), "超付金额"),
        "本次质保金累计扣留(元)": money(retained, "质保金累计扣留"),
    }


def normalize_claim(row, project):
    if not isinstance(row, dict):
        raise ValueError("进度款记录格式错误")
    item = {field: _text(row.get(field, "")) for field in CLAIM_FIELDS}
    for field in ("期次编号", "项目编号", "申报日期"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if item["项目编号"] != project["项目编号"]:
        raise ValueError("进度款引用的项目编号不匹配")
    item["申报日期"] = _date(item["申报日期"], "申报日期", required=True)
    item["付款日期"] = _date(item["付款日期"], "付款日期")
    if item["付款日期"] and item["付款日期"] < item["申报日期"]:
        raise ValueError("付款日期不能早于申报日期")
    if item["状态"] not in CLAIM_STATUSES:
        raise ValueError("进度款状态不正确")
    if item["状态"] == "已付款" and not item["付款日期"]:
        raise ValueError("已付款记录必须填写付款日期")
    if item["状态"] != "已付款" and item["付款日期"]:
        raise ValueError("只有已付款记录可以填写付款日期")
    for field in ("累计完成产值(元)", "累计已付款(元)", "本期预付款抵扣(元)", "本期其他扣款(元)"):
        item[field] = money(item[field], field)
    rate = item["累计支付比例(%)"] or project["进度款支付比例(%)"]
    retention = item["累计质保金比例(%)"] or project["质保金比例(%)"]
    item["累计支付比例(%)"] = percent(rate, "累计支付比例")
    item["累计质保金比例(%)"] = percent(retention, "累计质保金比例")
    if Decimal(item["累计质保金比例(%)"]) > Decimal(item["累计支付比例(%)"]):
        raise ValueError("进度款质保金比例不能高于支付比例")
    result = calculate_progress_payment(
        item["累计完成产值(元)"], item["累计已付款(元)"],
        item["本期预付款抵扣(元)"], item["本期其他扣款(元)"],
        item["累计支付比例(%)"], item["累计质保金比例(%)"],
    )
    supplied = item["本期应付金额(元)"]
    if supplied and money(supplied, "本期应付金额") != result["本期应付金额(元)"]:
        raise ValueError("进度款计算结果与 CSV/备份中的本期应付金额不一致")
    item["本期应付金额(元)"] = result["本期应付金额(元)"]
    return item


def _unique(rows, field, label):
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"{label}重复")


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


class ConstructionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.projects = []
        self.changes = []
        self.claims = []
        self.audit = []
        self.load()

    def _payload(self):
        return {
            "format": FORMAT, "version": VERSION,
            "projects": self.projects, "changes": self.changes,
            "claims": self.claims, "audit": self.audit,
        }

    def _validate_all(self, projects, changes, claims, audit):
        if not all(isinstance(value, list) for value in (projects, changes, claims, audit)):
            raise ValueError("项目、签证、进度款和操作记录必须都是数组")
        normalized_projects = [normalize_project(row) for row in projects]
        normalized_changes = [normalize_change(row) for row in changes]
        _unique(normalized_projects, "项目编号", "项目编号")
        _unique(normalized_changes, "签证编号", "签证编号")
        project_map = {row["项目编号"]: row for row in normalized_projects}
        for row in normalized_changes:
            if row["项目编号"] not in project_map:
                raise ValueError("签证引用了不存在的项目：" + row["项目编号"])
        normalized_claims = []
        for row in claims:
            project = project_map.get(_text(row.get("项目编号")) if isinstance(row, dict) else "")
            if project is None:
                raise ValueError("进度款引用了不存在的项目")
            normalized_claims.append(normalize_claim(row, project))
        _unique(normalized_claims, "期次编号", "期次编号")
        if not isinstance(audit, list):
            raise ValueError("操作记录必须是数组")
        normalized_audit = []
        for event in audit[-AUDIT_LIMIT:]:
            if not isinstance(event, dict):
                raise ValueError("操作记录格式错误")
            normalized_audit.append({field: _text(event.get(field, "")) for field in AUDIT_FIELDS})
        return normalized_projects, normalized_changes, normalized_claims, normalized_audit

    def load(self):
        if not self.path.exists():
            self.projects, self.changes, self.claims, self.audit = [], [], [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != FORMAT:
                raise ValueError("项目数据文件格式不受支持")
            if type(payload.get("version")) is not int or payload["version"] != VERSION:
                raise ValueError("项目数据文件版本不受支持")
            validated = self._validate_all(
                payload.get("projects"), payload.get("changes"),
                payload.get("claims"), payload.get("audit"),
            )
            self.projects, self.changes, self.claims, self.audit = validated
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"项目数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        validated = self._validate_all(self.projects, self.changes, self.claims, self.audit)
        self.projects, self.changes, self.claims, self.audit = validated
        _atomic_write(self.path, json.dumps(self._payload(), ensure_ascii=False, indent=2))

    def _mutate(self, category, record_id, action, description, operation):
        snapshot = (copy.deepcopy(self.projects), copy.deepcopy(self.changes),
                    copy.deepcopy(self.claims), copy.deepcopy(self.audit))
        try:
            operation()
            self.audit.append({
                "时间": datetime.now().isoformat(timespec="seconds"),
                "类别": category, "编号": record_id, "操作": action, "说明": description,
            })
            self.audit = self.audit[-AUDIT_LIMIT:]
            self.save()
        except Exception:
            self.projects, self.changes, self.claims, self.audit = snapshot
            raise

    def _project(self, project_id):
        project = next((row for row in self.projects if row["项目编号"] == project_id), None)
        if project is None:
            raise ValueError("找不到项目：" + str(project_id))
        return project

    def add_project(self, row):
        item = normalize_project(row)
        if any(x["项目编号"] == item["项目编号"] for x in self.projects):
            raise ValueError("项目编号已存在")
        self._mutate("项目", item["项目编号"], "新增", item["项目名称"],
                     lambda: self.projects.append(item))
        return item["项目编号"]

    def update_project(self, old_id, row):
        item = normalize_project(row)
        if item["项目编号"] != old_id:
            raise ValueError("项目编号用于关联签证和进度款，创建后不能修改")
        index = next((i for i, x in enumerate(self.projects) if x["项目编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的项目")
        self._mutate("项目", old_id, "修改", item["项目名称"],
                     lambda: self.projects.__setitem__(index, item))

    def delete_project(self, project_id):
        if any(x["项目编号"] == project_id for x in self.changes + self.claims):
            raise ValueError("项目仍有关联签证或进度款，请先处理关联记录")
        index = next((i for i, x in enumerate(self.projects) if x["项目编号"] == project_id), None)
        if index is None:
            raise ValueError("找不到要删除的项目")
        self._mutate("项目", project_id, "删除", "删除项目",
                     lambda: self.projects.pop(index))

    def add_change(self, row):
        item = normalize_change(row)
        self._project(item["项目编号"])
        if any(x["签证编号"] == item["签证编号"] for x in self.changes):
            raise ValueError("签证编号已存在")
        self._mutate("签证", item["签证编号"], "新增", item["项目/工序"],
                     lambda: self.changes.append(item))
        return item["签证编号"]

    def update_change(self, old_id, row):
        item = normalize_change(row)
        if item["签证编号"] != old_id:
            raise ValueError("签证编号创建后不能修改")
        self._project(item["项目编号"])
        index = next((i for i, x in enumerate(self.changes) if x["签证编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的签证")
        self._mutate("签证", old_id, "修改", item["项目/工序"],
                     lambda: self.changes.__setitem__(index, item))

    def delete_change(self, change_id):
        index = next((i for i, x in enumerate(self.changes) if x["签证编号"] == change_id), None)
        if index is None:
            raise ValueError("找不到要删除的签证")
        self._mutate("签证", change_id, "删除", "删除签证",
                     lambda: self.changes.pop(index))

    def add_claim(self, row):
        project = self._project(_text(row.get("项目编号")) if isinstance(row, dict) else "")
        item = normalize_claim(row, project)
        if any(x["期次编号"] == item["期次编号"] for x in self.claims):
            raise ValueError("期次编号已存在")
        self._mutate("进度款", item["期次编号"], "新增", item["申报日期"],
                     lambda: self.claims.append(item))
        return item["期次编号"]

    def update_claim(self, old_id, row):
        project = self._project(_text(row.get("项目编号")) if isinstance(row, dict) else "")
        item = normalize_claim(row, project)
        if item["期次编号"] != old_id:
            raise ValueError("期次编号创建后不能修改")
        index = next((i for i, x in enumerate(self.claims) if x["期次编号"] == old_id), None)
        if index is None:
            raise ValueError("找不到要修改的进度款")
        self._mutate("进度款", old_id, "修改", item["申报日期"],
                     lambda: self.claims.__setitem__(index, item))

    def delete_claim(self, claim_id):
        index = next((i for i, x in enumerate(self.claims) if x["期次编号"] == claim_id), None)
        if index is None:
            raise ValueError("找不到要删除的进度款")
        self._mutate("进度款", claim_id, "删除", "删除进度款",
                     lambda: self.claims.pop(index))

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
                try:
                    rows.append(row)
                except Exception as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        return rows

    def import_csv(self, kind, path):
        if kind == "projects":
            incoming = [normalize_project(row) for row in self._read_csv(path, PROJECT_FIELDS)]
            _unique(incoming, "项目编号", "导入项目编号")
            existing = {x["项目编号"] for x in self.projects}
            if existing.intersection(x["项目编号"] for x in incoming):
                raise ValueError("导入包含已存在项目编号，整批未导入")
            self._mutate("项目", "CSV", "批量导入", str(len(incoming)),
                         lambda: self.projects.extend(incoming))
        elif kind == "changes":
            incoming = [normalize_change(row) for row in self._read_csv(path, CHANGE_FIELDS)]
            _unique(incoming, "签证编号", "导入签证编号")
            existing = {x["签证编号"] for x in self.changes}
            if existing.intersection(x["签证编号"] for x in incoming):
                raise ValueError("导入包含已存在签证编号，整批未导入")
            project_ids = {x["项目编号"] for x in self.projects}
            if any(x["项目编号"] not in project_ids for x in incoming):
                raise ValueError("导入签证引用了不存在的项目，整批未导入")
            self._mutate("签证", "CSV", "批量导入", str(len(incoming)),
                         lambda: self.changes.extend(incoming))
        elif kind == "claims":
            raw = self._read_csv(path, CLAIM_FIELDS)
            project_map = {x["项目编号"]: x for x in self.projects}
            incoming = []
            for row in raw:
                project = project_map.get(_text(row.get("项目编号")))
                if project is None:
                    raise ValueError("导入进度款引用了不存在的项目，整批未导入")
                incoming.append(normalize_claim(row, project))
            _unique(incoming, "期次编号", "导入期次编号")
            existing = {x["期次编号"] for x in self.claims}
            if existing.intersection(x["期次编号"] for x in incoming):
                raise ValueError("导入包含已存在期次编号，整批未导入")
            self._mutate("进度款", "CSV", "批量导入", str(len(incoming)),
                         lambda: self.claims.extend(incoming))
        else:
            raise ValueError("未知 CSV 数据类别")
        return len(incoming)

    def export_csv(self, kind, path):
        mapping = {"projects": (PROJECT_FIELDS, self.projects),
                   "changes": (CHANGE_FIELDS, self.changes),
                   "claims": (CLAIM_FIELDS, self.claims)}
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
            payload.get("projects"), payload.get("changes"),
            payload.get("claims"), payload.get("audit"),
        )
        snapshot = (self.projects, self.changes, self.claims, self.audit)
        self.projects, self.changes, self.claims, self.audit = validated
        try:
            self.save()
        except Exception:
            self.projects, self.changes, self.claims, self.audit = snapshot
            raise

    def project_summary(self, project_id):
        project = self._project(project_id)
        signed = [x for x in self.changes if x["项目编号"] == project_id and x["状态"] == "已签认"]
        pending = [x for x in self.changes if x["项目编号"] == project_id and x["状态"] == "待签认"]
        approved_amount = sum((Decimal(x["金额(元)"]) for x in signed), Decimal("0"))
        pending_amount = sum((Decimal(x["金额(元)"]) for x in pending), Decimal("0"))
        return {
            "合同金额(元)": project["合同金额(元)"],
            "已签认变更净额(元)": money(approved_amount, allow_negative=True),
            "调整后合同额(元)": money(Decimal(project["合同金额(元)"]) + approved_amount, allow_negative=True),
            "待签认变更净额(元)": money(pending_amount, allow_negative=True),
            "签证数量": len([x for x in self.changes if x["项目编号"] == project_id]),
            "进度款期数": len([x for x in self.claims if x["项目编号"] == project_id]),
        }

    def risk_findings(self, today=None):
        today = today or date.today()
        if isinstance(today, str):
            today = datetime.strptime(_date(today, "检查日期", required=True), "%Y-%m-%d").date()
        findings = []
        project_map = {x["项目编号"]: x for x in self.projects}
        for change in self.changes:
            project = project_map[change["项目编号"]]
            if change["状态"] == "已签认" and not change["证据文件"]:
                findings.append({"等级": "高", "规则编号": "SIGNED_CHANGE_NO_EVIDENCE",
                                 "编号": change["签证编号"], "说明": "已签认签证没有登记现场照片或签字附件路径"})
            if change["状态"] == "已签认" and change["证据文件"] and (
                not Path(change["证据文件"]).is_file() or
                (change["证据SHA256"] and _digest_file(change["证据文件"]) != change["证据SHA256"])
            ):
                findings.append({"等级": "高", "规则编号": "EVIDENCE_MISSING_OR_CHANGED",
                                 "编号": change["签证编号"], "说明": "签证证据文件缺失或 SHA256 与登记值不一致"})
            event_day = date.fromisoformat(change["发生日期"])
            if event_day < date.fromisoformat(project["开工日期"]) or event_day > date.fromisoformat(project["合同竣工日期"]):
                findings.append({"等级": "中", "规则编号": "CHANGE_OUTSIDE_TERM",
                                 "编号": change["签证编号"], "说明": "签证发生日期超出合同工期范围，请核对是否有工期变更"})
            age = (today - event_day).days
            if change["状态"] == "待签认" and age > 14:
                findings.append({"等级": "中", "规则编号": "CHANGE_PENDING_OVER_14_DAYS",
                                 "编号": change["签证编号"], "说明": f"签证已待确认 {age} 天，建议补齐签认"})
        for project in self.projects:
            summary = self.project_summary(project["项目编号"])
            adjusted = Decimal(summary["调整后合同额(元)"])
            if adjusted < 0:
                findings.append({"等级": "高", "规则编号": "ADJUSTED_CONTRACT_NEGATIVE",
                                 "编号": project["项目编号"], "说明": "已签认减项超过原合同金额"})
            for claim in [x for x in self.claims if x["项目编号"] == project["项目编号"]]:
                if Decimal(claim["累计完成产值(元)"]) > adjusted:
                    findings.append({"等级": "高", "规则编号": "COMPLETED_VALUE_EXCEEDS_ADJUSTED_CONTRACT",
                                     "编号": claim["期次编号"], "说明": "累计完成产值超过原合同金额加已签认变更净额"})
                result = calculate_progress_payment(
                    claim["累计完成产值(元)"], claim["累计已付款(元)"],
                    claim["本期预付款抵扣(元)"], claim["本期其他扣款(元)"],
                    claim["累计支付比例(%)"], claim["累计质保金比例(%)"],
                )
                if Decimal(result["超付金额(元)"]) > 0:
                    findings.append({"等级": "高", "规则编号": "PAYMENT_EXCEEDS_CEILING",
                                     "编号": claim["期次编号"], "说明": "累计已付款及本期扣款超过合同约定的累计支付上限"})
        return findings


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "construction_settlement.json"


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = ConstructionStore(root / "construction.json")
        project = {
            "项目编号": "P001", "项目名称": "办公室翻新", "甲方/客户": "甲方",
            "施工方/乙方": "施工方", "合同金额(元)": "100000",
            "开工日期": "2026-01-01", "合同竣工日期": "2026-12-31",
            "进度款支付比例(%)": "90", "质保金比例(%)": "5",
            "状态": "施工中", "备注": "",
        }
        store.add_project(project)
        evidence = root / "签证照片.txt"
        evidence.write_text("现场确认样本", encoding="utf-8")
        change = {
            "签证编号": "V001", "项目编号": "P001", "发生日期": "2026-06-01",
            "变更类型": "增项", "项目/工序": "墙面修补", "计量方式": "面积×单价",
            "数量": "1", "长度(m)": "10", "宽度(m)": "2", "高度(m)": "0",
            "单位": "平方米", "综合单价(元)": "50", "状态": "已签认",
            "签认日期": "2026-06-02", "证据文件": str(evidence), "备注": "",
        }
        store.add_change(change)
        assert store.changes[0]["金额(元)"] == "1000.00"
        claim = {
            "期次编号": "P001-01", "项目编号": "P001", "申报日期": "2026-06-30",
            "累计完成产值(元)": "50000", "累计已付款(元)": "0",
            "本期预付款抵扣(元)": "2000", "本期其他扣款(元)": "0",
            "状态": "已申报", "备注": "",
        }
        store.add_claim(claim)
        assert store.claims[0]["本期应付金额(元)"] == "40500.00"
        assert store.project_summary("P001")["调整后合同额(元)"] == "101000.00"
        assert not store.risk_findings("2026-07-01")
        csv_path = root / "projects.csv"
        store.export_csv("projects", csv_path)
        other = ConstructionStore(root / "other.json")
        assert other.import_csv("projects", csv_path) == 1
        backup = root / "backup.json"
        store.backup(backup)
        restored = ConstructionStore(root / "restored.json")
        restored.restore(backup)
        assert restored.projects == store.projects
        assert restored.changes == store.changes
        assert restored.claims == store.claims
    if os.getenv("MAINLAND_EXE_SELF_TEST") == "1" or __name__ == "__main__":
        print("SELF_TEST_OK", flush=True)
