"""Offline food-safety inspection and corrective-action closure assistant."""
import csv, hashlib, io, json, os, sys, tempfile, uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "门店食品安全巡检与整改闭环助手"
CHECKLIST_VERSION = "CN-FOOD-SAFETY-OPS-2026.11.1"
BACKUP_FORMAT = "mainland-food-safety-inspection"
BACKUP_VERSION = 1
RISK_WEIGHT = {"高": 10, "中": 5, "低": 2}
RESULTS = {"待检查", "合格", "不合格", "不适用"}
CHECKLIST = (
    {"id":"FS-001","category":"采购查验","title":"供货者资质与进货查验","risk":"高","guide":"抽查供货者资质、进货查验记录及异常批次处理记录。","action":"补齐供货者资料和进货查验记录，隔离来源不明批次。"},
    {"id":"FS-002","category":"采购查验","title":"票据、批次与去向可追溯","risk":"高","guide":"核对票据、商品批次、数量和销售/使用去向能否对应。","action":"补录批次与去向关联，保留票据并核对库存差异。"},
    {"id":"FS-003","category":"人员卫生","title":"从业人员健康管理与个人卫生","risk":"高","guide":"检查健康管理资料、工作服帽及异常健康情况处置流程。","action":"按门店制度补齐健康管理资料并安排人员卫生培训。"},
    {"id":"FS-004","category":"人员卫生","title":"洗手设施与手部清洁","risk":"高","guide":"检查洗手设施、清洁用品、干手用品及关键操作前后的洗手执行。","action":"恢复洗手设施，补齐用品并重新培训关键洗手时点。"},
    {"id":"FS-005","category":"加工操作","title":"生熟分开与交叉污染控制","risk":"高","guide":"检查生熟食品、洁污区域、容器和操作流程是否分开。","action":"重新划分区域和容器，清洁消毒受污染区域并复查。"},
    {"id":"FS-006","category":"温度控制","title":"冷藏设备温度记录与超限处置","risk":"高","guide":"记录设备实测温度、时间及超限后的食品评估和处置。","action":"按食品类别设定门店阈值，校准设备并记录超限处置。"},
    {"id":"FS-007","category":"温度控制","title":"冷冻设备温度记录与超限处置","risk":"高","guide":"核对冷冻设备温度记录、设备状态和异常批次处置。","action":"按产品要求设定阈值，检查设备并隔离异常批次待评估。"},
    {"id":"FS-008","category":"效期管理","title":"日期标签、开封标识与先进先出","risk":"高","guide":"抽查生产/到期日期、开封时间、分装标签及先进先出执行。","action":"立即隔离过期或标识不清食品，补齐标签和轮转检查。"},
    {"id":"FS-009","category":"储存管理","title":"食品离地离墙、防潮与分类存放","risk":"中","guide":"检查食品是否按类别存放，避免直接落地、受潮和污染。","action":"调整货架和分区，清理受潮或污染食品并复查。"},
    {"id":"FS-010","category":"清洁消毒","title":"环境清洁、消毒程序与记录","risk":"高","guide":"抽查清洁频次、消毒方法、用品配比记录及执行情况。","action":"按产品说明和门店程序重新清洁消毒并补记真实执行记录。"},
    {"id":"FS-011","category":"清洁消毒","title":"餐具、器具与抹布分区管理","risk":"中","guide":"检查餐具、加工器具、抹布的清洗消毒和分区存放。","action":"重新分区标识，清洗消毒并替换破损或无法清洁用品。"},
    {"id":"FS-012","category":"化学品管理","title":"清洁剂与食品分区存放","risk":"高","guide":"检查清洁剂、消毒剂等化学品是否独立标识、密闭存放。","action":"立即移离食品区域，核对容器标签并排查污染风险。"},
    {"id":"FS-013","category":"虫害与废弃物","title":"虫害防治与垃圾密闭清运","risk":"中","guide":"检查防虫设施、虫害迹象、垃圾容器和清运频次。","action":"清洁受影响区域，处理虫害源并记录复查结果。"},
    {"id":"FS-014","category":"用水卫生","title":"加工用水与制冰用水卫生","risk":"高","guide":"检查加工、清洗和制冰用水来源、设施清洁及维护记录。","action":"暂停使用存在疑问的水源/制冰设备，查明原因后复核。"},
    {"id":"FS-015","category":"加工操作","title":"熟制食品充分加热与温度核验","risk":"高","guide":"对适用菜品抽查加热过程、测温工具和记录。","action":"按食品类别建立门店操作参数，培训并复测关键菜品。"},
    {"id":"FS-016","category":"过敏原管理","title":"过敏原提示与专用器具","risk":"中","guide":"检查菜单提示、顾客询问流程及必要的器具/区域隔离。","action":"补充清晰提示，建立询问确认流程并分开器具。"},
    {"id":"FS-017","category":"应急管理","title":"异常食品隔离、召回与处置记录","risk":"高","guide":"检查异常食品隔离标识、停售流程、去向查询和处置记录。","action":"建立异常批次隔离与追溯联系人清单，组织一次桌面演练。"},
)
RULES = {item["id"]: item for item in CHECKLIST}
ENTRY_FIELDS = ["规则编号","检查结果","证据记录","整改责任人","整改期限","整改状态","整改说明","复查日期"]
CSV_FIELDS = ["巡检编号","门店名称","巡检日期","检查人","清单版本","规则编号","检查项目","风险等级","检查结果","证据记录","整改责任人","整改期限","整改状态","整改说明","复查日期"]
MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_INSPECTIONS = 10000


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def inspection_snapshot_hash(inspection):
    body = {key: value for key, value in inspection.items() if key != "记录SHA256"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def csv_safe_cell(value):
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def atomic_write_text(path, content):
    """Write beside the destination, flush, then atomically replace the old file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def parse_date(value, field, *, required=False):
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


def normalize_entry(row):
    if not isinstance(row, dict):
        raise ValueError("检查项必须是对象")
    rule_id = str(row.get("规则编号", "")).strip()
    rule = RULES.get(rule_id)
    if rule is None:
        raise ValueError(f"检查项引用了未知规则：{rule_id}")
    result = str(row.get("检查结果", "待检查") or "待检查").strip()
    if result not in RESULTS:
        raise ValueError("检查结果必须是待检查、合格、不合格或不适用")
    evidence = str(row.get("证据记录", "") or "").strip()
    owner = str(row.get("整改责任人", "") or "").strip()
    due = parse_date(row.get("整改期限", ""), "整改期限")
    status = str(row.get("整改状态", "") or "").strip()
    resolution = str(row.get("整改说明", "") or "").strip()
    reviewed = parse_date(row.get("复查日期", ""), "复查日期")
    if result == "待检查":
        status, owner, due, resolution, reviewed = "未检查", "", "", "", ""
    elif result in {"合格", "不适用"}:
        status, owner, due, resolution, reviewed = "无需整改", "", "", "", ""
    else:
        status = status or "待整改"
        if not owner or not due:
            raise ValueError(f"{rule_id} 判定不合格时必须填写整改责任人和整改期限")
        if status not in {"待整改", "已完成"}:
            raise ValueError("不合格检查项的整改状态必须是待整改或已完成")
        if status == "已完成" and (not resolution or not reviewed):
            raise ValueError("已完成整改必须填写整改说明和复查日期")
        if status == "待整改":
            resolution, reviewed = "", ""
    return {
        "规则编号": rule_id, "检查项目": rule["title"], "风险等级": rule["risk"],
        "检查结果": result, "证据记录": evidence, "整改责任人": owner,
        "整改期限": due, "整改状态": status, "整改说明": resolution, "复查日期": reviewed,
    }


def normalize_inspection(row, *, verify_snapshot=False):
    if not isinstance(row, dict):
        raise ValueError("巡检记录必须是对象")
    inspection_id = str(row.get("巡检编号", "") or "").strip()
    if not inspection_id or len(inspection_id) > 64 or any(ord(c) < 32 for c in inspection_id):
        raise ValueError("巡检编号无效")
    store = str(row.get("门店名称", "") or "").strip()
    inspector = str(row.get("检查人", "") or "").strip()
    if not store or not inspector:
        raise ValueError("门店名称和检查人不能为空")
    inspected_on = parse_date(row.get("巡检日期", ""), "巡检日期", required=True)
    version = str(row.get("清单版本", "") or "").strip()
    if version != CHECKLIST_VERSION:
        raise ValueError(f"不支持的检查清单版本：{version}")
    raw_entries = row.get("检查项")
    if not isinstance(raw_entries, list):
        raise ValueError("巡检记录缺少检查项列表")
    entries = [normalize_entry(item) for item in raw_entries]
    ids = [item["规则编号"] for item in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("同一巡检中存在重复检查项")
    if set(ids) != set(RULES):
        raise ValueError("每次巡检必须包含当前版本的全部检查项，不得漏项")
    normalized = {
        "巡检编号": inspection_id, "门店名称": store, "巡检日期": inspected_on,
        "检查人": inspector, "清单版本": version,
        "检查项": sorted(entries, key=lambda item: item["规则编号"]),
        "创建时间": str(row.get("创建时间", "") or datetime.now().isoformat(timespec="seconds")),
    }
    digest = inspection_snapshot_hash(normalized)
    if verify_snapshot and row.get("记录SHA256") != digest:
        raise ValueError("巡检记录快照 SHA256 校验失败：" + inspection_id)
    normalized["记录SHA256"] = digest
    return normalized


def verify_event_chain(events):
    previous = "0" * 64
    required = {"序号","时间","动作","巡检编号","规则编号","摘要","记录SHA256","前序哈希","哈希"}
    for expected_seq, event in enumerate(events, start=1):
        if not isinstance(event, dict) or set(event) != required:
            raise ValueError("审计链事件格式无效")
        if event["序号"] != expected_seq or event["前序哈希"] != previous:
            raise ValueError("审计链序号或前序哈希不连续")
        try:
            datetime.fromisoformat(event["时间"])
        except (TypeError, ValueError):
            raise ValueError("审计链时间格式无效") from None
        body = {key: event[key] for key in required if key != "哈希"}
        digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
        if digest != event["哈希"]:
            raise ValueError(f"审计链校验失败：第 {expected_seq} 条事件")
        previous = digest
    return True


def append_event(events, action, inspection_id, snapshot_sha256, rule_id="", summary=""):
    previous = events[-1]["哈希"] if events else "0" * 64
    body = {
        "序号": len(events) + 1, "时间": datetime.now().isoformat(timespec="seconds"),
        "动作": str(action), "巡检编号": str(inspection_id), "规则编号": str(rule_id),
        "摘要": str(summary), "记录SHA256": str(snapshot_sha256), "前序哈希": previous,
    }
    event = dict(body)
    event["哈希"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return events + [event]


class InspectionStore:
    """Atomic local store with versioned checklist and tamper-evident audit chain."""
    def __init__(self, path):
        self.path = Path(path)
        self.inspections, self.events = [], []
        self.load()

    @staticmethod
    def _unique_inspections(rows):
        ids = [row["巡检编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("巡检编号重复")

    @staticmethod
    def _payload_body(payload):
        return {key: value for key, value in payload.items() if key != "SHA256"}

    @classmethod
    def decode_payload(cls, payload):
        if not isinstance(payload, dict) or payload.get("格式") != BACKUP_FORMAT:
            raise ValueError("备份格式不受支持")
        if payload.get("版本") != BACKUP_VERSION:
            raise ValueError("备份版本不受支持")
        body = cls._payload_body(payload)
        digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
        if payload.get("SHA256") != digest:
            raise ValueError("备份 SHA256 校验失败，原数据未修改")
        raw_inspections, raw_events = body.get("巡检记录"), body.get("审计链")
        if not isinstance(raw_inspections, list) or not isinstance(raw_events, list):
            raise ValueError("备份缺少巡检记录或审计链")
        if len(raw_inspections) > MAX_INSPECTIONS:
            raise ValueError("备份巡检记录超过 10000 条安全上限")
        inspections = [normalize_inspection(row, verify_snapshot=True) for row in raw_inspections]
        cls._unique_inspections(inspections)
        events = list(raw_events)
        verify_event_chain(events)
        cls.verify_snapshot_links(inspections, events)
        return inspections, events

    def load(self):
        if not self.path.exists():
            self.inspections, self.events = [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.inspections, self.events = self.decode_payload(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"本地数据无法读取，原文件未修改：{exc}") from exc

    @staticmethod
    def verify_snapshot_links(inspections, events):
        ids = {row["巡检编号"] for row in inspections}
        latest = {}
        for event in events:
            if event["巡检编号"] not in ids:
                raise ValueError("审计链引用了不存在的巡检记录")
            latest[event["巡检编号"]] = event["记录SHA256"]
        for row in inspections:
            if latest.get(row["巡检编号"]) != row["记录SHA256"]:
                raise ValueError("巡检记录与审计链快照不匹配：" + row["巡检编号"])
        return True

    def _make_payload(self, inspections, events):
        body = {
            "格式": BACKUP_FORMAT, "版本": BACKUP_VERSION,
            "更新时间": datetime.now().isoformat(timespec="seconds"),
            "巡检记录": inspections, "审计链": events,
        }
        return {**body, "SHA256": hashlib.sha256(canonical_bytes(body)).hexdigest()}

    def _commit(self, inspections, events):
        normalized = [normalize_inspection(row) for row in inspections]
        self._unique_inspections(normalized)
        if len(normalized) > MAX_INSPECTIONS:
            raise ValueError("巡检记录超过 10000 条安全上限")
        verify_event_chain(events)
        self.verify_snapshot_links(normalized, events)
        payload = self._make_payload(normalized, events)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(serialized.encode("utf-8")) > MAX_BACKUP_BYTES:
            raise ValueError("本地巡检数据超过 100 MiB 安全上限")
        atomic_write_text(self.path, serialized)
        self.inspections, self.events = normalized, list(events)

    def get_inspection(self, inspection_id):
        return next((row for row in self.inspections if row["巡检编号"] == inspection_id), None)

    def create_inspection(self, store, inspector, *, inspected_on=None):
        inspection = normalize_inspection({
            "巡检编号": uuid.uuid4().hex.upper(), "门店名称": store,
            "巡检日期": inspected_on or date.today().isoformat(), "检查人": inspector,
            "清单版本": CHECKLIST_VERSION,
            "检查项": [{"规则编号": item["id"], "检查结果": "待检查"} for item in CHECKLIST],
        })
        events = append_event(self.events, "创建巡检", inspection["巡检编号"], inspection["记录SHA256"], summary=f"{store} / {inspector}")
        self._commit(self.inspections + [inspection], events)
        return inspection["巡检编号"]

    def update_check(self, inspection_id, rule_id, result, evidence="", owner="", due_date=""):
        current = self.get_inspection(inspection_id)
        if current is None:
            raise ValueError("找不到巡检记录")
        updated, entries, found = dict(current), [], False
        for entry in current["检查项"]:
            if entry["规则编号"] == rule_id:
                found = True
                candidate = dict(entry)
                candidate.update({
                    "检查结果": result, "证据记录": evidence, "整改责任人": owner,
                    "整改期限": due_date, "整改状态": "待整改" if result == "不合格" else "",
                })
                entries.append(normalize_entry(candidate))
            else:
                entries.append(entry)
        if not found:
            raise ValueError("找不到所选检查项")
        updated["检查项"] = entries
        updated = normalize_inspection(updated)
        events = append_event(self.events, "记录检查结果", inspection_id, updated["记录SHA256"], rule_id, result)
        self._commit([updated if row["巡检编号"] == inspection_id else row for row in self.inspections], events)

    def close_finding(self, inspection_id, rule_id, resolution, *, reviewed_on=None):
        current = self.get_inspection(inspection_id)
        if current is None:
            raise ValueError("找不到巡检记录")
        resolution = str(resolution or "").strip()
        if not resolution:
            raise ValueError("整改说明不能为空")
        reviewed_on = parse_date(reviewed_on or date.today().isoformat(), "复查日期", required=True)
        updated, entries, found = dict(current), [], False
        for entry in current["检查项"]:
            if entry["规则编号"] == rule_id:
                found = True
                if entry["检查结果"] != "不合格" or entry["整改状态"] != "待整改":
                    raise ValueError("该检查项当前没有待闭环的整改任务")
                candidate = dict(entry)
                candidate.update({"整改状态": "已完成", "整改说明": resolution, "复查日期": reviewed_on})
                entries.append(normalize_entry(candidate))
            else:
                entries.append(entry)
        if not found:
            raise ValueError("找不到所选检查项")
        updated["检查项"] = entries
        updated = normalize_inspection(updated)
        events = append_event(self.events, "整改复查完成", inspection_id, updated["记录SHA256"], rule_id, resolution[:120])
        self._commit([updated if row["巡检编号"] == inspection_id else row for row in self.inspections], events)

    @staticmethod
    def score(inspection):
        checked = [row for row in inspection["检查项"] if row["检查结果"] in {"合格", "不合格"}]
        if not checked:
            return None
        total = sum(RISK_WEIGHT[row["风险等级"]] for row in checked)
        failed = sum(RISK_WEIGHT[row["风险等级"]] for row in checked if row["检查结果"] == "不合格")
        return round(100 * (1 - failed / total), 1) if total else None

    def open_findings(self):
        return [
            {**entry, "巡检编号": inspection["巡检编号"], "门店名称": inspection["门店名称"],
             "巡检日期": inspection["巡检日期"], "检查人": inspection["检查人"]}
            for inspection in self.inspections for entry in inspection["检查项"]
            if entry["检查结果"] == "不合格" and entry["整改状态"] == "待整改"
        ]

    def overdue_findings(self, *, today=None):
        today = today or date.today()
        return [row for row in self.open_findings() if date.fromisoformat(row["整改期限"]) < today]

    def repeated_findings_by_store(self, *, today=None, window_days=90):
        """Count recurrence within each store; never combine unrelated stores."""
        today = today or date.today()
        cutoff = today - timedelta(days=window_days)
        occurrences = {}
        for inspection in self.inspections:
            inspected_on = date.fromisoformat(inspection["巡检日期"])
            if inspected_on < cutoff or inspected_on > today:
                continue
            store = inspection["门店名称"]
            for entry in inspection["检查项"]:
                if entry["检查结果"] == "不合格":
                    key = (store, entry["规则编号"])
                    occurrences.setdefault(key, set()).add(inspection["巡检编号"])
        repeated = {}
        for (store, rule_id), inspection_ids in occurrences.items():
            if len(inspection_ids) >= 2:
                repeated.setdefault(store, []).append(rule_id)
        return {store: sorted(rule_ids) for store, rule_ids in sorted(repeated.items())}

    def repeated_findings(self, *, today=None, window_days=90):
        return sorted({
            rule_id
            for rule_ids in self.repeated_findings_by_store(today=today, window_days=window_days).values()
            for rule_id in rule_ids
        })

    def store_risk_report(self, *, today=None, window_days=90):
        """Return explainable per-store workload and risk indicators."""
        today = today or date.today()
        repeated = self.repeated_findings_by_store(today=today, window_days=window_days)
        report = []
        for store in sorted({row["门店名称"] for row in self.inspections}):
            inspections = [row for row in self.inspections if row["门店名称"] == store]
            open_rows = [
                {**entry, "巡检编号": inspection["巡检编号"], "门店名称": store}
                for inspection in inspections for entry in inspection["检查项"]
                if entry["检查结果"] == "不合格" and entry["整改状态"] == "待整改"
            ]
            overdue = [row for row in open_rows if date.fromisoformat(row["整改期限"]) < today]
            high_risk = [row for row in open_rows if row["风险等级"] == "高"]
            repeated_rules = repeated.get(store, [])
            scores = [self.score(row) for row in inspections]
            scores = [value for value in scores if value is not None]
            if overdue or high_risk or repeated_rules:
                attention, priority = "重点关注", 3
            elif open_rows:
                attention, priority = "跟进整改", 2
            else:
                attention, priority = "暂无待整改", 1
            report.append({
                "门店名称": store,
                "巡检次数": len(inspections),
                "最近巡检日期": max(row["巡检日期"] for row in inspections),
                "待整改": len(open_rows),
                "逾期整改": len(overdue),
                "高风险待整改": len(high_risk),
                "重复规则": "、".join(repeated_rules),
                "平均内部管理分": round(sum(scores) / len(scores), 1) if scores else None,
                "关注等级": attention,
                "_priority": priority,
            })
        report.sort(key=lambda row: (
            -row["_priority"], -row["逾期整改"], -row["高风险待整改"],
            -len([item for item in row["重复规则"].split("、") if item]), row["门店名称"]
        ))
        return [{key: value for key, value in row.items() if not key.startswith("_")} for row in report]

    def dashboard(self, *, today=None):
        open_rows = self.open_findings()
        scores = [self.score(row) for row in self.inspections]
        scores = [value for value in scores if value is not None]
        repeated = self.repeated_findings(today=today)
        return {
            "巡检次数": len(self.inspections), "待整改": len(open_rows),
            "逾期整改": len(self.overdue_findings(today=today)),
            "高风险待整改": sum(1 for row in open_rows if row["风险等级"] == "高"),
            "重复问题": len(repeated), "重复规则": repeated,
            "平均内部管理分": round(sum(scores) / len(scores), 1) if scores else None,
        }

    def export_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for inspection in self.inspections:
            for entry in inspection["检查项"]:
                row = {
                    "巡检编号": inspection["巡检编号"], "门店名称": inspection["门店名称"],
                    "巡检日期": inspection["巡检日期"], "检查人": inspection["检查人"],
                    "清单版本": inspection["清单版本"], **entry,
                }
                writer.writerow({key: csv_safe_cell(row.get(key, "")) for key in CSV_FIELDS})
        atomic_write_text(path, "\ufeff" + buffer.getvalue())

    def export_store_risk_csv(self, path, *, today=None):
        fields = [
            "门店名称", "巡检次数", "最近巡检日期", "待整改", "逾期整改",
            "高风险待整改", "90天重复规则", "平均内部管理分", "关注等级",
        ]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in self.store_risk_report(today=today):
            values = {
                **row,
                "90天重复规则": row["重复规则"],
                "平均内部管理分": "" if row["平均内部管理分"] is None else f"{row['平均内部管理分']:.1f}",
            }
            writer.writerow({key: csv_safe_cell(values.get(key, "")) for key in fields})
        atomic_write_text(path, "\ufeff" + buffer.getvalue())

    def import_csv(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_CSV_BYTES:
            raise ValueError("巡检 CSV 超过 25 MiB 安全上限")
        groups = {}
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = set(CSV_FIELDS) - set(reader.fieldnames or [])
            if missing:
                raise ValueError("CSV 缺少字段：" + "、".join(sorted(missing)))
            for line_no, row in enumerate(reader, start=2):
                if not row or not row.get("巡检编号"):
                    raise ValueError(f"CSV 第 {line_no} 行缺少巡检编号")
                inspection_id = row["巡检编号"].strip()
                meta = {
                    "巡检编号": inspection_id, "门店名称": row.get("门店名称", ""),
                    "巡检日期": row.get("巡检日期", ""), "检查人": row.get("检查人", ""),
                    "清单版本": row.get("清单版本", ""),
                }
                if inspection_id not in groups:
                    groups[inspection_id] = {**meta, "检查项": []}
                elif any(groups[inspection_id][key] != meta[key] for key in meta):
                    raise ValueError(f"CSV 第 {line_no} 行巡检基本信息不一致")
                rule_id = str(row.get("规则编号", "")).strip()
                rule = RULES.get(rule_id)
                if rule is None or row.get("检查项目") != rule["title"] or row.get("风险等级") != rule["risk"]:
                    raise ValueError(f"CSV 第 {line_no} 行规则名称或风险等级与清单版本不匹配")
                groups[inspection_id]["检查项"].append({key: row.get(key, "") for key in ENTRY_FIELDS})
        if len(groups) > MAX_INSPECTIONS:
            raise ValueError("单次导入巡检记录超过 10000 条安全上限")
        incoming = [normalize_inspection(row) for row in groups.values()]
        ids = [row["巡检编号"] for row in incoming]
        if len(ids) != len(set(ids)):
            raise ValueError("CSV 中巡检编号重复")
        existing = {row["巡检编号"] for row in self.inspections}
        if existing.intersection(ids):
            raise ValueError("CSV 中包含已存在的巡检编号，未导入任何数据")
        if len(self.inspections) + len(incoming) > MAX_INSPECTIONS:
            raise ValueError("导入后巡检记录超过 10000 条安全上限")
        events = list(self.events)
        for inspection in incoming:
            events = append_event(events, "CSV 导入巡检", inspection["巡检编号"], inspection["记录SHA256"], summary=inspection["门店名称"])
        self._commit(self.inspections + incoming, events)
        return len(incoming)

    def backup(self, path):
        payload = self._make_payload(self.inspections, self.events)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(serialized.encode("utf-8")) > MAX_BACKUP_BYTES:
            raise ValueError("巡检备份超过 100 MiB 安全上限")
        atomic_write_text(path, serialized)

    def restore(self, path):
        source = Path(path)
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("巡检备份超过 100 MiB 安全上限")
        payload = json.loads(source.read_text(encoding="utf-8"))
        inspections, events = self.decode_payload(payload)
        self._commit(inspections, events)


def default_data_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "MainlandBusinessTools" / "food_safety_inspections.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.store = InspectionStore(default_data_path())
        self.selected_id = None
        self.title(PRODUCT)
        self.geometry("1120x760")
        self.minsize(980, 650)
        self._build()
        self.refresh()

    def _build(self):
        ttk.Label(self, text=PRODUCT, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        ttk.Label(self, text=f"版本化检查清单 {CHECKLIST_VERSION}｜本地审计链｜不依赖云端服务",
                  foreground="#555").pack(anchor="w", padx=18, pady=(0, 10))
        actions = ttk.Frame(self, padding=(12, 4))
        actions.pack(fill="x")
        for label, command in [
            ("新建巡检", self.new_inspection), ("录入检查结果", self.edit_check),
            ("整改闭环", self.close_finding), ("风险复盘", self.show_dashboard),
            ("多门店风险分析", self.show_store_risk_report),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("导出门店风险 CSV", self.export_store_risk_csv),
            ("备份", self.backup), ("恢复", self.restore),
        ]:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=3, pady=3)
        ttk.Label(self, text="巡检记录").pack(anchor="w", padx=18, pady=(8, 2))
        self.inspection_tree = ttk.Treeview(self, columns=("date","store","inspector","score","open"), show="headings", height=9)
        for col, title, width in [
            ("date","巡检日期",110),("store","门店",240),("inspector","检查人",120),("score","内部管理分",110),("open","待整改",90)
        ]:
            self.inspection_tree.heading(col, text=title)
            self.inspection_tree.column(col, width=width, anchor="center")
        self.inspection_tree.pack(fill="x", padx=18, pady=(0, 10))
        self.inspection_tree.bind("<<TreeviewSelect>>", self.on_inspection_select)
        ttk.Label(self, text="检查清单与整改状态").pack(anchor="w", padx=18, pady=(4, 2))
        self.detail_tree = ttk.Treeview(self, columns=("category","title","risk","result","status","due"), show="headings", height=15)
        for col, title, width in [
            ("category","类别",100),("title","检查项目",330),("risk","风险",70),
            ("result","结果",90),("status","整改状态",100),("due","整改期限",110)
        ]:
            self.detail_tree.heading(col, text=title)
            self.detail_tree.column(col, width=width, anchor="center")
        self.detail_tree.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.status = tk.StringVar(value="选中巡检后，可录入检查结果或关闭整改任务。")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def refresh(self):
        for item in self.inspection_tree.get_children():
            self.inspection_tree.delete(item)
        for inspection in sorted(self.store.inspections, key=lambda row: row["巡检日期"], reverse=True):
            score = self.store.score(inspection)
            open_count = sum(1 for row in inspection["检查项"] if row["整改状态"] == "待整改")
            self.inspection_tree.insert("", "end", iid=inspection["巡检编号"], values=(
                inspection["巡检日期"], inspection["门店名称"], inspection["检查人"],
                "未评分" if score is None else f"{score:.1f}", open_count,
            ))
        if self.selected_id and self.inspection_tree.exists(self.selected_id):
            self.inspection_tree.selection_set(self.selected_id)
        elif self.store.inspections:
            first = sorted(self.store.inspections, key=lambda row: row["巡检日期"], reverse=True)[0]
            self.selected_id = first["巡检编号"]
            self.inspection_tree.selection_set(self.selected_id)
        self.refresh_details()

    def on_inspection_select(self, _event=None):
        selection = self.inspection_tree.selection()
        self.selected_id = selection[0] if selection else None
        self.refresh_details()

    def refresh_details(self):
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)
        inspection = self.store.get_inspection(self.selected_id) if self.selected_id else None
        if not inspection:
            return
        for entry in inspection["检查项"]:
            rule = RULES[entry["规则编号"]]
            self.detail_tree.insert("", "end", iid=entry["规则编号"], values=(
                rule["category"], entry["检查项目"], entry["风险等级"], entry["检查结果"],
                entry["整改状态"], entry["整改期限"],
            ))
        open_count = sum(1 for row in inspection["检查项"] if row["整改状态"] == "待整改")
        self.status.set(f"{inspection['门店名称']}｜{inspection['巡检日期']}｜待整改 {open_count} 项｜审计事件 {len(self.store.events)} 条")

    def selected_entry(self):
        if not self.selected_id:
            raise ValueError("请先选择一条巡检记录")
        selection = self.detail_tree.selection()
        if not selection:
            raise ValueError("请先选择一条检查项")
        inspection = self.store.get_inspection(self.selected_id)
        return next(row for row in inspection["检查项"] if row["规则编号"] == selection[0])

    def new_inspection(self):
        store = simpledialog.askstring("新建巡检", "门店名称：", parent=self)
        if not store:
            return
        inspector = simpledialog.askstring("新建巡检", "检查人：", parent=self)
        if not inspector:
            return
        try:
            self.selected_id = self.store.create_inspection(store, inspector)
            self.refresh()
        except Exception as exc:
            messagebox.showerror("无法新建巡检", str(exc), parent=self)

    def edit_check(self):
        try:
            entry = self.selected_entry()
        except ValueError as exc:
            messagebox.showinfo("提示", str(exc), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"录入检查结果 - {entry['规则编号']}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("560x430")
        rule = RULES[entry["规则编号"]]
        ttk.Label(dialog, text=f"{rule['category']}｜{rule['title']}", wraplength=520).pack(anchor="w", padx=14, pady=(14, 8))
        result_var = tk.StringVar(value=entry["检查结果"])
        ttk.Label(dialog, text="检查结果").pack(anchor="w", padx=14)
        ttk.Combobox(dialog, textvariable=result_var, values=sorted(RESULTS), state="readonly").pack(fill="x", padx=14, pady=(2, 8))
        ttk.Label(dialog, text="证据记录 / 实测值").pack(anchor="w", padx=14)
        evidence = tk.Text(dialog, height=5)
        evidence.pack(fill="x", padx=14, pady=(2, 8))
        evidence.insert("1.0", entry["证据记录"])
        ttk.Label(dialog, text="整改责任人（不合格时必填）").pack(anchor="w", padx=14)
        owner = ttk.Entry(dialog)
        owner.pack(fill="x", padx=14, pady=(2, 8))
        owner.insert(0, entry["整改责任人"])
        ttk.Label(dialog, text="整改期限 YYYY-MM-DD（不合格时必填）").pack(anchor="w", padx=14)
        due = ttk.Entry(dialog)
        due.pack(fill="x", padx=14, pady=(2, 8))
        due.insert(0, entry["整改期限"])
        def save():
            try:
                self.store.update_check(self.selected_id, entry["规则编号"], result_var.get(),
                                        evidence.get("1.0", "end").strip(), owner.get(), due.get())
                dialog.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("检查结果无效", str(exc), parent=dialog)
        ttk.Button(dialog, text="保存检查结果", command=save).pack(pady=12)

    def close_finding(self):
        try:
            entry = self.selected_entry()
            if entry["检查结果"] != "不合格" or entry["整改状态"] != "待整改":
                raise ValueError("请选择一条待整改的不合格检查项")
            note = simpledialog.askstring("整改闭环", "填写整改措施和复查结果：", parent=self)
            if not note:
                return
            self.store.close_finding(self.selected_id, entry["规则编号"], note)
            self.refresh()
        except ValueError as exc:
            messagebox.showinfo("提示", str(exc), parent=self)
        except Exception as exc:
            messagebox.showerror("整改失败", str(exc), parent=self)

    def show_dashboard(self):
        data = self.store.dashboard()
        score = "暂无" if data["平均内部管理分"] is None else f"{data['平均内部管理分']:.1f}"
        repeated = "、".join(data["重复规则"]) or "无"
        messagebox.showinfo("风险复盘",
            f"巡检次数：{data['巡检次数']}\n待整改：{data['待整改']}\n逾期整改：{data['逾期整改']}\n"
            f"高风险待整改：{data['高风险待整改']}\n90 天重复问题：{data['重复问题']}（{repeated}）\n"
            f"平均内部管理分：{score}\n\n该分数仅供门店内部趋势比较，不是监管评分或合规结论。",
            parent=self)

    def show_store_risk_report(self):
        rows = self.store.store_risk_report()
        if not rows:
            messagebox.showinfo("多门店风险分析", "暂无巡检记录。", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("多门店风险分析")
        dialog.geometry("940x460")
        columns = ("store", "level", "count", "latest", "open", "overdue", "high", "repeat", "score")
        tree = ttk.Treeview(dialog, columns=columns, show="headings")
        headings = [
            ("store", "门店", 150), ("level", "关注等级", 105), ("count", "巡检次数", 75),
            ("latest", "最近巡检", 105), ("open", "待整改", 70), ("overdue", "逾期", 65),
            ("high", "高风险", 70), ("repeat", "90天重复规则", 150), ("score", "平均内部管理分", 115),
        ]
        for key, title, width in headings:
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
        for row in rows:
            score = "暂无" if row["平均内部管理分"] is None else f"{row['平均内部管理分']:.1f}"
            tree.insert("", "end", values=(
                row["门店名称"], row["关注等级"], row["巡检次数"], row["最近巡检日期"],
                row["待整改"], row["逾期整改"], row["高风险待整改"],
                row["重复规则"] or "无", score,
            ))

    def export_store_risk_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_store_risk_csv(path)
            messagebox.showinfo("导出完成", f"已导出门店风险报表：{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 次巡检。", parent=self)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            self.store.export_csv(path)
            messagebox.showinfo("导出完成", f"已导出到：{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        try:
            self.store.backup(path)
            messagebox.showinfo("备份完成", f"已备份到：{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("备份失败", str(exc), parent=self)

    def restore(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("JSON 备份", "*.json")])
        if not path or not messagebox.askyesno("确认恢复", "恢复会替换当前巡检记录，请先确认已有备份。继续吗？", parent=self):
            return
        try:
            self.store.restore(path)
            self.selected_id = None
            self.refresh()
            messagebox.showinfo("恢复完成", "巡检记录和审计链已恢复。", parent=self)
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc), parent=self)


def self_test():
    assert len(CHECKLIST) == 17 and len(RULES) == len(CHECKLIST)
    with tempfile.TemporaryDirectory() as directory:
        store = InspectionStore(Path(directory) / "inspection.json")
        inspection_id = store.create_inspection("测试门店", "测试检查人")
        store.update_check(inspection_id, "FS-001", "不合格", "票据缺失", "张三", date.today().isoformat())
        second_id = store.create_inspection("测试门店", "复查员")
        store.update_check(second_id, "FS-001", "不合格", "复查仍缺失", "李四", date.today().isoformat())
        assert store.repeated_findings() == ["FS-001"]
        assert store.store_risk_report()[0]["重复规则"] == "FS-001"
        assert store.dashboard()["待整改"] == 2
        assert store.score(store.get_inspection(inspection_id)) is not None
        backup = Path(directory) / "backup.json"
        store.backup(backup)
        store.close_finding(inspection_id, "FS-001", "补齐票据并复核")
        store.restore(backup)
        assert store.dashboard()["待整改"] == 1
        assert verify_event_chain(store.events)
    print("SELF_TEST_OK", flush=True)


def main():
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        return 0
    require_license(PRODUCT)
    App().mainloop()
    return 0


if __name__ == "__main__":
    if os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    raise SystemExit(main())
