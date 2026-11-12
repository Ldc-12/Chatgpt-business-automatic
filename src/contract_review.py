"""Persistent, traceable human review decisions for offline contract screening."""
import csv
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

REVIEW_FORMAT = "mainland-contract-review"
REVIEW_VERSION = 1
REVIEW_DECISIONS = ("已复核（无待办）", "需补充材料", "暂缓处理")
REVIEW_CSV_FIELDS = [
    "合同编号", "合同名称", "来源文件", "来源SHA256", "规则版本",
    "风险命中数", "风险明细", "风险明细SHA256", "人工结论", "复核人", "复核备注",
]
RECORD_FIELDS = [
    "复核编号", "复核时间", "合同编号", "合同名称", "来源文件", "来源SHA256",
    "规则版本", "风险命中数", "风险明细SHA256", "人工结论", "复核人", "复核备注",
    "风险明细",
]
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_REVIEW_ROWS = 50000
MAX_FINDINGS = 1000
MAX_NOTE_CHARS = 4000
MAX_REVIEW_CSV_BYTES = 50 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def findings_sha256(findings):
    return hashlib.sha256(_canonical(findings)).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _findings(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("风险明细不是有效 JSON") from exc
    if not isinstance(value, list) or len(value) > MAX_FINDINGS:
        raise ValueError("风险明细必须是有效列表且不超过 1000 项")
    required = ("等级", "规则编号", "检查项", "风险说明", "证据摘录", "建议动作")
    normalized = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in required):
            raise ValueError(f"第 {index} 项风险明细字段无效")
        normalized.append({key: item[key] for key in required})
    return normalized


def normalize_record(raw):
    if not isinstance(raw, dict):
        raise ValueError("复核记录必须是对象")
    record_id = str(raw.get("复核编号", "")).strip()
    if not record_id:
        raise ValueError("复核编号不能为空")
    source_name = str(raw.get("来源文件", "")).strip()
    source_hash = str(raw.get("来源SHA256", "")).strip().lower()
    ruleset = str(raw.get("规则版本", "")).strip()
    reviewer = str(raw.get("复核人", "")).strip()
    decision = str(raw.get("人工结论", "")).strip()
    note = str(raw.get("复核备注", "")).strip()
    if not source_name or len(source_name) > 260:
        raise ValueError("来源文件名不能为空且不得超过 260 个字符")
    if not SHA256_RE.fullmatch(source_hash):
        raise ValueError("来源 SHA256 必须是 64 位十六进制指纹")
    if not ruleset or len(ruleset) > 80:
        raise ValueError("规则版本不能为空且不得超过 80 个字符")
    if not reviewer or len(reviewer) > 120:
        raise ValueError("复核人不能为空且不得超过 120 个字符")
    if decision not in REVIEW_DECISIONS:
        raise ValueError("人工结论无效，请选择已复核、需补充材料或暂缓处理")
    if decision != REVIEW_DECISIONS[0] and not note:
        raise ValueError("选择需补充材料或暂缓处理时，必须填写复核备注")
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError("复核备注不得超过 4000 个字符")
    reviewed_at = str(raw.get("复核时间", "")).strip()
    try:
        datetime.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ValueError("复核时间必须是 ISO 日期时间") from exc
    findings = _findings(raw.get("风险明细"))
    try:
        count = int(str(raw.get("风险命中数", "")).strip())
    except ValueError as exc:
        raise ValueError("风险命中数必须是非负整数") from exc
    if count < 0 or count != len(findings):
        raise ValueError("风险命中数与风险明细数量不一致")
    if count > 0 and decision == REVIEW_DECISIONS[0] and not note:
        raise ValueError("存在风险提示时，标记已复核（无待办）必须填写复核备注")
    detail_hash = str(raw.get("风险明细SHA256", "")).strip().lower()
    actual_hash = findings_sha256(findings)
    if not SHA256_RE.fullmatch(detail_hash) or detail_hash != actual_hash:
        raise ValueError("风险明细 SHA256 不匹配，草稿内容可能被修改")
    return {
        "复核编号": record_id,
        "复核时间": reviewed_at,
        "合同编号": str(raw.get("合同编号", "")).strip(),
        "合同名称": str(raw.get("合同名称", "")).strip(),
        "来源文件": source_name,
        "来源SHA256": source_hash,
        "规则版本": ruleset,
        "风险命中数": str(count),
        "风险明细SHA256": actual_hash,
        "人工结论": decision,
        "复核人": reviewer,
        "复核备注": note,
        "风险明细": findings,
    }


def spreadsheet_safe_cell(value):
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


class ReviewStore:
    """Append-only review history; each re-review is a separate dated record."""

    def __init__(self, path):
        self.path = Path(path)
        self.records = []
        self.load()

    @staticmethod
    def validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError("复核备份根对象必须是对象")
        if payload.get("format") != REVIEW_FORMAT:
            raise ValueError("复核备份格式不受支持")
        if type(payload.get("version")) is not int or payload.get("version") != REVIEW_VERSION:
            raise ValueError("复核备份版本不受支持")
        raw_records = payload.get("records")
        if not isinstance(raw_records, list) or len(raw_records) > MAX_REVIEW_ROWS:
            raise ValueError("复核备份记录列表无效或超过数量上限")
        records = [normalize_record(item) for item in raw_records]
        ids = [item["复核编号"] for item in records]
        if len(ids) != len(set(ids)):
            raise ValueError("复核编号重复")
        return records

    def load(self):
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = self.validate_payload(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"复核记录无法读取，原文件未修改：{exc}") from exc

    def payload(self):
        return {"format": REVIEW_FORMAT, "version": REVIEW_VERSION, "records": self.records}

    def save(self):
        if len(self.records) > MAX_REVIEW_ROWS:
            raise ValueError("复核记录超过 50000 条上限，请先导出归档")
        payload = self.payload()
        self.validate_payload(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def import_csv(self, path):
        if Path(path).stat().st_size > MAX_REVIEW_CSV_BYTES:
            raise ValueError("复核 CSV 超过 50 MiB 安全上限")
        incoming = []
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(REVIEW_CSV_FIELDS).issubset(reader.fieldnames):
                raise ValueError("CSV 缺少复核字段：" + "、".join(REVIEW_CSV_FIELDS))
            for line, raw in enumerate(reader, 2):
                try:
                    item = dict(raw)
                    item["复核编号"] = uuid.uuid4().hex.upper()
                    item["复核时间"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    incoming.append(normalize_record(item))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        if not incoming:
            raise ValueError("CSV 中没有可导入的复核记录")
        if len(self.records) + len(incoming) > MAX_REVIEW_ROWS:
            raise ValueError("复核记录超过 50000 条上限，请先导出归档")

        def fingerprint(item):
            return (item["来源SHA256"], item["规则版本"], item["风险明细SHA256"],
                    item["人工结论"], item["复核人"], item["复核备注"])

        existing = {fingerprint(item) for item in self.records}
        batch = [fingerprint(item) for item in incoming]
        if len(batch) != len(set(batch)) or existing.intersection(batch):
            raise ValueError("发现完全重复的复核记录，整批未导入；如需重新复核，请修改复核结论或备注")
        old = self.records[:]
        self.records.extend(incoming)
        try:
            self.save()
        except Exception:
            self.records = old
            raise
        return len(incoming)

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RECORD_FIELDS)
            writer.writeheader()
            for item in self.records:
                row = dict(item)
                row["风险明细"] = json.dumps(item["风险明细"], ensure_ascii=False, separators=(",", ":"))
                writer.writerow({field: spreadsheet_safe_cell(row.get(field, "")) for field in RECORD_FIELDS})

    def restore_payload(self, payload):
        records = self.validate_payload(payload)
        old = self.records[:]
        self.records = records
        try:
            self.save()
        except Exception:
            self.records = old
            raise
