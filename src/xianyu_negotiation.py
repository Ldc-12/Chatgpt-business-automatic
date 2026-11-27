"""Offline Xianyu inquiry conversion and negotiation review ledger."""
from __future__ import annotations
import csv, hashlib, io, json, os, tempfile, uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

PRODUCT = "闲鱼询价转化与议价复盘助手"
FIELDS = (
    "记录编号", "商品编号", "订单编号", "商品名称", "SKU", "买家备注", "询价日期",
    "标价", "最低接受价", "买家报价", "卖家回价", "成交价",
    "商品成本", "平台费用", "运费成本", "结果",
    "最近沟通日期", "下次跟进日期", "未成交原因", "内部备注",
)
IMPORT_REQUIRED = ("商品编号", "商品名称", "询价日期")
MONEY_FIELDS = ("标价", "最低接受价", "买家报价", "卖家回价", "成交价", "商品成本", "平台费用", "运费成本")
RESULTS = ("待回复", "议价中", "已成交", "未成交", "已取消")
OPEN_RESULTS = ("待回复", "议价中")
CENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999.99")


def default_data_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MainlandBusinessTools" / "xianyu_negotiation_review.json"


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


_FORMULA_PREFIXES = ("=", "+", "-", "@")
_FORMULA_LEADING_CONTROLS = "\\t\\r\\n"


def _needs_formula_escape(text: str) -> bool:
    if not text:
        return False
    if text[0] == "'" or text[0] in _FORMULA_LEADING_CONTROLS:
        return True
    return text.lstrip().startswith(_FORMULA_PREFIXES)


def _safe_text(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if _needs_formula_escape(text) else text


def _restore_safe_text(value) -> str:
    text = "" if value is None else str(value)
    if not text.startswith("'"):
        return text
    original = text[1:]
    if original.startswith("'") or (
        original and (
            original[0] in _FORMULA_LEADING_CONTROLS
            or original.lstrip().startswith(_FORMULA_PREFIXES)
        )
    ):
        return original
    return text


def _money(value, field: str) -> Decimal:
    raw = "" if value is None else str(value).strip()
    raw = raw.replace("￥", "").replace("¥", "").replace(",", "")
    if not raw:
        raw = "0"
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是有效金额") from None
    if not amount.is_finite() or amount < 0 or amount > MAX_MONEY:
        raise ValueError(f"{field}必须在 0 至 {MAX_MONEY} 之间")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _date_value(value, field: str, *, required: bool = False) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD") from None
    if parsed.isoformat() != text:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD")
    return text


def normalize_row(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("询价记录必须是对象")
    row = {field: str(raw.get(field, "") or "").strip() for field in FIELDS}
    row["记录编号"] = row["记录编号"] or ("XN-" + uuid.uuid4().hex[:12].upper())
    for field in ("商品编号", "商品名称"):
        if not row[field]:
            raise ValueError(f"{field}不能为空")
    row["询价日期"] = _date_value(row["询价日期"], "询价日期", required=True)
    row["最近沟通日期"] = _date_value(row["最近沟通日期"], "最近沟通日期")
    row["下次跟进日期"] = _date_value(row["下次跟进日期"], "下次跟进日期")
    inquiry_date = date.fromisoformat(row["询价日期"])
    if row["最近沟通日期"] and date.fromisoformat(row["最近沟通日期"]) < inquiry_date:
        raise ValueError("最近沟通日期不能早于询价日期")
    if row["下次跟进日期"] and date.fromisoformat(row["下次跟进日期"]) < inquiry_date:
        raise ValueError("下次跟进日期不能早于询价日期")
    for field in MONEY_FIELDS:
        row[field] = format(_money(row[field], field), ".2f")
    if Decimal(row["标价"]) <= 0:
        raise ValueError("标价必须大于 0")
    row["结果"] = row["结果"] or "待回复"
    if row["结果"] not in RESULTS:
        raise ValueError("结果必须是：" + "、".join(RESULTS))
    if row["结果"] == "已成交" and Decimal(row["成交价"]) <= 0:
        raise ValueError("已成交记录必须填写大于 0 的成交价")
    if row["结果"] != "已成交" and Decimal(row["成交价"]) > 0:
        raise ValueError("只有已成交记录才能填写成交价")
    return row


def _profit(row: dict) -> Decimal:
    if row["结果"] != "已成交":
        return Decimal("0.00")
    return (
        Decimal(row["成交价"]) - Decimal(row["商品成本"])
        - Decimal(row["平台费用"]) - Decimal(row["运费成本"])
    ).quantize(CENT, rounding=ROUND_HALF_UP)


def followup_rows(rows: list[dict], today: str | date | None = None) -> list[dict]:
    current = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    result = [
        row for row in rows
        if row["结果"] in OPEN_RESULTS
        and row["下次跟进日期"]
        and date.fromisoformat(row["下次跟进日期"]) <= current
    ]
    return sorted(result, key=lambda row: (row["下次跟进日期"], row["询价日期"], row["商品编号"], row["记录编号"]))


def summary_rows(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["商品编号"].casefold(), row["SKU"].casefold())].append(row)
    result = []
    for grouped in groups.values():
        sold = [row for row in grouped if row["结果"] == "已成交"]
        asking = [Decimal(row["标价"]) for row in grouped]
        sold_prices = [Decimal(row["成交价"]) for row in sold]
        discounts = [
            (Decimal(row["标价"]) - Decimal(row["成交价"])) * Decimal("100") / Decimal(row["标价"])
            for row in sold
        ]
        average_discount = sum(discounts, Decimal("0")) / len(discounts) if discounts else Decimal("0")
        first = grouped[0]
        result.append({
            "商品编号": first["商品编号"],
            "商品名称": " / ".join(sorted({row["商品名称"] for row in grouped})),
            "SKU": first["SKU"],
            "询价数": len(grouped),
            "成交数": len(sold),
            "转化率": f"{(Decimal(len(sold)) * Decimal('100') / Decimal(len(grouped))):.2f}%",
            "平均标价": format(sum(asking, Decimal("0")) / len(asking), ".2f"),
            "平均成交价": format(sum(sold_prices, Decimal("0")) / len(sold_prices), ".2f") if sold else "0.00",
            "平均议价幅度": f"{average_discount:.2f}%",
            "成交金额": format(sum(sold_prices, Decimal("0")), ".2f"),
            "估算毛利": format(sum((_profit(row) for row in sold), Decimal("0")), ".2f"),
            "低于底价成交数": sum(1 for row in sold if Decimal(row["最低接受价"]) > 0 and Decimal(row["成交价"]) < Decimal(row["最低接受价"])),
        })
    return sorted(result, key=lambda item: (-item["询价数"], item["商品编号"].casefold(), item["SKU"].casefold()))


def _validated_items(payload, label: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
        raise ValueError(f"{label}版本或结构不受支持")
    if any(not isinstance(row, dict) for row in payload["items"]):
        raise ValueError(f"{label}明细结构无效")
    return payload["items"]


class NegotiationStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.rows = self._load()

    @staticmethod
    def _validate_unique(rows):
        ids = [row["记录编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("记录编号重复")

    def _load(self):
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取询价台账：{exc}") from exc
        items = _validated_items(payload, "数据文件")
        rows = [normalize_row(row) for row in items]
        self._validate_unique(rows)
        return rows

    def _commit(self, rows):
        candidate = [normalize_row(row) for row in rows]
        self._validate_unique(candidate)
        _atomic_write(self.path, _canonical({"version": 1, "items": candidate}))
        self.rows = candidate

    def add(self, raw):
        row = normalize_row(raw)
        if any(item["记录编号"] == row["记录编号"] for item in self.rows):
            raise ValueError("记录编号已存在")
        self._commit(self.rows + [row])
        return row

    def update(self, record_id, raw):
        if not any(row["记录编号"] == record_id for row in self.rows):
            raise ValueError("找不到要编辑的询价记录")
        candidate, updated = [], None
        for existing in self.rows:
            if existing["记录编号"] == record_id:
                updated = normalize_row({**raw, "记录编号": record_id})
                candidate.append(updated)
            else:
                candidate.append(existing)
        self._commit(candidate)
        return updated

    def delete(self, record_id):
        candidate = [row for row in self.rows if row["记录编号"] != record_id]
        if len(candidate) == len(self.rows):
            raise ValueError("找不到要删除的询价记录")
        self._commit(candidate)

    def import_csv(self, path: Path) -> int:
        raw = Path(path).read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("gb18030")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError("CSV 列名不能重复")
        if not set(IMPORT_REQUIRED).issubset(headers):
            raise ValueError("CSV 必须包含商品编号、商品名称、询价日期三列")
        imported, seen = [], {row["记录编号"] for row in self.rows}
        for index, source in enumerate(reader, start=2):
            if None in source:
                raise ValueError(f"第 {index} 行列数超过表头")
            if not any(str(value or "").strip() for value in source.values()):
                continue
            row = {field: _restore_safe_text(source.get(field, "")) for field in FIELDS}
            if not row["记录编号"]:
                identity = "|".join(row.get(field, "") for field in ("商品编号", "商品名称", "SKU", "询价日期", "买家备注")) + f"|{index}"
                row["记录编号"] = "XN-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
            normalized = normalize_row(row)
            if normalized["记录编号"] in seen:
                raise ValueError(f"第 {index} 行记录编号重复：{normalized['记录编号']}")
            seen.add(normalized["记录编号"])
            imported.append(normalized)
        if imported:
            self._commit(self.rows + imported)
        return len(imported)

    def _export_rows(self, path, fields, rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _safe_text(row.get(field, "")) for field in fields})
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
        return len(rows)

    def export_csv(self, path):
        return self._export_rows(path, FIELDS, self.rows)

    def export_followups_csv(self, path, today=None):
        fields = ("记录编号", "商品编号", "商品名称", "SKU", "买家备注", "询价日期", "买家报价", "卖家回价", "结果", "下次跟进日期", "内部备注")
        return self._export_rows(path, fields, followup_rows(self.rows, today))

    def export_summary_csv(self, path):
        fields = ("商品编号", "商品名称", "SKU", "询价数", "成交数", "转化率", "平均标价", "平均成交价", "平均议价幅度", "成交金额", "估算毛利", "低于底价成交数")
        return self._export_rows(path, fields, summary_rows(self.rows))

    def backup(self, path):
        data = {"version": 1, "items": self.rows}
        payload = {**data, "sha256": hashlib.sha256(_canonical(data)).hexdigest()}
        _atomic_write(Path(path), _canonical(payload))

    def restore(self, path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取备份：{exc}") from exc
        items = _validated_items(payload, "备份")
        data = {"version": 1, "items": items}
        if payload.get("sha256") != hashlib.sha256(_canonical(data)).hexdigest():
            raise ValueError("备份 SHA256 校验失败")
        rows = [normalize_row(row) for row in items]
        self._validate_unique(rows)
        self._commit(rows)
        return len(rows)


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = NegotiationStore(root / "data.json")
        store.add({
            "商品编号": "XY-TEST-001", "商品名称": "测试手机", "询价日期": "2026-11-27",
            "标价": "1000", "最低接受价": "850", "结果": "待回复", "下次跟进日期": "2026-11-27",
        })
        store.add({
            "商品编号": "XY-TEST-001", "商品名称": "测试手机", "询价日期": "2026-11-27",
            "标价": "1000", "最低接受价": "850", "成交价": "900", "商品成本": "600",
            "平台费用": "10", "运费成本": "8", "结果": "已成交",
        })
        assert len(summary_rows(store.rows)) == 1
        assert summary_rows(store.rows)[0]["转化率"] == "50.00%"
        assert followup_rows(store.rows, "2026-11-27")
        store.export_csv(root / "records.csv")
        store.export_summary_csv(root / "summary.csv")
        store.backup(root / "backup.json")
        restored = NegotiationStore(root / "restored.json")
        assert restored.restore(root / "backup.json") == 2
        assert restored.rows == store.rows
    print("SELF_TEST_OK", flush=True)
