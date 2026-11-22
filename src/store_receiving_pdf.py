"""Generate local Chinese supplier reconciliation PDFs for the store receiving ledger."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from .store_receiving import atomic_write

MAX_PDF_ROWS = 50000
FONT_NAME = "STSong-Light"


def _register_cjk_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def _paragraph(value, style):
    from reportlab.platypus import Paragraph

    text = escape("" if value is None else str(value)).replace("\n", "<br/>")
    return Paragraph(text or " ", style)


def export_supplier_statement_pdf(store, path, supplier, start_date=None, end_date=None):
    """Export one supplier's inclusive-period receiving statement as an atomic PDF.

    The source ledger is read-only. The returned dictionary is the same supplier
    summary used by the CSV reports, so the PDF and CSV reporting totals agree.
    """
    supplier_name = str(supplier or "").strip()
    if not supplier_name:
        raise ValueError("必须选择供应商")
    if len(supplier_name) > 80 or any(ord(ch) < 32 for ch in supplier_name):
        raise ValueError("供应商名称长度或字符不符合要求")

    summaries = store.supplier_summary_rows(start_date, end_date)
    summary = next(
        (row for row in summaries if row["供应商"].casefold() == supplier_name.casefold()),
        None,
    )
    if summary is None:
        raise ValueError("该供应商在所选统计期间没有收货记录")

    start_text = summary["统计开始日期"]
    end_text = summary["统计结束日期"]
    start_day = date.fromisoformat(start_text) if start_text != "不限" else None
    end_day = date.fromisoformat(end_text) if end_text != "不限" else None
    details = []
    for row in store.report_rows():
        if row["供应商"].casefold() != supplier_name.casefold():
            continue
        arrival_day = date.fromisoformat(row["到货日期"])
        if start_day and arrival_day < start_day:
            continue
        if end_day and arrival_day > end_day:
            continue
        details.append(row)
    details.sort(
        key=lambda row: (
            row["到货日期"],
            row["收货单号"].casefold(),
            row["SKU"].casefold(),
            row["明细编号"].casefold(),
        )
    )
    if len(details) > MAX_PDF_ROWS:
        raise ValueError(f"单份 PDF 最多导出 {MAX_PDF_ROWS} 条收货明细，请缩小日期范围")
    if not details:
        raise ValueError("该供应商在所选统计期间没有收货明细")

    _register_cjk_font()
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    title_style = ParagraphStyle(
        "SupplierStatementTitle",
        fontName=FONT_NAME,
        fontSize=16,
        leading=21,
        alignment=TA_CENTER,
        spaceAfter=5,
    )
    meta_style = ParagraphStyle(
        "SupplierStatementMeta",
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "SupplierStatementSection",
        fontName=FONT_NAME,
        fontSize=10,
        leading=13,
        spaceBefore=5,
        spaceAfter=4,
    )
    summary_style = ParagraphStyle(
        "SupplierStatementSummary",
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
    )
    header_style = ParagraphStyle(
        "SupplierStatementTableHeader",
        fontName=FONT_NAME,
        fontSize=6.2,
        leading=7.4,
        alignment=TA_CENTER,
    )
    cell_style = ParagraphStyle(
        "SupplierStatementTableCell",
        fontName=FONT_NAME,
        fontSize=5.8,
        leading=7,
        alignment=TA_LEFT,
    )

    page_size = landscape(A4)
    left_margin = right_margin = 12 * mm
    available_width = page_size[0] - left_margin - right_margin
    column_widths = [15, 22, 18, 15, 24, 10, 10, 10, 9, 9, 9, 9, 15, 15, 16, 30]
    scale = min(1.0, available_width / (sum(column_widths) * mm))
    widths = [value * mm * scale for value in column_widths]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=12 * mm,
        bottomMargin=15 * mm,
        title=f"{summary['供应商']}收货对账单",
        author="门店收货验收与差异处理助手",
    )

    story = [
        Paragraph("供应商收货对账单", title_style),
        _paragraph(f"供应商：{summary['供应商']}", meta_style),
        _paragraph(
            f"统计期间：{start_text} 至 {end_text}（首尾日期均包含）　生成日期：{date.today().isoformat()}",
            meta_style,
        ),
        Spacer(1, 5),
        Paragraph("汇总信息", section_style),
    ]

    summary_cells = [
        ("收货单数", summary["收货单数"]),
        ("收货明细数", summary["收货明细数"]),
        ("差异明细数", summary["差异明细数"]),
        ("待处理差异", summary["待处理差异"]),
        ("验收金额", f"¥{summary['验收金额']}"),
        ("差异金额", f"¥{summary['差异金额']}"),
        ("待处理差异金额", f"¥{summary['待处理差异金额']}"),
    ]
    summary_data = []
    for index in range(0, len(summary_cells), 3):
        row = [
            _paragraph(f"{label}：{value}", summary_style)
            for label, value in summary_cells[index:index + 3]
        ]
        while len(row) < 3:
            row.append(Paragraph(" ", summary_style))
        summary_data.append(row)
    summary_table = Table(summary_data, colWidths=[available_width / 3] * 3)
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F5F8")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD3DC")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8DEE6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([summary_table, Spacer(1, 7), Paragraph("收货明细", section_style)])

    headers = [
        "到货日期", "收货单号", "采购单号", "SKU", "商品名称", "订购",
        "实收", "合格", "短缺", "超收", "破损", "拒收",
        "验收金额", "差异金额", "处理状态", "差异原因",
    ]
    table_data = [[_paragraph(label, header_style) for label in headers]]
    for row in details:
        values = [
            row["到货日期"], row["收货单号"], row["采购单号"], row["SKU"], row["商品名称"],
            row["订购数量"], row["实收数量"], row["验收合格数量"], row["短缺数量"],
            row["超收数量"], row["破损数量"], row["拒收数量"],
            f"¥{row['验收金额']}", f"¥{row['差异金额']}",
            row["差异处理"], row["差异原因"],
        ]
        table_data.append([_paragraph(value, cell_style) for value in values])

    detail_table = LongTable(
        table_data,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    detail_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF3")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B9C2CC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (5, 1), (13, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(detail_table)
    story.extend([
        Spacer(1, 6),
        _paragraph(
            "说明：本对账单仅根据本机人工录入的收货数据生成。验收金额、差异金额为管理核对参考，"
            "最终结算以双方确认的采购单据、退补货凭证、折让或退款凭证为准。",
            meta_style,
        ),
    ])

    def draw_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT_NAME, 7)
        canvas.drawRightString(
            page_size[0] - right_margin,
            7 * mm,
            f"第 {document.page} 页",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page_number, onLaterPages=draw_page_number)
    atomic_write(Path(path), buffer.getvalue())
    return dict(summary)
