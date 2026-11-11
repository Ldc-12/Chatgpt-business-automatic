"""Offline after-sales dispute case and tamper-evident evidence-chain assistant.

The SHA-256 event chain detects edits to the local log; it does not prove who
created a file, when an event occurred, or that a record is legally admissible.
"""
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "售后纠纷证据链管理助手"
CASE_FIELDS = [
    "案件编号", "平台", "订单编号", "买家备注名", "商品名称", "纠纷类型",
    "购买日期", "响应截止日期", "退款金额", "补偿金额", "状态", "负责人", "备注",
]
EVIDENCE_FIELDS = [
    "证据编号", "案件编号", "原始文件名", "存储路径", "说明",
    "大小字节", "SHA256", "添加时间",
]
EVENT_FIELDS = [
    "序号", "时间", "案件编号", "事件类型", "说明", "证据编号",
    "记录快照SHA256", "前序哈希", "事件哈希",
]
STATUSES = {"待处理", "处理中", "待平台介入", "已解决", "已关闭"}
BACKUP_FORMAT = "mainland-after-sales-evidence-backup"
BACKUP_VERSION = 2
ZERO_HASH = "0" * 64
MAX_EVIDENCE_BYTES = 100 * 1024 * 1024
MAX_BACKUP_BYTES = 1024 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_component(value):
    text = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(value))
    text = text.strip("._")
    return text[:80] or "item"


def safe_relative(value):
    text = str(value or "")
    if not text or "\\" in text:
        raise ValueError("证据路径必须是非空的相对 POSIX 路径")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("证据路径包含不安全的目录跳转")
    windows_reserved = {"CON", "PRN", "AUX", "NUL"}
    windows_reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10))
    windows_reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in ("¹", "²", "³"))
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if (
            any(ord(ch) < 32 for ch in part)
            or any(ch in '<>:"|?*' for ch in part)
            or part.endswith((" ", "."))
            or stem in windows_reserved
        ):
            raise ValueError(f"证据路径包含 Windows 不支持的文件名：{part}")
    return path.as_posix()


def decimal_text(value, field):
    text = str(value if value is not None else "").replace(",", "").replace("，", "").strip()
    try:
        amount = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效金额") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field}必须是大于或等于 0 的有限金额")
    return format(amount.quantize(Decimal("0.01")), "f")


def optional_date(value, field):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式") from None


def normalize_case(row):
    if not isinstance(row, dict):
        raise ValueError("案件记录必须是对象")
    item = {field: str(row.get(field, "") or "").strip() for field in CASE_FIELDS}
    for field in ("案件编号", "平台", "订单编号", "商品名称", "纠纷类型"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    if any(ord(ch) < 32 for ch in item["案件编号"] + item["订单编号"]):
        raise ValueError("案件编号和订单编号不能包含控制字符")
    if item["状态"] not in STATUSES:
        raise ValueError("案件状态无效")
    item["购买日期"] = optional_date(item["购买日期"], "购买日期")
    item["响应截止日期"] = optional_date(item["响应截止日期"], "响应截止日期")
    if item["购买日期"] and item["响应截止日期"]:
        if date.fromisoformat(item["响应截止日期"]) < date.fromisoformat(item["购买日期"]):
            raise ValueError("响应截止日期不能早于购买日期")
    item["退款金额"] = decimal_text(item["退款金额"], "退款金额")
    item["补偿金额"] = decimal_text(item["补偿金额"], "补偿金额")
    return item


def event_hash(event):
    payload = {key: event[key] for key in EVENT_FIELDS if key != "事件哈希"}
    return sha256_bytes(canonical(payload))


def verify_event_chain(events):
    previous = ZERO_HASH
    for expected_seq, raw in enumerate(events, start=1):
        if not isinstance(raw, dict):
            raise ValueError("事件日志记录格式无效")
        item = {field: str(raw.get(field, "") or "") for field in EVENT_FIELDS}
        if item["序号"] != str(expected_seq):
            raise ValueError(f"事件日志序号不连续：第 {expected_seq} 条")
        try:
            datetime.fromisoformat(item["时间"])
        except ValueError:
            raise ValueError(f"第 {expected_seq} 条事件时间无效") from None
        snapshot_hash = item["记录快照SHA256"]
        if len(snapshot_hash) != 64 or any(ch not in "0123456789abcdef" for ch in snapshot_hash.lower()):
            raise ValueError(f"第 {expected_seq} 条案件记录快照 SHA256 无效")
        if item["前序哈希"] != previous:
            raise ValueError(f"事件链前序哈希不匹配：第 {expected_seq} 条")
        expected_hash = event_hash(item)
        if item["事件哈希"] != expected_hash:
            raise ValueError(f"事件链内容哈希不匹配：第 {expected_seq} 条")
        previous = expected_hash
    return previous


def verify_case_snapshots(cases, events):
    latest = {}
    for event in events:
        latest[event["案件编号"]] = event["记录快照SHA256"]
    case_ids = set()
    for row in cases:
        case_id = row["案件编号"]
        case_ids.add(case_id)
        expected = sha256_bytes(canonical(normalize_case(row)))
        if latest.get(case_id) != expected:
            raise ValueError(f"案件记录快照哈希不匹配：{case_id}")
    if set(latest) != case_ids:
        raise ValueError("案件与事件日志的关联不完整")
    return True


def csv_safe(value):
    text = str(value if value is not None else "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_restore(value):
    text = str(value if value is not None else "")
    if text.startswith("'") and text[1:].lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return text[1:]
    return text


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe(row.get(field, "")) for field in fields})


class EvidenceStore:
    """Atomic local case store with append-only SHA-256 chained events."""

    def __init__(self, path):
        self.path = Path(path)
        self.root = self.path.parent
        self.evidence_dir = self.root / "after_sales_evidence"
        self.cases = []
        self.evidence = []
        self.events = []
        self.load()

    @staticmethod
    def _unique(rows, field, label):
        values = [row[field] for row in rows]
        if len(values) != len(set(values)):
            raise ValueError(f"{label}重复，数据文件可能损坏")

    def _evidence_path(self, relative):
        rel = safe_relative(relative)
        target = (self.evidence_dir / Path(*PurePosixPath(rel).parts)).resolve()
        base = self.evidence_dir.resolve()
        if target != base and base not in target.parents:
            raise ValueError("证据路径越界")
        return target

    def _normalize_evidence(self, rows, case_ids):
        normalized = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("证据记录必须是对象")
            item = {field: str(raw.get(field, "") or "").strip() for field in EVIDENCE_FIELDS}
            if not item["证据编号"] or item["案件编号"] not in case_ids:
                raise ValueError("证据编号为空或引用了不存在的案件")
            item["存储路径"] = safe_relative(item["存储路径"])
            try:
                size = int(item["大小字节"])
            except ValueError:
                raise ValueError("证据大小无效") from None
            if size < 0 or len(item["SHA256"]) != 64:
                raise ValueError("证据大小或 SHA256 无效")
            if any(ch not in "0123456789abcdef" for ch in item["SHA256"].lower()):
                raise ValueError("证据 SHA256 格式无效")
            try:
                datetime.fromisoformat(item["添加时间"])
            except ValueError:
                raise ValueError("证据添加时间无效") from None
            normalized.append(item)
        self._unique(normalized, "证据编号", "证据编号")
        return normalized

    @staticmethod
    def _normalize_events(rows, case_ids, evidence_ids):
        normalized = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("事件日志必须是对象")
            item = {field: str(raw.get(field, "") or "") for field in EVENT_FIELDS}
            if item["案件编号"] not in case_ids:
                raise ValueError("事件日志引用了不存在的案件")
            if item["证据编号"] and item["证据编号"] not in evidence_ids:
                raise ValueError("事件日志引用了不存在的证据")
            normalized.append(item)
        verify_event_chain(normalized)
        return normalized

    def _verify_evidence_files(self, rows):
        for row in rows:
            path = self._evidence_path(row["存储路径"])
            if not path.is_file():
                raise ValueError(f"证据文件缺失：{row['原始文件名']}")
            if path.stat().st_size != int(row["大小字节"]):
                raise ValueError(f"证据文件大小已变化：{row['原始文件名']}")
            if sha256_file(path) != row["SHA256"]:
                raise ValueError(f"证据文件哈希已变化：{row['原始文件名']}")

    def load(self):
        if not self.path.exists():
            self.cases, self.evidence, self.events = [], [], []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
                raise ValueError("本地数据格式不受支持")
            if payload.get("version") != BACKUP_VERSION:
                raise ValueError("本地数据版本不受支持")
            raw_cases, raw_evidence, raw_events = (
                payload.get("cases"), payload.get("evidence"), payload.get("events")
            )
            if not all(isinstance(rows, list) for rows in (raw_cases, raw_evidence, raw_events)):
                raise ValueError("本地数据缺少案件、证据或事件列表")
            cases = [normalize_case(row) for row in raw_cases]
            self._unique(cases, "案件编号", "案件编号")
            case_ids = {row["案件编号"] for row in cases}
            evidence = self._normalize_evidence(raw_evidence, case_ids)
            evidence_ids = {row["证据编号"] for row in evidence}
            events = self._normalize_events(raw_events, case_ids, evidence_ids)
            verify_case_snapshots(cases, events)
            self._verify_evidence_files(evidence)
            self.cases, self.evidence, self.events = cases, evidence, events
        except (OSError, json.JSONDecodeError, TypeError, AttributeError, ValueError) as exc:
            raise ValueError(f"本地数据校验失败，原文件未修改：{exc}") from exc

    def _commit(self, cases, evidence, events):
        cases = [normalize_case(row) for row in cases]
        self._unique(cases, "案件编号", "案件编号")
        case_ids = {row["案件编号"] for row in cases}
        evidence = self._normalize_evidence(evidence, case_ids)
        evidence_ids = {row["证据编号"] for row in evidence}
        events = self._normalize_events(events, case_ids, evidence_ids)
        verify_case_snapshots(cases, events)
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "cases": cases,
            "evidence": evidence,
            "events": events,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        self.cases, self.evidence, self.events = cases, evidence, events

    def _append_event(self, events, case_id, kind, description, evidence_id="", case_snapshot=None):
        if case_snapshot is None:
            case_snapshot = next((row for row in self.cases if row["案件编号"] == case_id), None)
        if case_snapshot is None:
            raise ValueError(f"找不到案件快照：{case_id}")
        snapshot_hash = sha256_bytes(canonical(normalize_case(case_snapshot)))
        previous = events[-1]["事件哈希"] if events else ZERO_HASH
        event = {
            "序号": str(len(events) + 1),
            "时间": datetime.now().isoformat(timespec="seconds"),
            "案件编号": case_id,
            "事件类型": kind,
            "说明": description,
            "证据编号": evidence_id,
            "记录快照SHA256": snapshot_hash,
            "前序哈希": previous,
            "事件哈希": "",
        }
        event["事件哈希"] = event_hash(event)
        return events + [event]

    def add_case(self, row):
        item = normalize_case(row)
        if any(existing["案件编号"] == item["案件编号"] for existing in self.cases):
            raise ValueError("案件编号已存在")
        events = self._append_event(list(self.events), item["案件编号"], "创建案件", "建立售后案件记录", case_snapshot=item)
        self._commit(self.cases + [item], self.evidence, events)

    def update_case(self, case_id, row):
        current = next((item for item in self.cases if item["案件编号"] == case_id), None)
        if current is None:
            raise ValueError("找不到所选案件")
        item = normalize_case(row)
        if item["案件编号"] != case_id:
            raise ValueError("案件编号创建后不可修改，以保持证据关联")
        changes = []
        for field in CASE_FIELDS:
            if field != "案件编号" and current.get(field) != item.get(field):
                changes.append(field)
        if not changes:
            return
        description = "更新字段：" + "、".join(changes)
        events = self._append_event(list(self.events), case_id, "更新案件", description, case_snapshot=item)
        if current["状态"] != item["状态"]:
            events = self._append_event(events, case_id, "状态变更", f"{current['状态']} → {item['状态']}", case_snapshot=item)
        cases = [item if row["案件编号"] == case_id else row for row in self.cases]
        self._commit(cases, self.evidence, events)

    def add_evidence(self, case_id, source_path, description=""):
        if not any(row["案件编号"] == case_id for row in self.cases):
            raise ValueError("找不到所选案件")
        source = Path(source_path)
        if not source.is_file():
            raise ValueError("请选择存在的普通文件")
        size = source.stat().st_size
        if size > MAX_EVIDENCE_BYTES:
            raise ValueError("单个证据文件不能超过 100 MiB")
        evidence_id = uuid.uuid4().hex.upper()
        filename = safe_component(source.name)
        relative = f"{safe_component(case_id)}/{evidence_id}_{filename}"
        target = self._evidence_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        try:
            shutil.copyfile(source, temp)
            copied_size = temp.stat().st_size
            digest = sha256_file(temp)
            if copied_size != size:
                raise ValueError("复制后文件大小不一致")
            os.replace(temp, target)
            item = {
                "证据编号": evidence_id,
                "案件编号": case_id,
                "原始文件名": source.name,
                "存储路径": relative,
                "说明": description.strip(),
                "大小字节": str(copied_size),
                "SHA256": digest,
                "添加时间": datetime.now().isoformat(timespec="seconds"),
            }
            current_case = next(row for row in self.cases if row["案件编号"] == case_id)
            events = self._append_event(list(self.events), case_id, "添加证据", f"{source.name} | SHA256 {digest}", evidence_id, case_snapshot=current_case)
            self._commit(self.cases, self.evidence + [item], events)
            return item
        except Exception:
            temp.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(CASE_FIELDS).issubset(set(reader.fieldnames)):
                raise ValueError("CSV 必须包含全部案件字段：" + "、".join(CASE_FIELDS))
            for line, row in enumerate(reader, start=2):
                try:
                    incoming.append(normalize_case({key: csv_restore(value) for key, value in row.items()}))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        self._unique(incoming, "案件编号", "CSV 案件编号")
        existing = {row["案件编号"] for row in self.cases}
        duplicates = existing.intersection(row["案件编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在案件，未导入任何数据：" + "、".join(sorted(duplicates)))
        if not incoming:
            return 0
        events = list(self.events)
        for row in incoming:
            events = self._append_event(events, row["案件编号"], "CSV 导入", "批量导入案件", case_snapshot=row)
        self._commit(self.cases + incoming, self.evidence, events)
        return len(incoming)

    def export_csv(self, path):
        write_csv(path, CASE_FIELDS, self.cases)

    def export_evidence_csv(self, path):
        write_csv(path, EVIDENCE_FIELDS, self.evidence)

    def export_events_csv(self, path, case_id=None):
        rows = [row for row in self.events if not case_id or row["案件编号"] == case_id]
        write_csv(path, EVENT_FIELDS, rows)

    def events_for(self, case_id):
        return [row for row in self.events if row["案件编号"] == case_id]

    def evidence_for(self, case_id):
        return [row for row in self.evidence if row["案件编号"] == case_id]

    def verify_integrity(self):
        errors = []
        try:
            verify_event_chain(self.events)
            verify_case_snapshots(self.cases, self.events)
        except ValueError as exc:
            errors.append(str(exc))
        for row in self.evidence:
            try:
                path = self._evidence_path(row["存储路径"])
                if not path.is_file():
                    errors.append(f"证据文件缺失：{row['原始文件名']}")
                elif path.stat().st_size != int(row["大小字节"]):
                    errors.append(f"证据文件大小已变化：{row['原始文件名']}")
                elif sha256_file(path) != row["SHA256"]:
                    errors.append(f"证据文件哈希已变化：{row['原始文件名']}")
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        return errors

    @staticmethod
    def _zip_manifest(entries, manifest_format):
        return {
            "format": manifest_format,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "files": {
                name: {"size": len(data), "sha256": sha256_bytes(data)}
                for name, data in sorted(entries.items())
            },
        }

    def _atomic_zip(self, path, entries, manifest_format):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest = self._zip_manifest(entries, manifest_format)
        temp = target.with_name(target.name + ".tmp")
        try:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
            with zipfile.ZipFile(temp) as archive:
                if archive.testzip() is not None:
                    raise ValueError("生成的 ZIP CRC 校验失败")
            os.replace(temp, target)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def export_case_bundle(self, case_id, path):
        case = next((row for row in self.cases if row["案件编号"] == case_id), None)
        if case is None:
            raise ValueError("找不到所选案件")
        errors = self.verify_integrity()
        if errors:
            raise ValueError("证据完整性校验失败：" + "；".join(errors))
        entries = {
            "case.json": json.dumps(case, ensure_ascii=False, indent=2).encode("utf-8"),
        }
        events = self.events_for(case_id)
        events_csv = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="")
        writer = csv.DictWriter(events_csv, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows({field: csv_safe(row.get(field, "")) for field in EVENT_FIELDS} for row in events)
        events_csv.seek(0)
        entries["events.csv"] = events_csv.read().encode("utf-8-sig")
        events_csv.close()
        entries["event-chain.json"] = json.dumps(
            {
                "format": "mainland-after-sales-case-event-reference",
                "version": 1,
                "scope": "case-only",
                "case_id": case_id,
                "event_count": len(events),
                "global_chain_head": self.events[-1]["事件哈希"] if self.events else ZERO_HASH,
                "note": "本文件只包含当前案件事件，保留原始序号和前序哈希；完整全局事件链须在本地数据文件中校验。本文件不独立证明全局链完整性。",
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        evidence_rows = self.evidence_for(case_id)
        evidence_csv = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="")
        evidence_writer = csv.DictWriter(evidence_csv, fieldnames=EVIDENCE_FIELDS)
        evidence_writer.writeheader()
        evidence_writer.writerows({field: csv_safe(row.get(field, "")) for field in EVIDENCE_FIELDS} for row in evidence_rows)
        evidence_csv.seek(0)
        entries["evidence-index.csv"] = evidence_csv.read().encode("utf-8-sig")
        evidence_csv.close()
        for row in evidence_rows:
            source = self._evidence_path(row["存储路径"])
            entries[f"evidence/{row['证据编号']}_{safe_component(row['原始文件名'])}"] = source.read_bytes()
        self._atomic_zip(path, entries, "mainland-after-sales-case-export")

    def backup(self, path):
        errors = self.verify_integrity()
        if errors:
            raise ValueError("备份前完整性校验失败：" + "；".join(errors))
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "cases": self.cases,
            "evidence": self.evidence,
            "events": self.events,
        }
        entries = {"data.json": json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")}
        for row in self.evidence:
            entries[f"evidence/{row['存储路径']}"] = self._evidence_path(row["存储路径"]).read_bytes()
        self._atomic_zip(path, entries, BACKUP_FORMAT)

    def restore(self, path):
        archive_path = Path(path)
        if archive_path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("备份文件超过 1 GiB，拒绝恢复")
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("备份 ZIP CRC 校验失败")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("备份包含重复文件名")
            file_names = [name for name in names if not name.endswith("/")]
            if sum(archive.getinfo(name).file_size for name in file_names) > MAX_BACKUP_BYTES:
                raise ValueError("备份解压后的总大小超过 1 GiB，拒绝恢复")
            for name in file_names:
                safe_relative(name)
            if "manifest.json" not in file_names or "data.json" not in file_names:
                raise ValueError("备份缺少 manifest.json 或 data.json")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
                raise ValueError("备份格式不受支持")
            expected = manifest.get("files")
            actual_names = set(file_names) - {"manifest.json"}
            if not isinstance(expected, dict) or set(expected) != actual_names:
                raise ValueError("备份清单与 ZIP 文件列表不一致")
            for name in actual_names:
                data = archive.read(name)
                meta = expected[name]
                if not isinstance(meta, dict):
                    raise ValueError(f"备份清单元数据无效：{name}")
                try:
                    expected_size = int(meta.get("size", -1))
                except (TypeError, ValueError):
                    raise ValueError(f"备份清单文件大小无效：{name}") from None
                expected_hash = meta.get("sha256")
                if expected_size < 0 or not isinstance(expected_hash, str) or len(expected_hash) != 64:
                    raise ValueError(f"备份清单 SHA256 或大小无效：{name}")
                if len(data) != expected_size or sha256_bytes(data) != expected_hash:
                    raise ValueError(f"备份文件 SHA256 或大小不匹配：{name}")
            payload = json.loads(archive.read("data.json").decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != BACKUP_VERSION:
                raise ValueError("备份数据版本或格式不受支持")
            raw_cases, raw_evidence, raw_events = payload.get("cases"), payload.get("evidence"), payload.get("events")
            if not all(isinstance(rows, list) for rows in (raw_cases, raw_evidence, raw_events)):
                raise ValueError("备份缺少案件、证据或事件列表")
            cases = [normalize_case(row) for row in raw_cases]
            self._unique(cases, "案件编号", "案件编号")
            case_ids = {row["案件编号"] for row in cases}
            evidence = self._normalize_evidence(raw_evidence, case_ids)
            evidence_ids = {row["证据编号"] for row in evidence}
            events = self._normalize_events(raw_events, case_ids, evidence_ids)
            verify_case_snapshots(cases, events)
            referenced_members = {"data.json"} | {f"evidence/{row['存储路径']}" for row in evidence}
            if actual_names != referenced_members:
                raise ValueError("备份包含未引用的文件或缺少证据文件")
            for row in evidence:
                member = f"evidence/{row['存储路径']}"
                if member not in actual_names:
                    raise ValueError(f"备份缺少证据文件：{row['原始文件名']}")
                data = archive.read(member)
                if len(data) != int(row["大小字节"]) or sha256_bytes(data) != row["SHA256"]:
                    raise ValueError(f"证据记录与备份文件不一致：{row['原始文件名']}")
            staging = self.root / (".after_sales_restore_" + uuid.uuid4().hex)
            old = self.root / (".after_sales_previous_" + uuid.uuid4().hex)
            staging.mkdir(parents=True, exist_ok=False)
            try:
                for row in evidence:
                    member = f"evidence/{row['存储路径']}"
                    target = staging / Path(*PurePosixPath(row["存储路径"]).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))
                had_old = self.evidence_dir.exists()
                if had_old:
                    os.replace(self.evidence_dir, old)
                try:
                    os.replace(staging, self.evidence_dir)
                    self._commit(cases, evidence, events)
                except Exception:
                    if self.evidence_dir.exists():
                        shutil.rmtree(self.evidence_dir)
                    if had_old and old.exists():
                        os.replace(old, self.evidence_dir)
                    raise
                if old.exists():
                    shutil.rmtree(old)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "after_sales_cases.json"


def deadline_state(row, *, today=None):
    if row["状态"] in {"已解决", "已关闭"}:
        return "已结束"
    if not row["响应截止日期"]:
        return "未设置期限"
    today = today or date.today()
    days = (date.fromisoformat(row["响应截止日期"]) - today).days
    if days < 0:
        return f"已逾期 {-days} 天"
    if days == 0:
        return "今日截止"
    if days <= 3:
        return f"{days} 日内截止"
    return "正常"


def run_self_test():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = EvidenceStore(root / "cases.json")
        case = {
            "案件编号": "CASE-TEST", "平台": "闲鱼", "订单编号": "ORDER-001",
            "买家备注名": "测试买家", "商品名称": "测试商品", "纠纷类型": "退货争议",
            "购买日期": "2026-01-01", "响应截止日期": "2099-12-31",
            "退款金额": "10", "补偿金额": "0", "状态": "处理中",
            "负责人": "测试", "备注": "",
        }
        store.add_case(case)
        evidence_source = root / "chat.txt"
        evidence_source.write_text("本地自测证据", encoding="utf-8")
        store.add_evidence("CASE-TEST", evidence_source, "自测文件")
        backup = root / "backup.zip"
        store.backup(backup)
        restored = EvidenceStore(root / "restored" / "cases.json")
        restored.restore(backup)
        if restored.verify_integrity() or len(restored.evidence) != 1:
            raise SystemExit("SELF_TEST_FAILED")
    print("SELF_TEST_OK", flush=True)


class App:
    def __init__(self, root):
        self.root = root
        root.title("售后纠纷证据链管理助手｜大陆版")
        root.geometry("1120x680")
        try:
            self.store = EvidenceStore(default_data_path())
        except ValueError as exc:
            messagebox.showerror("数据校验失败", str(exc))
            raise
        self.search_var = tk.StringVar()
        top = ttk.Frame(root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="搜索案件 / 订单 / 商品").pack(side="left")
        search = ttk.Entry(top, textvariable=self.search_var, width=34)
        search.pack(side="left", padx=8)
        search.bind("<KeyRelease>", lambda _event: self.refresh())
        ttk.Label(top, text="哈希链只用于发现本地记录变化，不证明来源或法律效力。", foreground="#805000").pack(side="right")
        columns = ("案件编号", "平台", "订单编号", "商品名称", "纠纷类型", "状态", "响应截止日期", "退款金额", "期限")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=20)
        widths = (130, 75, 140, 160, 110, 90, 115, 90, 100)
        for column, width in zip(columns, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree.bind("<Double-1>", lambda _event: self.edit_case())
        actions = ttk.Frame(root, padding=12)
        actions.pack(fill="x")
        buttons = [
            ("新建案件", self.new_case), ("编辑案件", self.edit_case),
            ("添加证据", self.add_evidence), ("案件证据包", self.export_case),
            ("导入 CSV", self.import_csv), ("导出案件 CSV", self.export_csv),
            ("导出证据 CSV", self.export_evidence), ("事件日志", self.show_timeline),
            ("备份", self.backup), ("恢复", self.restore), ("校验完整性", self.verify),
        ]
        for index, (label, command) in enumerate(buttons):
            ttk.Button(actions, text=label, command=command).grid(row=index // 6, column=index % 6, padx=3, pady=4, sticky="ew")
        for column in range(6):
            actions.columnconfigure(column, weight=1)
        self.status = ttk.Label(root, text="", padding=(12, 4))
        self.status.pack(fill="x")
        self.refresh()

    def selected_case(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("请选择案件", "请先选择一条案件记录。")
            return None
        return self.tree.item(selection[0], "values")[0]

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        query = self.search_var.get().strip().lower()
        rows = sorted(self.store.cases, key=lambda row: (row["响应截止日期"] or "9999-12-31", row["案件编号"]))
        for row in rows:
            if query and not any(query in row[field].lower() for field in ("案件编号", "订单编号", "平台", "商品名称", "买家备注名")):
                continue
            self.tree.insert("", "end", values=(
                row["案件编号"], row["平台"], row["订单编号"], row["商品名称"],
                row["纠纷类型"], row["状态"], row["响应截止日期"], row["退款金额"],
                deadline_state(row),
            ))
        self.status.config(text=f"案件 {len(self.store.cases)} 条｜证据 {len(self.store.evidence)} 份｜事件 {len(self.store.events)} 条｜数据目录：{self.store.root}")

    def case_dialog(self, existing=None):
        current = existing or {field: "" for field in CASE_FIELDS}
        if not existing:
            current.update({"状态": "待处理", "退款金额": "0", "补偿金额": "0"})
        window = tk.Toplevel(self.root)
        window.title("编辑售后案件" if existing else "新建售后案件")
        window.transient(self.root)
        variables = {}
        for index, field in enumerate(CASE_FIELDS):
            ttk.Label(window, text=field).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            variable = tk.StringVar(value=current.get(field, ""))
            variables[field] = variable
            if field == "状态":
                widget = ttk.Combobox(window, textvariable=variable, values=sorted(STATUSES), state="readonly", width=38)
            else:
                widget = ttk.Entry(window, textvariable=variable, width=42)
            widget.grid(row=index, column=1, padx=8, pady=4, sticky="w")
        result = {"saved": False}
        def save():
            row = {field: variable.get() for field, variable in variables.items()}
            try:
                if existing:
                    self.store.update_case(existing["案件编号"], row)
                else:
                    self.store.add_case(row)
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)
                return
            result["saved"] = True
            window.destroy()
            self.refresh()
        ttk.Button(window, text="保存", command=save).grid(row=len(CASE_FIELDS), column=0, columnspan=2, pady=10)
        window.grab_set()
        self.root.wait_window(window)
        return result["saved"]

    def new_case(self):
        self.case_dialog()

    def edit_case(self):
        case_id = self.selected_case()
        if not case_id:
            return
        row = next(item for item in self.store.cases if item["案件编号"] == case_id)
        self.case_dialog(dict(row))

    def add_evidence(self):
        case_id = self.selected_case()
        if not case_id:
            return
        source = filedialog.askopenfilename(parent=self.root, title="选择要归档的证据文件")
        if not source:
            return
        description = simpledialog.askstring("证据说明", "说明该文件的内容或用途：", parent=self.root) or ""
        try:
            item = self.store.add_evidence(case_id, source, description)
        except (ValueError, OSError) as exc:
            messagebox.showerror("归档失败", str(exc))
            return
        self.refresh()
        messagebox.showinfo("证据已归档", f"已复制到本地证据目录。\nSHA256：{item['SHA256']}")

    def export_case(self):
        case_id = self.selected_case()
        if not case_id:
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".zip", filetypes=[("ZIP 文件", "*.zip")])
        if not path:
            return
        try:
            self.store.export_case_bundle(case_id, path)
            messagebox.showinfo("导出完成", "案件摘要、事件记录、证据文件及 SHA256 清单已导出。")
        except (ValueError, OSError) as exc:
            messagebox.showerror("导出失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            count = self.store.import_csv(path)
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 条案件。")
        except (ValueError, OSError) as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            self.store.export_csv(path)
            messagebox.showinfo("导出完成", "案件 CSV 已导出；公式开头的文本已加安全前缀。")

    def export_evidence(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            self.store.export_evidence_csv(path)
            messagebox.showinfo("导出完成", "证据索引 CSV 已导出。")

    def show_timeline(self):
        case_id = self.selected_case()
        if not case_id:
            return
        window = tk.Toplevel(self.root)
        window.title(f"案件事件日志｜{case_id}")
        window.geometry("900x420")
        tree = ttk.Treeview(window, columns=("序号", "时间", "事件类型", "说明", "前序哈希", "事件哈希"), show="headings")
        for column, width in zip(("序号", "时间", "事件类型", "说明", "前序哈希", "事件哈希"), (55, 150, 100, 260, 150, 150)):
            tree.heading(column, text=column)
            tree.column(column, width=width)
        tree.pack(fill="both", expand=True)
        for row in self.store.events_for(case_id):
            tree.insert("", "end", values=tuple(row[field] for field in ("序号", "时间", "事件类型", "说明", "前序哈希", "事件哈希")))

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".zip", filetypes=[("ZIP 备份", "*.zip")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "案件数据、事件链和证据文件已一并备份。")
            except (ValueError, OSError) as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("ZIP 备份", "*.zip")])
        if not path:
            return
        if not messagebox.askyesno("确认恢复", "恢复会替换当前案件数据和证据文件，建议先另行备份。是否继续？"):
            return
        try:
            self.store.restore(path)
            self.refresh()
            messagebox.showinfo("恢复完成", "数据和证据已恢复，并通过 ZIP 清单校验。")
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            messagebox.showerror("恢复失败", str(exc))


    def verify(self):
        errors = self.store.verify_integrity()
        if errors:
            messagebox.showerror("完整性校验未通过", "\n".join(errors))
        else:
            messagebox.showinfo("完整性校验通过", f"事件链 {len(self.store.events)} 条，证据 {len(self.store.evidence)} 份，哈希校验通过。\n注意：哈希链不证明文件来源、形成时间或法律效力。")


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        run_self_test()
        os._exit(0)
    require_license(PRODUCT)
    root = tk.Tk()
    App(root)
    root.mainloop()
