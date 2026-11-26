"""Offline Xianyu parcel freight estimator with seller-maintained tariff cards."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-xianyu-freight-calculator"
BACKUP_FORMAT = "mainland-xianyu-freight-calculator-backup"
VERSION = 1
MAX_ROWS = 50000
MAX_BYTES = 50 * 1024 * 1024
MAX_NUMERIC_ABS = Decimal("1000000000")
MAX_TEXT = 2000
CARRIERS = (
    "顺丰速运", "中通快递", "圆通速递", "申通快递", "韵达速递",
    "极兔速递", "中国邮政", "邮政EMS", "京东物流", "德邦快递", "其他",
)
RATE_FIELDS = (
    "规则编号", "承运商", "目的地区关键词", "抛重系数(cm³/kg)", "首重(kg)",
    "首费(元)", "续重单位(kg)", "续费(元)", "附加费(元)",
    "有效起始日期", "有效结束日期", "备注",
)
QUOTE_FIELDS = (
    "试算编号", "订单编号", "商品/SKU", "承运商", "目的地区", "费率规则编号",
    "实重(kg)", "长(cm)", "宽(cm)", "高(cm)", "抛重系数(cm³/kg)",
    "首重(kg)", "首费(元)", "续重单位(kg)", "续费(元)", "附加费(元)",
    "体积重(kg)", "计费重量(kg)", "预估运费(元)", "实际运费(元)",
    "运费差额(元)", "试算日期", "备注",
)
RATE_REQUIRED = set(RATE_FIELDS[:9])
QUOTE_REQUIRED = {"订单编号", "承运商", "目的地区", "实重(kg)", "长(cm)", "宽(cm)", "高(cm)"}


def _text(value, label: str, limit: int = 160) -> str:
    result = str("" if value is None else value).strip()
    if len(result) > limit:
        raise ValueError(f"{label}长度不能超过 {limit} 个字符")
    return result


def _decimal(value, label: str, *, allow_blank: bool = False) -> Decimal | None:
    raw = str("" if value is None else value).strip()
    raw = raw.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    if not raw:
        if allow_blank:
            return None
        raise ValueError(f"{label}不能为空")
    if len(raw) > 64:
        raise ValueError(f"{label}输入过长")
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not number.is_finite() or abs(number) > MAX_NUMERIC_ABS:
        raise ValueError(f"{label}超出支持范围")
    return number


def _money(value: Decimal, label: str) -> str:
    try:
        return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    except InvalidOperation as exc:
        raise ValueError(f"{label}超出金额精度范围") from exc


def _quantity(value: Decimal, label: str, *, minimum: Decimal = Decimal("0")) -> str:
    if value < minimum:
        raise ValueError(f"{label}必须大于或等于 {minimum}")
    return format(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), "f").rstrip("0").rstrip(".") or "0"


def _date(value, label: str, *, allow_blank: bool = False) -> str:
    raw = str("" if value is None else value).strip()
    if not raw and allow_blank:
        return ""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式")
    return raw


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _safe_text(value) -> str:
    text = str("" if value is None else value)
    probe = text.lstrip(" \t\r\n")
    if probe.startswith("'") and len(probe) > 1 and probe[1] in "=+-@":
        return "'" + text
    if probe and probe[0] in "=+-@":
        return "'" + text
    return text


def _restore_safe_text(value) -> str:
    text = str("" if value is None else value)
    probe = text.lstrip(" \t\r\n")
    if probe.startswith("''") and len(probe) > 2 and probe[2] in "=+-@":
        index = len(text) - len(probe)
        return text[:index] + probe[1:]
    if probe.startswith("'") and len(probe) > 1 and probe[1] in "=+-@":
        index = len(text) - len(probe)
        return text[:index] + probe[1:]
    return text


def normalize_rate(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("费率规则必须是对象")
    row = {field: str("" if raw.get(field) is None else raw.get(field, "")).strip() for field in RATE_FIELDS}
    row["规则编号"] = row["规则编号"] or ("FR-" + uuid.uuid4().hex[:12].upper())
    row["规则编号"] = _text(row["规则编号"], "规则编号", 80)
    row["承运商"] = _text(row["承运商"], "承运商", 60)
    row["目的地区关键词"] = _text(row["目的地区关键词"], "目的地区关键词", 80)
    row["备注"] = _text(row["备注"], "备注", MAX_TEXT)
    if not row["承运商"] or (row["承运商"] not in CARRIERS and row["承运商"] != "全部承运商"):
        raise ValueError("承运商必须从内置列表中选择，或选择全部承运商")
    if not row["目的地区关键词"]:
        raise ValueError("目的地区关键词不能为空；全国通用规则请填写“全国”")
    divisor = _decimal(row["抛重系数(cm³/kg)"], "抛重系数")
    first_weight = _decimal(row["首重(kg)"], "首重")
    first_fee = _decimal(row["首费(元)"], "首费")
    step = _decimal(row["续重单位(kg)"], "续重单位")
    step_fee = _decimal(row["续费(元)"], "续费")
    surcharge = _decimal(row["附加费(元)"], "附加费", allow_blank=True) or Decimal("0")
    if divisor <= 0 or divisor > Decimal("1000000"):
        raise ValueError("抛重系数必须大于 0 且不超过 1000000")
    if first_weight <= 0 or first_weight > Decimal("1000"):
        raise ValueError("首重必须在 0–1000 kg 之间且大于 0")
    if step <= 0 or step > Decimal("1000"):
        raise ValueError("续重单位必须在 0–1000 kg 之间且大于 0")
    if min(first_fee, step_fee, surcharge) < 0:
        raise ValueError("首费、续费和附加费不能为负数")
    row["抛重系数(cm³/kg)"] = _quantity(divisor, "抛重系数", minimum=Decimal("0.001"))
    row["首重(kg)"] = _quantity(first_weight, "首重", minimum=Decimal("0.001"))
    row["首费(元)"] = _money(first_fee, "首费")
    row["续重单位(kg)"] = _quantity(step, "续重单位", minimum=Decimal("0.001"))
    row["续费(元)"] = _money(step_fee, "续费")
    row["附加费(元)"] = _money(surcharge, "附加费")
    row["有效起始日期"] = _date(row["有效起始日期"], "有效起始日期", allow_blank=True)
    row["有效结束日期"] = _date(row["有效结束日期"], "有效结束日期", allow_blank=True)
    if row["有效起始日期"] and row["有效结束日期"] and row["有效结束日期"] < row["有效起始日期"]:
        raise ValueError("有效结束日期不能早于有效起始日期")
    return row


def match_rate(rates: list[dict], carrier: str, destination: str, on_date: date | None = None) -> dict:
    on_date = on_date or date.today()
    if not isinstance(on_date, date):
        raise ValueError("费率匹配日期必须是日期对象")
    carrier = _text(carrier, "承运商", 60)
    destination = _text(destination, "目的地区", 120)
    if not carrier or not destination:
        raise ValueError("承运商和目的地区不能为空")
    candidates = []
    for raw in rates:
        rate = normalize_rate(raw)
        if rate["承运商"] not in {carrier, "全部承运商"}:
            continue
        keyword = rate["目的地区关键词"]
        if keyword != "全国" and keyword not in destination:
            continue
        if rate["有效起始日期"] and on_date < date.fromisoformat(rate["有效起始日期"]):
            continue
        if rate["有效结束日期"] and on_date > date.fromisoformat(rate["有效结束日期"]):
            continue
        specificity = 0 if keyword == "全国" else len(keyword)
        specificity += 1000 if rate["承运商"] == carrier else 0
        candidates.append((specificity, rate))
    if not candidates:
        raise ValueError(f"没有匹配的费率规则：{carrier} / {destination} / {on_date.isoformat()}")
    best = max(score for score, _ in candidates)
    winners = [rate for score, rate in candidates if score == best]
    if len(winners) != 1:
        ids = "、".join(sorted(rate["规则编号"] for rate in winners))
        raise ValueError(f"费率规则匹配不唯一，请调整地区关键词或有效日期：{ids}")
    return winners[0]


def calculate_freight(package: dict, rate: dict) -> dict:
    if not isinstance(package, dict):
        raise ValueError("包裹信息必须是对象")
    tariff = normalize_rate(rate)
    carrier = _text(package.get("承运商"), "承运商", 60)
    destination = _text(package.get("目的地区"), "目的地区", 120)
    if carrier != tariff["承运商"] and tariff["承运商"] != "全部承运商":
        raise ValueError("费率规则承运商与包裹承运商不一致")
    if tariff["目的地区关键词"] != "全国" and tariff["目的地区关键词"] not in destination:
        raise ValueError("费率规则地区关键词与包裹目的地区不匹配")
    actual = _decimal(package.get("实重(kg)"), "实重")
    length = _decimal(package.get("长(cm)"), "长度")
    width = _decimal(package.get("宽(cm)"), "宽度")
    height = _decimal(package.get("高(cm)"), "高度")
    if min(actual, length, width, height) <= 0:
        raise ValueError("实重和包裹长、宽、高必须大于 0")
    if actual > Decimal("1000") or max(length, width, height) > Decimal("10000"):
        raise ValueError("重量或尺寸超出支持范围")
    divisor = Decimal(tariff["抛重系数(cm³/kg)"])
    first_weight = Decimal(tariff["首重(kg)"])
    step = Decimal(tariff["续重单位(kg)"])
    volume_weight = length * width * height / divisor
    if volume_weight.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) <= 0:
        raise ValueError("计算出的体积重小于 0.001 kg，请核对尺寸和抛重系数")
    basis = max(actual, volume_weight)
    extra_units = (
        int(((basis - first_weight) / step).to_integral_value(rounding=ROUND_CEILING))
        if basis > first_weight else 0
    )
    billable = first_weight + Decimal(extra_units) * step
    fee = (
        Decimal(tariff["首费(元)"])
        + Decimal(extra_units) * Decimal(tariff["续费(元)"])
        + Decimal(tariff["附加费(元)"])
    )
    return {
        "费率规则编号": tariff["规则编号"],
        "抛重系数(cm³/kg)": tariff["抛重系数(cm³/kg)"],
        "首重(kg)": tariff["首重(kg)"],
        "首费(元)": tariff["首费(元)"],
        "续重单位(kg)": tariff["续重单位(kg)"],
        "续费(元)": tariff["续费(元)"],
        "附加费(元)": tariff["附加费(元)"],
        "体积重(kg)": _quantity(volume_weight, "体积重"),
        "计费重量(kg)": _quantity(billable, "计费重量"),
        "预估运费(元)": _money(fee, "预估运费"),
    }


def normalize_quote(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("运费试算记录必须是对象")
    row = {field: str("" if raw.get(field) is None else raw.get(field, "")).strip() for field in QUOTE_FIELDS}
    row["试算编号"] = row["试算编号"] or ("FQ-" + uuid.uuid4().hex[:12].upper())
    row["试算编号"] = _text(row["试算编号"], "试算编号", 80)
    row["订单编号"] = _text(row["订单编号"], "订单编号", 120)
    row["商品/SKU"] = _text(row["商品/SKU"], "商品/SKU", 160)
    row["承运商"] = _text(row["承运商"], "承运商", 60)
    row["目的地区"] = _text(row["目的地区"], "目的地区", 120)
    row["费率规则编号"] = _text(row["费率规则编号"], "费率规则编号", 80)
    row["备注"] = _text(row["备注"], "备注", MAX_TEXT)
    if row["承运商"] not in CARRIERS:
        raise ValueError("承运商不在内置列表中")
    for field in ("订单编号", "承运商", "目的地区", "费率规则编号"):
        if not row[field]:
            raise ValueError(f"{field}不能为空")
    for field, label in (("实重(kg)", "实重"), ("长(cm)", "长度"), ("宽(cm)", "宽度"), ("高(cm)", "高度"), ("抛重系数(cm³/kg)", "抛重系数"), ("首重(kg)", "首重"), ("续重单位(kg)", "续重单位"), ("体积重(kg)", "体积重"), ("计费重量(kg)", "计费重量")):
        number = _decimal(row[field], label)
        if number <= 0:
            raise ValueError(f"{label}必须大于 0")
        row[field] = _quantity(number, label, minimum=Decimal("0.001"))
    for field, label in (("首费(元)", "首费"), ("续费(元)", "续费"), ("附加费(元)", "附加费"), ("预估运费(元)", "预估运费")):
        number = _decimal(row[field], label)
        if number < 0:
            raise ValueError(f"{label}不能为负数")
        row[field] = _money(number, label)
    actual = _decimal(row["实际运费(元)"], "实际运费", allow_blank=True)
    if actual is not None and actual < 0:
        raise ValueError("实际运费不能为负数")
    row["实际运费(元)"] = "" if actual is None else _money(actual, "实际运费")
    row["运费差额(元)"] = "" if actual is None else _money(actual - Decimal(row["预估运费(元)"]), "运费差额")
    row["试算日期"] = _date(row["试算日期"] or date.today().isoformat(), "试算日期")
    return row


def freight_summary(rows: list[dict]) -> dict:
    groups = {}
    total_estimated = Decimal("0")
    total_actual = Decimal("0")
    actual_count = 0
    for raw in rows:
        row = normalize_quote(raw)
        group = groups.setdefault(row["承运商"], {"承运商": row["承运商"], "试算单数": 0, "预估运费(元)": Decimal("0"), "已录实际单数": 0, "实际运费(元)": Decimal("0")})
        group["试算单数"] += 1
        group["预估运费(元)"] += Decimal(row["预估运费(元)"])
        total_estimated += Decimal(row["预估运费(元)"])
        if row["实际运费(元)"]:
            group["已录实际单数"] += 1
            group["实际运费(元)"] += Decimal(row["实际运费(元)"])
            total_actual += Decimal(row["实际运费(元)"])
            actual_count += 1
    result = []
    for group in groups.values():
        result.append({
            **group,
            "预估运费(元)": _money(group["预估运费(元)"], "预估运费"),
            "实际运费(元)": _money(group["实际运费(元)"], "实际运费"),
        })
    return {
        "试算总数": len(rows),
        "已录实际运费单数": actual_count,
        "累计预估运费(元)": _money(total_estimated, "累计预估运费"),
        "累计实际运费(元)": _money(total_actual, "累计实际运费"),
        "承运商汇总": sorted(result, key=lambda item: item["承运商"]),
    }


class FreightStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.rates, self.rows = self._load()

    def _load(self):
        if not self.path.exists():
            return [], []
        try:
            if self.path.stat().st_size > MAX_BYTES:
                raise ValueError("数据文件超过 50 MB 限制")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != VERSION or not isinstance(payload.get("rates"), list) or not isinstance(payload.get("items"), list):
                raise ValueError("数据文件版本或结构不受支持")
            if any(not isinstance(item, dict) for item in payload["rates"] + payload["items"]):
                raise ValueError("数据文件明细结构无效")
            rates = [normalize_rate(item) for item in payload["rates"]]
            rows = [normalize_quote(item) for item in payload["items"]]
            self._validate_unique(rates, rows)
            return rates, rows
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取运费试算数据：{exc}") from exc

    @staticmethod
    def _validate_unique(rates, rows):
        rate_ids = [item["规则编号"] for item in rates]
        quote_ids = [item["试算编号"] for item in rows]
        if len(rate_ids) != len(set(rate_ids)):
            raise ValueError("费率规则编号重复")
        if len(quote_ids) != len(set(quote_ids)):
            raise ValueError("试算编号重复")

    def _commit(self, rates=None, rows=None):
        new_rates = [normalize_rate(item) for item in (self.rates if rates is None else rates)]
        new_rows = [normalize_quote(item) for item in (self.rows if rows is None else rows)]
        if len(new_rates) > MAX_ROWS or len(new_rows) > MAX_ROWS:
            raise ValueError("记录数量超过上限")
        self._validate_unique(new_rates, new_rows)
        payload = _canonical({"version": VERSION, "rates": new_rates, "items": new_rows})
        if len(payload) > MAX_BYTES:
            raise ValueError("本地数据超过 50 MB 限制")
        _atomic_write(self.path, payload)
        self.rates, self.rows = new_rates, new_rows

    def add_rate(self, raw):
        rate = normalize_rate(raw)
        if any(item["规则编号"] == rate["规则编号"] for item in self.rates):
            raise ValueError("费率规则编号已存在")
        self._commit(rates=self.rates + [rate])
        return rate

    def update_rate(self, rule_id, raw):
        if not any(item["规则编号"] == rule_id for item in self.rates):
            raise ValueError("找不到要编辑的费率规则")
        candidate = [normalize_rate({**raw, "规则编号": rule_id}) if item["规则编号"] == rule_id else item for item in self.rates]
        self._commit(rates=candidate)

    def delete_rate(self, rule_id):
        candidate = [item for item in self.rates if item["规则编号"] != rule_id]
        if len(candidate) == len(self.rates):
            raise ValueError("找不到要删除的费率规则")
        self._commit(rates=candidate)

    def quote(self, raw, on_date: date | None = None):
        if not isinstance(raw, dict):
            raise ValueError("包裹信息必须是对象")
        quote_date = on_date or date.today()
        carrier = _text(raw.get("承运商"), "承运商", 60)
        destination = _text(raw.get("目的地区"), "目的地区", 120)
        rate = match_rate(self.rates, carrier, destination, quote_date)
        result = calculate_freight(raw, rate)
        row = normalize_quote({**raw, **result, "试算日期": quote_date.isoformat()})
        if any(item["试算编号"] == row["试算编号"] for item in self.rows):
            raise ValueError("试算编号已存在")
        self._commit(rows=self.rows + [row])
        return row

    def update_actual(self, quote_id, actual_freight):
        if not any(item["试算编号"] == quote_id for item in self.rows):
            raise ValueError("找不到要更新的试算记录")
        candidate = []
        updated = None
        for item in self.rows:
            if item["试算编号"] == quote_id:
                updated = normalize_quote({**item, "实际运费(元)": actual_freight})
                candidate.append(updated)
            else:
                candidate.append(item)
        self._commit(rows=candidate)
        return updated

    def import_csv(self, path: Path) -> int:
        raw = Path(path).read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("CSV 文件超过 50 MB 限制")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 不是可识别的 UTF-8 或 GB18030 编码") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not QUOTE_REQUIRED.issubset(reader.fieldnames):
            raise ValueError("CSV 必须包含订单编号、承运商、目的地区、实重和包裹长宽高")
        imported, seen = [], {row["试算编号"] for row in self.rows}
        for index, source in enumerate(reader, start=2):
            row = {field: _restore_safe_text(source.get(field, "")) for field in QUOTE_FIELDS}
            if not row["试算编号"]:
                identity = "|".join(row.get(field, "") for field in ("订单编号", "商品/SKU", "承运商", "目的地区")) + f"|{index}"
                row["试算编号"] = "FQ-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
            normalized = normalize_quote(row)
            if normalized["试算编号"] in seen:
                raise ValueError(f"第 {index} 行试算编号重复：{normalized['试算编号']}")
            seen.add(normalized["试算编号"])
            imported.append(normalized)
        if len(self.rows) + len(imported) > MAX_ROWS:
            raise ValueError("试算记录数量超过上限")
        if imported:
            self._commit(rows=self.rows + imported)
        return len(imported)

    def delete_quote(self, quote_id: str) -> None:
        candidate = [row for row in self.rows if row["试算编号"] != quote_id]
        if len(candidate) == len(self.rows):
            raise ValueError("找不到要删除的试算记录")
        self._commit(rows=candidate)

    def export_csv(self, path: Path) -> int:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=QUOTE_FIELDS)
        writer.writeheader()
        for row in self.rows:
            writer.writerow({field: _safe_text(row.get(field, "")) for field in QUOTE_FIELDS})
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
        return len(self.rows)

    def import_rate_csv(self, path: Path) -> int:
        raw = Path(path).read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("费率 CSV 文件超过 50 MB 限制")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 不是可识别的 UTF-8 或 GB18030 编码") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not RATE_REQUIRED.issubset(reader.fieldnames):
            raise ValueError("费率 CSV 必须包含规则编号、承运商、地区关键词、抛重系数、首重首费和续重单位续费")
        imported, seen = [], {rate["规则编号"] for rate in self.rates}
        for index, source in enumerate(reader, start=2):
            row = {field: _restore_safe_text(source.get(field, "")) for field in RATE_FIELDS}
            if not row["规则编号"]:
                row["规则编号"] = "FR-" + hashlib.sha256("|".join(row.get(field, "") for field in ("承运商", "目的地区关键词", "有效起始日期")).encode("utf-8")).hexdigest()[:12].upper()
            normalized = normalize_rate(row)
            if normalized["规则编号"] in seen:
                raise ValueError(f"第 {index} 行费率规则编号重复：{normalized['规则编号']}")
            seen.add(normalized["规则编号"])
            imported.append(normalized)
        if len(self.rates) + len(imported) > MAX_ROWS:
            raise ValueError("费率规则数量超过上限")
        if imported:
            self._commit(rates=self.rates + imported)
        return len(imported)

    def export_rate_csv(self, path: Path) -> int:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=RATE_FIELDS)
        writer.writeheader()
        for row in self.rates:
            writer.writerow({field: _safe_text(row.get(field, "")) for field in RATE_FIELDS})
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))
        return len(self.rates)

    def backup(self, path: Path) -> None:
        data = {"format": BACKUP_FORMAT, "version": VERSION, "rates": self.rates, "items": self.rows}
        payload = {**data, "sha256": hashlib.sha256(_canonical(data)).hexdigest()}
        _atomic_write(Path(path), _canonical(payload))

    def restore(self, path: Path) -> int:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取备份：{exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT or payload.get("version") != VERSION or not isinstance(payload.get("rates"), list) or not isinstance(payload.get("items"), list):
            raise ValueError("备份版本或结构不受支持")
        if len(payload["rates"]) > MAX_ROWS or len(payload["items"]) > MAX_ROWS:
            raise ValueError("备份记录数量超过上限")
        data = {"format": BACKUP_FORMAT, "version": VERSION, "rates": payload["rates"], "items": payload["items"]}
        if payload.get("sha256") != hashlib.sha256(_canonical(data)).hexdigest():
            raise ValueError("备份 SHA256 校验失败")
        if any(not isinstance(item, dict) for item in payload["rates"] + payload["items"]):
            raise ValueError("备份明细结构无效")
        rates = [normalize_rate(item) for item in payload["rates"]]
        rows = [normalize_quote(item) for item in payload["items"]]
        self._commit(rates=rates, rows=rows)
        return len(rows)


def default_data_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "MainlandBusinessTools" / "xianyu_freight_calculator.json"


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = FreightStore(root / "data.json")
        store.add_rate({
            "规则编号": "FR-SELF", "承运商": "中通快递", "目的地区关键词": "全国",
            "抛重系数(cm³/kg)": "6000", "首重(kg)": "1", "首费(元)": "8",
            "续重单位(kg)": "0.5", "续费(元)": "2", "附加费(元)": "0",
        })
        row = store.quote({
            "订单编号": "XY-SELF", "商品/SKU": "测试商品", "承运商": "中通快递",
            "目的地区": "广东省广州市", "实重(kg)": "2", "长(cm)": "40",
            "宽(cm)": "30", "高(cm)": "20",
        })
        assert row["体积重(kg)"] == "4"
        assert row["计费重量(kg)"] == "4"
        assert row["预估运费(元)"] == "20.00"
        store.update_actual(row["试算编号"], "22")
        assert store.rows[0]["运费差额(元)"] == "2.00"
        store.export_csv(root / "quotes.csv")
        store.backup(root / "backup.json")
        restored = FreightStore(root / "restored.json")
        assert restored.restore(root / "backup.json") == 1
        assert restored.rows == store.rows and restored.rates == store.rates
    print("SELF_TEST_OK", flush=True)
