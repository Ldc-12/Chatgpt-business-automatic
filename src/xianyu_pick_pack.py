"""Offline order picking and packing ledger for Xianyu sellers."""
from __future__ import annotations
import csv, hashlib, io, json, os, tempfile, uuid
from datetime import date
from pathlib import Path

PRODUCT = "闲鱼订单拣货与打包清单助手"
FIELDS = ("明细编号", "订单编号", "商品名称", "SKU", "规格/成色", "数量", "已拣数量", "已打包数量", "包裹编号", "订单日期", "买家备注", "内部备注")
IMPORT_REQUIRED = ("订单编号", "商品名称", "数量")


def default_data_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MainlandBusinessTools" / "xianyu_pick_pack.json"


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


def _safe_text(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "'")) else text


def _restore_safe_text(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith("''"):
        return text[1:]
    if len(text) > 1 and text[0] == "'" and text[1] in "=+-@":
        return text[1:]
    return text


def _integer(value, field: str, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是整数") from None
    if not minimum <= number <= maximum:
        raise ValueError(f"{field}必须在 {minimum}–{maximum} 之间")
    return number


def normalize_row(raw: dict) -> dict:
    row = {field: str(raw.get(field, "") or "").strip() for field in FIELDS}
    row["明细编号"] = row["明细编号"] or ("PP-" + uuid.uuid4().hex[:12].upper())
    for field in ("订单编号", "商品名称"):
        if not row[field]:
            raise ValueError(f"{field}不能为空")
    row["数量"] = _integer(row["数量"], "数量", 1, 100000)
    row["已拣数量"] = _integer(row["已拣数量"] or 0, "已拣数量", 0, 100000)
    row["已打包数量"] = _integer(row["已打包数量"] or 0, "已打包数量", 0, 100000)
    if row["已拣数量"] > row["数量"]:
        raise ValueError("已拣数量不能超过订单数量")
    if row["已打包数量"] > row["已拣数量"]:
        raise ValueError("已打包数量不能超过已拣数量")
    if row["订单日期"]:
        try:
            date.fromisoformat(row["订单日期"])
        except ValueError:
            raise ValueError("订单日期必须使用 YYYY-MM-DD") from None
    return row


def line_status(row: dict) -> str:
    qty, picked, packed = int(row["数量"]), int(row["已拣数量"]), int(row["已打包数量"])
    if packed == qty:
        return "已打包"
    if packed:
        return "打包中"
    if picked == qty:
        return "已拣货"
    if picked:
        return "拣货中"
    return "待拣货"


def picking_summary(rows: list[dict]) -> list[dict]:
    groups = {}
    for row in rows:
        sku = row["SKU"] or row["商品名称"]
        key = (sku.casefold(), row["规格/成色"].casefold())
        item = groups.setdefault(key, {"SKU/商品": sku, "规格/成色": row["规格/成色"], "_names": set(), "_orders": set(), "需求数量": 0, "已拣数量": 0, "已打包数量": 0})
        item["_names"].add(row["商品名称"])
        item["_orders"].add(row["订单编号"])
        item["需求数量"] += int(row["数量"])
        item["已拣数量"] += int(row["已拣数量"])
        item["已打包数量"] += int(row["已打包数量"])
    result = []
    for item in groups.values():
        item["商品名称"] = " / ".join(sorted(item.pop("_names")))
        item["订单数"] = len(item.pop("_orders"))
        item["待拣数量"] = item["需求数量"] - item["已拣数量"]
        item["待打包数量"] = item["需求数量"] - item["已打包数量"]
        result.append(item)
    return sorted(result, key=lambda x: (x["SKU/商品"].casefold(), x["规格/成色"].casefold()))


def packing_progress(rows: list[dict]) -> dict:
    return {
        "明细行数": len(rows),
        "订单数": len({row["订单编号"] for row in rows}),
        "需求数量": sum(int(row["数量"]) for row in rows),
        "已拣数量": sum(int(row["已拣数量"]) for row in rows),
        "已打包数量": sum(int(row["已打包数量"]) for row in rows),
        "待拣数量": sum(int(row["数量"]) - int(row["已拣数量"]) for row in rows),
        "待打包数量": sum(int(row["数量"]) - int(row["已打包数量"]) for row in rows),
    }


def _validated_items(payload, label: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
        raise ValueError(f"{label}版本或结构不受支持")
    if any(not isinstance(row, dict) for row in payload["items"]):
        raise ValueError(f"{label}明细结构无效")
    return payload["items"]


class PickPackStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.rows = self._load()

    @staticmethod
    def _validate_unique(rows):
        ids = [row["明细编号"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("明细编号重复")

    def _load(self):
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            items = _validated_items(payload, "数据文件")
            rows = [normalize_row(row) for row in items]
            self._validate_unique(rows)
            return rows
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取拣货台账：{exc}") from exc

    def _commit(self, rows):
        candidate = [normalize_row(row) for row in rows]
        self._validate_unique(candidate)
        _atomic_write(self.path, _canonical({"version": 1, "items": candidate}))
        self.rows = candidate

    def add(self, raw):
        row = normalize_row(raw)
        if any(item["明细编号"] == row["明细编号"] for item in self.rows):
            raise ValueError("明细编号已存在")
        self._commit(self.rows + [row])
        return row

    def update(self, line_id, raw):
        if not any(row["明细编号"] == line_id for row in self.rows):
            raise ValueError("找不到要编辑的明细")
        candidate, updated = [], None
        for existing in self.rows:
            if existing["明细编号"] == line_id:
                updated = normalize_row({**raw, "明细编号": line_id})
                candidate.append(updated)
            else:
                candidate.append(existing)
        self._commit(candidate)
        return updated

    def delete(self, line_id):
        candidate = [row for row in self.rows if row["明细编号"] != line_id]
        if len(candidate) == len(self.rows):
            raise ValueError("找不到要删除的明细")
        self._commit(candidate)

    def import_csv(self, path: Path) -> int:
        raw = Path(path).read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("gb18030")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not set(IMPORT_REQUIRED).issubset(reader.fieldnames):
            raise ValueError("CSV 必须包含订单编号、商品名称、数量三列")
        imported, seen = [], {row["明细编号"] for row in self.rows}
        for index, source in enumerate(reader, start=2):
            row = {field: _restore_safe_text(source.get(field, "")) for field in FIELDS}
            if not row["明细编号"]:
                identity = "|".join(row.get(f, "") for f in ("订单编号", "商品名称", "SKU", "规格/成色")) + f"|{index}"
                row["明细编号"] = "PP-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
            normalized = normalize_row(row)
            if normalized["明细编号"] in seen:
                raise ValueError(f"第 {index} 行明细编号重复：{normalized['明细编号']}")
            seen.add(normalized["明细编号"])
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

    def export_picking_list_csv(self, path):
        fields = ("SKU/商品", "商品名称", "规格/成色", "订单数", "需求数量", "已拣数量", "待拣数量", "已打包数量", "待打包数量")
        return self._export_rows(path, fields, picking_summary(self.rows))

    def export_packing_list_csv(self, path):
        fields = FIELDS + ("处理状态",)
        rows = [{**row, "处理状态": line_status(row)} for row in self.rows]
        return self._export_rows(path, fields, rows)

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
        store = PickPackStore(root / "data.json")
        store.add({"订单编号": "XY-TEST-001", "商品名称": "测试商品", "SKU": "SKU-1", "规格/成色": "黑色", "数量": 2, "已拣数量": 1})
        assert packing_progress(store.rows)["待拣数量"] == 1
        assert picking_summary(store.rows)[0]["待拣数量"] == 1
        store.export_csv(root / "export.csv")
        store.backup(root / "backup.json")
        restored = PickPackStore(root / "restored.json")
        assert restored.restore(root / "backup.json") == 1
        assert restored.rows == store.rows
    print("SELF_TEST_OK", flush=True)
