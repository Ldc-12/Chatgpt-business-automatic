"""Offline renovation material takeoff, waste planning and budget ledger."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import os
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

FORMAT = "mainland-renovation-materials"
BACKUP_FORMAT = "mainland-renovation-materials-backup"
VERSION = 1
CATEGORIES = ("地面", "墙面", "顶面", "水电", "门窗", "辅材", "其他")
UNITS = ("m²", "m", "kg", "L", "个", "套", "箱", "包", "卷")
FIELDS = (
    "记录编号", "项目编号", "项目名称", "房间/区域", "材料编码", "材料名称",
    "材料类别", "计量单位", "净用量", "损耗率(%)", "包装规格",
    "单价(元/单位)", "供应商", "实际采购量", "实际金额(元)", "备注",
)
TEXT_FIELDS = {
    "记录编号", "项目编号", "项目名称", "房间/区域", "材料编码",
    "材料名称", "材料类别", "计量单位", "供应商", "备注",
}
QUANTITY_FIELDS = ("净用量", "包装规格", "实际采购量")
MONEY_FIELDS = ("单价(元/单位)", "实际金额(元)")


def _decimal(value, label: str, allow_blank: bool = False) -> Decimal | None:
    raw = str(value if value is not None else "").strip().replace(",", "").replace("，", "")
    if not raw:
        if allow_blank:
            return None
        raise ValueError(f"{label}不能为空")
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not result.is_finite():
        raise ValueError(f"{label}不能是 NaN 或无穷大")
    return result


def _quantize(value: Decimal, places: str) -> str:
    return format(value.quantize(Decimal(places), rounding=ROUND_HALF_UP), "f")


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def normalize_material_row(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("材料记录必须是对象")
    result = {field: str("" if row.get(field) is None else row.get(field, "")).strip() for field in FIELDS}
    required = (
        "记录编号", "项目编号", "项目名称", "房间/区域", "材料编码",
        "材料名称", "材料类别", "计量单位",
    )
    for field in required:
        if not result[field]:
            raise ValueError(f"{field}不能为空")
        if len(result[field]) > 120:
            raise ValueError(f"{field}长度不能超过 120 个字符")
    if result["材料类别"] not in CATEGORIES:
        raise ValueError("材料类别不在内置分类中")
    if result["计量单位"] not in UNITS:
        raise ValueError("计量单位不在支持列表中")

    net = _decimal(result["净用量"], "净用量")
    waste = _decimal(result["损耗率(%)"], "损耗率")
    pack = _decimal(result["包装规格"], "包装规格")
    price = _decimal(result["单价(元/单位)"], "单价")
    actual_qty = _decimal(result["实际采购量"], "实际采购量", allow_blank=True)
    actual_amount = _decimal(result["实际金额(元)"], "实际金额", allow_blank=True)
    if net <= 0:
        raise ValueError("净用量必须大于 0")
    if waste < 0 or waste > 100:
        raise ValueError("损耗率必须在 0–100% 之间")
    if pack <= 0:
        raise ValueError("包装规格必须大于 0")
    if price < 0:
        raise ValueError("单价不能为负数")
    if actual_qty is not None and actual_qty < 0:
        raise ValueError("实际采购量不能为负数")
    if actual_amount is not None and actual_amount < 0:
        raise ValueError("实际金额不能为负数")

    result["净用量"] = _quantize(net, "0.001")
    result["损耗率(%)"] = _quantize(waste, "0.01")
    result["包装规格"] = _quantize(pack, "0.001")
    result["单价(元/单位)"] = _quantize(price, "0.01")
    result["实际采购量"] = "" if actual_qty is None else _quantize(actual_qty, "0.001")
    result["实际金额(元)"] = "" if actual_amount is None else _quantize(actual_amount, "0.01")
    if len(result["备注"]) > 2000:
        raise ValueError("备注不能超过 2000 个字符")
    return result


def calculate_material(row: dict) -> dict:
    item = normalize_material_row(row)
    net = Decimal(item["净用量"])
    waste = Decimal(item["损耗率(%)"])
    pack = Decimal(item["包装规格"])
    price = Decimal(item["单价(元/单位)"])
    planned = net * (Decimal("1") + waste / Decimal("100"))
    packs = _ceil_decimal(planned / pack)
    purchase = pack * packs
    budget = (purchase * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    actual_amount = Decimal(item["实际金额(元)"]) if item["实际金额(元)"] else None
    variance = None if actual_amount is None else (
        actual_amount - budget
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "净用量": _quantize(net, "0.001"),
        "计划用量(含损耗)": _quantize(planned, "0.001"),
        "建议采购包装数": packs,
        "建议采购量": _quantize(purchase, "0.001"),
        "预算金额(元)": _quantize(budget, "0.01"),
        "实际采购量": item["实际采购量"],
        "实际金额(元)": item["实际金额(元)"],
        "实际与预算差额(元)": "" if variance is None else _quantize(variance, "0.01"),
    }


def calculate_tile_quantity(
    room_area_m2, tile_length_mm, tile_width_mm, waste_pct=8, tiles_per_box=4
) -> dict:
    area = _decimal(room_area_m2, "铺贴面积")
    length = _decimal(tile_length_mm, "瓷砖长度")
    width = _decimal(tile_width_mm, "瓷砖宽度")
    waste = _decimal(waste_pct, "损耗率")
    per_box = _decimal(tiles_per_box, "每箱片数")
    if area <= 0 or length <= 0 or width <= 0:
        raise ValueError("面积和瓷砖长宽必须大于 0")
    if waste < 0 or waste > 100:
        raise ValueError("损耗率必须在 0–100% 之间")
    if per_box <= 0 or per_box != per_box.to_integral_value():
        raise ValueError("每箱片数必须是正整数")
    tile_area = length * width / Decimal("1000000")
    required = _ceil_decimal(area * (Decimal("1") + waste / Decimal("100")) / tile_area)
    boxes = math.ceil(required / int(per_box))
    purchased = boxes * int(per_box)
    purchased_area = tile_area * purchased
    return {
        "单片面积(m²)": _quantize(tile_area, "0.000001"),
        "理论所需片数": required,
        "建议整箱数": boxes,
        "建议采购片数": purchased,
        "采购覆盖面积(m²)": _quantize(purchased_area, "0.001"),
    }


def calculate_paint_liters(area_m2, coats, coverage_m2_per_liter, waste_pct=10) -> str:
    area = _decimal(area_m2, "涂刷面积")
    coverage = _decimal(coverage_m2_per_liter, "每升理论涂刷面积")
    waste = _decimal(waste_pct, "损耗率")
    try:
        coat_count = int(str(coats).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("涂刷遍数必须是 1–10 的整数") from exc
    if area <= 0 or coverage <= 0:
        raise ValueError("面积和涂布率必须大于 0")
    if coat_count < 1 or coat_count > 10:
        raise ValueError("涂刷遍数必须是 1–10 的整数")
    if waste < 0 or waste > 100:
        raise ValueError("损耗率必须在 0–100% 之间")
    liters = area * coat_count / coverage * (Decimal("1") + waste / Decimal("100"))
    rounded_tenths = (liters * 10).to_integral_value(rounding=ROUND_CEILING) / Decimal("10")
    return _quantize(rounded_tenths, "0.1")


def project_summary(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        item = normalize_material_row(row)
        calc = calculate_material(item)
        key = item["项目编号"]
        bucket = grouped.setdefault(key, {
            "项目编号": key,
            "项目名称": item["项目名称"],
            "材料行数": 0,
            "预算金额(元)": Decimal("0"),
            "实际金额(元)": Decimal("0"),
            "已录入实际金额行数": 0,
        })
        if bucket["项目名称"] != item["项目名称"]:
            raise ValueError(f"项目编号 {key} 对应多个项目名称")
        bucket["材料行数"] += 1
        bucket["预算金额(元)"] += Decimal(calc["预算金额(元)"])
        if calc["实际金额(元)"]:
            bucket["实际金额(元)"] += Decimal(calc["实际金额(元)"])
            bucket["已录入实际金额行数"] += 1
    return {
        key: {
            **value,
            "预算金额(元)": _quantize(value["预算金额(元)"], "0.01"),
            "实际金额(元)": _quantize(value["实际金额(元)"], "0.01"),
            "实际与预算差额(元)": _quantize(
                value["实际金额(元)"] - value["预算金额(元)"], "0.01"
            ),
        }
        for key, value in grouped.items()
    }


def _safe_csv_text(value) -> str:
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class MaterialStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    @staticmethod
    def validate_rows(rows):
        ids = [row["记录编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("记录编号重复")
        project_names = {}
        for row in rows:
            previous = project_names.setdefault(row["项目编号"], row["项目名称"])
            if previous != row["项目名称"]:
                raise ValueError(f"项目编号 {row['项目编号']} 对应多个项目名称")

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("materials"), list)
            ):
                raise ValueError("材料台账数据格式或版本不受支持")
            rows = [normalize_material_row(item) for item in payload["materials"]]
            self.validate_rows(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"材料台账无法读取，原文件未修改：{exc}") from exc

    def save(self, rows=None):
        items = self.rows if rows is None else rows
        normalized = [normalize_material_row(row) for row in items]
        self.validate_rows(normalized)
        payload = {
            "format": FORMAT,
            "version": VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "materials": normalized,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        _atomic_write(self.path, data)

    def add(self, row):
        item = normalize_material_row(row)
        if any(old["记录编号"] == item["记录编号"] for old in self.rows):
            raise ValueError("记录编号已存在")
        updated = self.rows + [item]
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def update(self, record_id, row):
        item = normalize_material_row(row)
        if item["记录编号"] != record_id:
            raise ValueError("记录编号不能修改")
        index = next((i for i, old in enumerate(self.rows) if old["记录编号"] == record_id), None)
        if index is None:
            raise ValueError("找不到要编辑的材料记录")
        updated = list(self.rows)
        updated[index] = item
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated

    def delete(self, record_id):
        updated = [row for row in self.rows if row["记录编号"] != record_id]
        if len(updated) == len(self.rows):
            raise ValueError("找不到要删除的材料记录")
        self.save(updated)
        self.rows = updated

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(FIELDS):
                raise ValueError("CSV 表头必须与软件导出的字段和顺序完全一致")
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余字段")
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_material_row(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
                if len(incoming) > 100000:
                    raise ValueError("单次最多导入 100000 条材料记录")
        self.validate_rows(incoming)
        existing_ids = {row["记录编号"] for row in self.rows}
        duplicates = existing_ids.intersection(row["记录编号"] for row in incoming)
        if duplicates:
            raise ValueError("导入包含已存在记录编号，整批未导入：" + "、".join(sorted(duplicates)))
        updated = self.rows + incoming
        self.validate_rows(updated)
        self.save(updated)
        self.rows = updated
        return len(incoming)

    def export_csv(self, path):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({
                field: _safe_csv_text(row[field]) if field in TEXT_FIELDS else row[field]
                for field in FIELDS
            })
        _atomic_write(Path(path), buffer.getvalue().encode("utf-8-sig"))

    def backup(self, path):
        materials = [dict(row) for row in self.rows]
        canonical = json.dumps(
            materials, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload = {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "materials": materials,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        _atomic_write(Path(path), data)

    def restore(self, path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != VERSION
                or not isinstance(payload.get("materials"), list)
                or not isinstance(payload.get("sha256"), str)
            ):
                raise ValueError("备份文件格式或版本不受支持")
            canonical = json.dumps(
                payload["materials"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            actual = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(actual, payload["sha256"]):
                raise ValueError("备份 SHA256 校验失败，当前数据未修改")
            rows = [normalize_material_row(item) for item in payload["materials"]]
            self.validate_rows(rows)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"恢复失败，当前数据未修改：{exc}") from exc
        self.save(rows)
        self.rows = rows


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "renovation_materials.json"


def self_test():
    import tempfile

    sample = {
        "记录编号": "RM-TEST-001", "项目编号": "P-TEST", "项目名称": "测试装修项目",
        "房间/区域": "客厅", "材料编码": "TILE-600", "材料名称": "600×600 地砖",
        "材料类别": "地面", "计量单位": "m²", "净用量": "10",
        "损耗率(%)": "8", "包装规格": "1", "单价(元/单位)": "38",
        "供应商": "测试供应商", "实际采购量": "", "实际金额(元)": "", "备注": "",
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = MaterialStore(root / "materials.json")
        store.add(sample)
        assert calculate_material(sample)["预算金额(元)"] == "418.00"
        assert calculate_tile_quantity("10", "600", "600", 8, 4)["建议整箱数"] == 8
        assert calculate_paint_liters("50", 2, "10", 10) == "11.0"
        csv_path = root / "materials.csv"
        store.export_csv(csv_path)
        imported = MaterialStore(root / "imported.json")
        assert imported.import_csv(csv_path) == 1
        backup = root / "materials-backup.json"
        store.backup(backup)
        restored = MaterialStore(root / "restored.json")
        restored.restore(backup)
        assert restored.rows == store.rows
    if __import__("sys").stdout is not None:
        print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    self_test()
