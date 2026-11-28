import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
import src.xianyu_condition_report as condition_report
from src.xianyu_condition_report import FUNCTION_VALUES, GRADE_VALUES, ConditionStore, disclosure_text, generate_report_pdf, generate_batch_reports_zip, normalize_row


def sample(**overrides):
    row={"商品编号":"XY-QC-001","商品名称":"二手手机","品类":"手机","品牌型号":"测试型号","成色等级":"95新","检测日期":"2026-11-28","检测人":"卖家","外观检查":"屏幕无明显划痕","功能检测结论":"全部通过","功能检查记录":"开机、触控、充电正常","配件清单":"手机、数据线","瑕疵说明":"边框轻微掉漆","维修/拆修历史":"未填写","序列号尾号":"A123","建议售价":"1299","购入成本":"900","内部备注":"测试记录"}
    row.update(overrides); return row


def test_normalize_row_validates_enums_dates_money_and_serial_suffix():
    row=normalize_row(sample()); assert row["建议售价"]=="1299.00"; assert row["购入成本"]=="900.00"
    assert row["成色等级"] in GRADE_VALUES and row["功能检测结论"] in FUNCTION_VALUES
    with pytest.raises(ValueError,match="成色等级"): normalize_row(sample(成色等级="99.9新"))
    with pytest.raises(ValueError,match="功能检测结论"): normalize_row(sample(功能检测结论="绝对完美"))
    with pytest.raises(ValueError,match="序列号尾号"): normalize_row(sample(序列号尾号="FULLSERIAL123456"))
    with pytest.raises(ValueError,match="检测日期"): normalize_row(sample(检测日期="2026/11/28"))
    with pytest.raises(ValueError,match="建议售价"): normalize_row(sample(建议售价="NaN"))


def test_store_persists_add_update_delete_and_rejects_duplicate_ids(tmp_path):
    path=tmp_path/"data.json"; store=ConditionStore(path); row=store.add(sample(记录编号="QC-001"))
    assert ConditionStore(path).rows==[row]
    updated=store.update("QC-001",{**row,"瑕疵说明":"增加镜头边缘细纹"}); assert updated["瑕疵说明"]=="增加镜头边缘细纹"
    with pytest.raises(ValueError,match="记录编号已存在"): store.add(sample(记录编号="QC-001",商品编号="XY-QC-002"))
    store.delete("QC-001"); assert store.rows==[]


def test_csv_export_is_formula_safe_and_round_trips(tmp_path):
    store=ConditionStore(tmp_path/"data.json"); store.add(sample(瑕疵说明='  =HYPERLINK("https://bad.invalid")'))
    csv_path=tmp_path/"records.csv"; assert store.export_csv(csv_path)==1
    raw=csv_path.read_text(encoding="utf-8-sig"); assert "'=HYPERLINK" in raw
    imported=ConditionStore(tmp_path/"imported.json"); assert imported.import_csv(csv_path)==1
    assert imported.rows[0]["瑕疵说明"]=='=HYPERLINK("https://bad.invalid")'


def test_import_accepts_gb18030_and_generates_stable_ids(tmp_path):
    source=tmp_path/"gb.csv"; source.write_bytes(("商品编号,商品名称,品类,检测日期,瑕疵说明\nXY-2,二手相机,相机,2026-11-28,镜头轻微灰尘\n").encode("gb18030"))
    store=ConditionStore(tmp_path/"data.json"); assert store.import_csv(source)==1
    assert store.rows[0]["商品名称"]=="二手相机" and store.rows[0]["记录编号"].startswith("QC-")


def test_import_is_all_or_nothing_and_rejects_duplicate_headers(tmp_path):
    store=ConditionStore(tmp_path/"data.json"); source=tmp_path/"bad.csv"
    source.write_text("商品编号,商品名称,品类,检测日期,成色等级\nXY-1,手机,手机,2026-11-28,95新\nXY-2,电脑,电脑,not-a-date,95新\n",encoding="utf-8")
    with pytest.raises(ValueError,match="检测日期"): store.import_csv(source)
    assert store.rows==[]
    source.write_text("商品编号,商品名称,品类,检测日期,检测日期\n",encoding="utf-8")
    with pytest.raises(ValueError,match="列名不能重复"): store.import_csv(source)


def test_import_rejects_oversized_file_before_open(tmp_path,monkeypatch):
    import src.xianyu_condition_report as module
    source=tmp_path/"oversized.csv"; source.write_bytes(b"x")
    monkeypatch.setattr(module,"MAX_IMPORT_BYTES",0)
    monkeypatch.setattr(Path,"open",lambda *_a,**_k: (_ for _ in ()).throw(AssertionError("must not open")))
    store=ConditionStore(tmp_path/"data.json")
    with pytest.raises(ValueError,match="超过 0 MB"): store.import_csv(source)


def test_backup_restore_integrity_and_tamper_rejection(tmp_path):
    store=ConditionStore(tmp_path/"data.json"); store.add(sample()); backup=tmp_path/"backup.json"; store.backup(backup)
    restored=ConditionStore(tmp_path/"restored.json"); assert restored.restore(backup)==1 and restored.rows==store.rows
    payload=json.loads(backup.read_text(encoding="utf-8")); payload["items"][0]["瑕疵说明"]="tampered"
    backup.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8"); before=list(restored.rows)
    with pytest.raises(ValueError,match="SHA256"): restored.restore(backup)
    assert restored.rows==before


def test_disclosure_text_does_not_claim_professional_certification():
    text=disclosure_text(sample()); assert "边框轻微掉漆" in text
    assert "不构成专业鉴定" in text and "序列号尾号：A123" in text


def test_pdf_report_is_valid_and_escapes_user_markup(tmp_path):
    target=generate_report_pdf(sample(瑕疵说明="边框 <script>alert('x')</script> 轻微掉漆"),tmp_path/"report.pdf")
    data=target.read_bytes(); assert data.startswith(b"%PDF-") and len(data)>1500
    from pypdf import PdfReader
    reader=PdfReader(str(target)); assert len(reader.pages)==1
    text=reader.pages[0].extract_text() or ""
    assert "商品自检报告" in text and "不构成专业鉴定" in text
    assert "购入成本" not in text and "900.00" not in text
    assert "建议售价" not in text and "1299.00" not in text
    assert "内部备注" not in text and "测试记录" not in text


def test_pdf_failure_does_not_replace_existing_target(tmp_path,monkeypatch):
    import reportlab.platypus
    target=tmp_path/"existing.pdf"; target.write_bytes(b"old-pdf")
    original=reportlab.platypus.SimpleDocTemplate.build
    def fail(*_args,**_kwargs): raise RuntimeError("render failed")
    monkeypatch.setattr(reportlab.platypus.SimpleDocTemplate,"build",fail)
    with pytest.raises(RuntimeError,match="render failed"): generate_report_pdf(sample(),target)
    assert target.read_bytes()==b"old-pdf"
    monkeypatch.setattr(reportlab.platypus.SimpleDocTemplate,"build",original)



def test_batch_report_zip_contains_safe_index_and_sha256_manifest(tmp_path):
    rows = [
        sample(记录编号="../QC/001", 商品编号="XY:001", 商品名称='=HYPERLINK("x")', 内部备注="PRIVATE_NOTE"),
        sample(记录编号="QC-002", 商品编号="XY-002", 商品名称="二手相机", 建议售价="1888", 购入成本="1200"),
    ]
    target = generate_batch_reports_zip(rows, tmp_path / "batch.zip")
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        pdf_names = [name for name in names if name.endswith(".pdf")]
        assert len(pdf_names) == 2
        assert all("/" not in name and "\\\\" not in name and ".." not in name for name in pdf_names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_count"] == 2
        assert len(manifest["reports"]) == 2
        for report in manifest["reports"]:
            data = archive.read(report["file"])
            assert len(data) == report["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == report["sha256"]
            from pypdf import PdfReader
            text = PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""
            assert "购入成本" not in text and "建议售价" not in text and "内部备注" not in text
            assert "PRIVATE_NOTE" not in text and "1299.00" not in text
        index = archive.read("报告索引.csv").decode("utf-8-sig")
        assert "'=HYPERLINK" in index
        assert "PRIVATE_NOTE" not in index and "900.00" not in index and "1299.00" not in index
        assert "报告索引不包含建议售价" in archive.read("使用说明.txt").decode("utf-8")


def test_batch_report_zip_rejects_empty_and_duplicate_ids_without_replacing_target(tmp_path):
    target = tmp_path / "existing.zip"
    target.write_bytes(b"existing-package")
    with pytest.raises(ValueError, match="至少选择"):
        generate_batch_reports_zip([], target)
    assert target.read_bytes() == b"existing-package"
    with pytest.raises(ValueError, match="记录编号重复"):
        generate_batch_reports_zip([sample(记录编号="QC-1"), sample(记录编号="QC-1", 商品编号="XY-2")], target)
    assert target.read_bytes() == b"existing-package"


def test_batch_report_zip_failure_preserves_existing_target_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "existing.zip"
    target.write_bytes(b"existing-package")
    original = condition_report.generate_report_pdf
    calls = 0
    def fail_second(row, path):
        nonlocal calls
        calls += 1
        if calls == 2: raise RuntimeError("second report failed")
        return original(row, path)
    monkeypatch.setattr(condition_report, "generate_report_pdf", fail_second)
    with pytest.raises(RuntimeError, match="second report failed"):
        condition_report.generate_batch_reports_zip([sample(记录编号="QC-1"), sample(记录编号="QC-2", 商品编号="XY-2")], target)
    assert target.read_bytes() == b"existing-package"
    assert not list(tmp_path.glob(".existing.*.zip"))


def test_self_test():
    from src.xianyu_condition_report import self_test
    self_test()
