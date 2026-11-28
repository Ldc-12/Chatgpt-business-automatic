"""Offline Xianyu pre-sale inspection ledger and printable condition report."""
from __future__ import annotations
import csv, hashlib, io, json, os, tempfile, uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape

PRODUCT = "闲鱼售前质检与成色报告助手"
FIELDS = ("记录编号","商品编号","商品名称","品类","品牌型号","成色等级","检测日期","检测人","外观检查","功能检测结论","功能检查记录","配件清单","瑕疵说明","维修/拆修历史","序列号尾号","建议售价","购入成本","内部备注")
IMPORT_REQUIRED = ("商品编号","商品名称","品类","检测日期")
GRADE_VALUES = ("全新未使用","99新","95新","9成新","8成新","7成新及以下","待检测")
FUNCTION_VALUES = ("全部通过","部分异常","未完成检测")
MONEY_FIELDS = ("建议售价","购入成本")
MAX_MONEY = Decimal("9999999999.99")
CENT = Decimal("0.01")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
TEXT_LIMITS = {"商品编号":60,"商品名称":120,"品类":40,"品牌型号":120,"检测人":60,"外观检查":2000,"功能检查记录":3000,"配件清单":2000,"瑕疵说明":3000,"维修/拆修历史":2000,"内部备注":2000}
MULTILINE_FIELDS = ("外观检查","功能检查记录","配件清单","瑕疵说明","维修/拆修历史","内部备注")


def default_data_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MainlandBusinessTools" / "xianyu_condition_report.json"


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


_FORMULA_PREFIXES = ("=", "+", "-", "@")
_FORMULA_LEADING_CONTROLS = "\t\r\n"


def _safe_text(value) -> str:
    text = "" if value is None else str(value)
    if text and (text[0] == "'" or text[0] in _FORMULA_LEADING_CONTROLS or text.lstrip().startswith(_FORMULA_PREFIXES)):
        return "'" + text
    return text


def _restore_safe_text(value) -> str:
    text = "" if value is None else str(value)
    if not text.startswith("'"): return text
    original = text[1:]
    if original.startswith("'") or (original and (original[0] in _FORMULA_LEADING_CONTROLS or original.lstrip().startswith(_FORMULA_PREFIXES))):
        return original
    return text


def _money(value, field: str) -> str:
    raw = "" if value is None else str(value).strip()
    if not raw: return ""
    raw = raw.replace("￥","").replace("¥","").replace(",","")
    try: amount = Decimal(raw)
    except (InvalidOperation, ValueError): raise ValueError(f"{field}必须是有效金额") from None
    if not amount.is_finite() or amount < 0 or amount > MAX_MONEY:
        raise ValueError(f"{field}必须在 0 至 {MAX_MONEY} 之间")
    return format(amount.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def _date_value(value, field: str, *, required: bool = False) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        if required: raise ValueError(f"{field}不能为空")
        return ""
    try: parsed = date.fromisoformat(text)
    except ValueError: raise ValueError(f"{field}必须使用 YYYY-MM-DD") from None
    if parsed.isoformat() != text: raise ValueError(f"{field}必须使用 YYYY-MM-DD")
    return text


def normalize_row(raw: dict) -> dict:
    if not isinstance(raw, dict): raise ValueError("质检记录必须是对象")
    row = {field: str(raw.get(field, "") or "").strip() for field in FIELDS}
    row["记录编号"] = row["记录编号"] or ("QC-" + uuid.uuid4().hex[:12].upper())
    for field in IMPORT_REQUIRED:
        if not row[field]: raise ValueError(f"{field}不能为空")
    row["检测日期"] = _date_value(row["检测日期"], "检测日期", required=True)
    row["成色等级"] = row["成色等级"] or "待检测"
    row["功能检测结论"] = row["功能检测结论"] or "未完成检测"
    if row["成色等级"] not in GRADE_VALUES: raise ValueError("成色等级必须是：" + "、".join(GRADE_VALUES))
    if row["功能检测结论"] not in FUNCTION_VALUES: raise ValueError("功能检测结论必须是：" + "、".join(FUNCTION_VALUES))
    serial_tail = row["序列号尾号"]
    if len(serial_tail) > 6 or (serial_tail and not serial_tail.isalnum()):
        raise ValueError("序列号尾号最多 6 位字母或数字；请勿录入完整序列号")
    for field, limit in TEXT_LIMITS.items():
        if len(row[field]) > limit: raise ValueError(f"{field}不能超过 {limit} 个字符")
    for field in MONEY_FIELDS: row[field] = _money(row[field], field)
    return row


def _validated_items(payload, label: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
        raise ValueError(f"{label}版本或结构不受支持")
    if any(not isinstance(row, dict) for row in payload["items"]): raise ValueError(f"{label}明细结构无效")
    return payload["items"]


def disclosure_text(row: dict) -> str:
    item = normalize_row(row)
    lines = [
        f"商品：{item['商品名称']}（编号：{item['商品编号']}）",
        f"品类/型号：{item['品类']} / {item['品牌型号'] or '未填写'}",
        f"成色等级：{item['成色等级']}；功能检测：{item['功能检测结论']}",
        f"检测日期：{item['检测日期']}",
        f"外观检查：{item['外观检查'] or '未填写'}",
        f"功能检查记录：{item['功能检查记录'] or '未填写'}",
        f"配件清单：{item['配件清单'] or '未填写'}",
        f"瑕疵说明：{item['瑕疵说明'] or '卖家未录入明显瑕疵；请以实物复核为准'}",
        f"维修/拆修历史：{item['维修/拆修历史'] or '未填写/未提供相关记录'}",
    ]
    if item["序列号尾号"]: lines.append(f"序列号尾号：{item['序列号尾号']}")
    lines.append("以上为卖家自行记录的检查信息，不构成专业鉴定、官方质检或无瑕疵保证；请买家以实物、现场测试及双方沟通为准。")
    return "\n".join(lines)


def generate_report_pdf(row: dict, path: Path) -> Path:
    item = normalize_row(row)
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".pdf", dir=str(target.parent)); os.close(fd)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        font_name = "STSong-Light"
        if font_name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(UnicodeCIDFont(font_name))
        title_style = ParagraphStyle("ConditionTitle", fontName=font_name, fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=12)
        body_style = ParagraphStyle("ConditionBody", fontName=font_name, fontSize=9, leading=14, wordWrap="CJK")
        label_style = ParagraphStyle("ConditionLabel", fontName=font_name, fontSize=9, leading=14, textColor=colors.HexColor("#333333"))
        note_style = ParagraphStyle("ConditionNote", fontName=font_name, fontSize=8, leading=12, textColor=colors.HexColor("#555555"))
        def paragraph(value, style=body_style):
            return Paragraph(escape(str(value or "未填写")).replace("\n", "<br/>"), style)
        story = [Paragraph(escape(PRODUCT) + "｜商品自检报告", title_style)]
        story += [paragraph("本报告用于整理卖家手工检查信息，方便上架前核对和向买家披露。", note_style), Spacer(1, 10)]
        fields = ("商品编号","商品名称","品类","品牌型号","成色等级","功能检测结论","检测日期","检测人","外观检查","功能检查记录","配件清单","瑕疵说明","维修/拆修历史","序列号尾号","建议售价","购入成本")
        data = [[paragraph("项目", label_style), paragraph("检查记录", label_style)]]
        for field in fields: data.append([paragraph(field, label_style), paragraph(item[field])])
        table = Table(data, colWidths=[105,390], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF0F6")),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#B8C2CC")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ]))
        heading = ParagraphStyle("DisclosureHeading", parent=body_style, fontSize=11, leading=16, spaceAfter=6)
        story.extend([table, Spacer(1,14), Paragraph("可复制的商品披露文案", heading), paragraph(disclosure_text(item)), Spacer(1,10)])
        story.append(paragraph("重要说明：本报告由卖家自行录入，不是第三方检测、品牌官方鉴定或法律结论。空白项目代表未填写，不代表检测通过；请在发布前核对每项内容。", note_style))
        SimpleDocTemplate(temporary, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=42, bottomMargin=42, title=PRODUCT).build(story)
        with open(temporary, "rb+") as stream:
            if stream.read(5) != b"%PDF-": raise ValueError("PDF 报告生成失败")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target); return target
    except Exception:
        Path(temporary).unlink(missing_ok=True); raise


class ConditionStore:
    def __init__(self, path: Path):
        self.path = Path(path); self.rows = self._load()
    @staticmethod
    def _validate_unique(rows):
        ids = [row["记录编号"] for row in rows]
        if len(ids) != len(set(ids)): raise ValueError("记录编号重复")
    def _load(self):
        if not self.path.exists(): return []
        try: payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError(f"无法读取质检台账：{exc}") from exc
        rows = [normalize_row(row) for row in _validated_items(payload, "数据文件")]
        self._validate_unique(rows); return rows
    def _commit(self, rows):
        candidate = [normalize_row(row) for row in rows]; self._validate_unique(candidate)
        _atomic_write(self.path, _canonical({"version":1,"items":candidate})); self.rows = candidate
    def add(self, raw):
        row = normalize_row(raw)
        if any(item["记录编号"] == row["记录编号"] for item in self.rows): raise ValueError("记录编号已存在")
        self._commit(self.rows + [row]); return row
    def update(self, record_id, raw):
        if not any(row["记录编号"] == record_id for row in self.rows): raise ValueError("找不到要编辑的质检记录")
        candidate=[]; updated=None
        for existing in self.rows:
            if existing["记录编号"] == record_id:
                updated=normalize_row({**raw,"记录编号":record_id}); candidate.append(updated)
            else: candidate.append(existing)
        self._commit(candidate); return updated
    def delete(self, record_id):
        candidate=[row for row in self.rows if row["记录编号"] != record_id]
        if len(candidate)==len(self.rows): raise ValueError("找不到要删除的质检记录")
        self._commit(candidate)
    def import_csv(self, path: Path) -> int:
        source_path=Path(path)
        try: size_bytes=source_path.stat().st_size
        except OSError as exc: raise ValueError(f"无法读取 CSV 文件：{exc}") from exc
        if size_bytes>MAX_IMPORT_BYTES: raise ValueError(f"CSV 文件超过 {MAX_IMPORT_BYTES // (1024*1024)} MB 限制")
        try:
            with source_path.open("rb") as stream: raw=stream.read(MAX_IMPORT_BYTES+1)
        except OSError as exc: raise ValueError(f"无法读取 CSV 文件：{exc}") from exc
        if len(raw)>MAX_IMPORT_BYTES: raise ValueError(f"CSV 文件超过 {MAX_IMPORT_BYTES // (1024*1024)} MB 限制")
        try: text=raw.decode("utf-8-sig")
        except UnicodeDecodeError: text=raw.decode("gb18030")
        reader=csv.DictReader(io.StringIO(text,newline="")); headers=reader.fieldnames or []
        if len(headers)!=len(set(headers)): raise ValueError("CSV 列名不能重复")
        if not set(IMPORT_REQUIRED).issubset(headers): raise ValueError("CSV 必须包含商品编号、商品名称、品类、检测日期四列")
        imported=[]; seen={row["记录编号"] for row in self.rows}
        for index, source in enumerate(reader,start=2):
            if None in source: raise ValueError(f"第 {index} 行列数超过表头")
            if not any(str(value or "").strip() for value in source.values()): continue
            row={field:_restore_safe_text(source.get(field,"")) for field in FIELDS}
            if not row["记录编号"]:
                identity="|".join(row.get(field,"") for field in ("商品编号","商品名称","品类","检测日期","瑕疵说明"))+f"|{index}"
                row["记录编号"]="QC-"+hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
            normalized=normalize_row(row)
            if normalized["记录编号"] in seen: raise ValueError(f"第 {index} 行记录编号重复：{normalized['记录编号']}")
            seen.add(normalized["记录编号"]); imported.append(normalized)
        if imported: self._commit(self.rows+imported)
        return len(imported)
    def export_csv(self, path: Path) -> int:
        buffer=io.StringIO(newline=""); writer=csv.DictWriter(buffer,fieldnames=FIELDS,extrasaction="ignore"); writer.writeheader()
        for row in self.rows: writer.writerow({field:_safe_text(row.get(field,"")) for field in FIELDS})
        _atomic_write(Path(path),buffer.getvalue().encode("utf-8-sig")); return len(self.rows)
    def backup(self, path: Path) -> None:
        data={"version":1,"items":self.rows}; payload={**data,"sha256":hashlib.sha256(_canonical(data)).hexdigest()}
        _atomic_write(Path(path),_canonical(payload))
    def restore(self, path: Path) -> int:
        try: payload=json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ValueError(f"无法读取备份：{exc}") from exc
        items=_validated_items(payload,"备份"); data={"version":1,"items":items}
        if payload.get("sha256")!=hashlib.sha256(_canonical(data)).hexdigest(): raise ValueError("备份 SHA256 校验失败")
        rows=[normalize_row(row) for row in items]; self._validate_unique(rows); self._commit(rows); return len(rows)


def self_test():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); store=ConditionStore(root/"data.json")
        row=store.add({"商品编号":"XY-QC-001","商品名称":"测试手机","品类":"手机","品牌型号":"测试型号","成色等级":"95新","检测日期":"2026-11-28","检测人":"卖家","功能检测结论":"全部通过","功能检查记录":"开机正常；充电正常","瑕疵说明":"边框有轻微划痕","序列号尾号":"A123","建议售价":"1200"})
        assert "边框有轻微划痕" in disclosure_text(row)
        csv_path=root/"records.csv"; assert store.export_csv(csv_path)==1
        imported=ConditionStore(root/"imported.json"); assert imported.import_csv(csv_path)==1
        backup=root/"backup.json"; store.backup(backup)
        restored=ConditionStore(root/"restored.json"); assert restored.restore(backup)==1
        pdf=generate_report_pdf(row,root/"report.pdf"); assert pdf.read_bytes().startswith(b"%PDF-")
    print("SELF_TEST_OK",flush=True)
