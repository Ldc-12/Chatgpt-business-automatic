import csv
import json
from pathlib import Path

from src import construction_project as module


def project(pid="P001"):
    return {
        "项目编号": pid, "项目名称": "办公室翻新", "甲方/客户": "甲方",
        "施工方/乙方": "施工方", "合同金额(元)": "100000",
        "开工日期": "2026-01-01", "合同竣工日期": "2026-12-31",
        "进度款支付比例(%)": "90", "质保金比例(%)": "5",
        "状态": "施工中", "备注": "",
    }


def change(vid="V001", pid="P001", **overrides):
    row = {
        "签证编号": vid, "项目编号": pid, "发生日期": "2026-06-01",
        "变更类型": "增项", "项目/工序": "墙面修补", "计量方式": "面积×单价",
        "数量": "1", "长度(m)": "10", "宽度(m)": "2", "高度(m)": "0",
        "单位": "平方米", "综合单价(元)": "50", "状态": "待签认",
        "签认日期": "", "证据文件": "", "备注": "",
    }
    row.update(overrides)
    return row


def claim(cid="P001-01", pid="P001", **overrides):
    row = {
        "期次编号": cid, "项目编号": pid, "申报日期": "2026-06-30",
        "累计完成产值(元)": "50000", "累计已付款(元)": "0",
        "本期预付款抵扣(元)": "2000", "本期其他扣款(元)": "0",
        "状态": "已申报", "付款日期": "", "备注": "",
    }
    row.update(overrides)
    return row


def test_measurement_formulas_and_change_signs():
    area = change(计量方式="面积×单价", 数量="2", **{"长度(m)": "3", "宽度(m)": "4"})
    assert module.calculate_change_amount(area) == "1200.00"
    volume = change(计量方式="体积×单价", 数量="2",
                    **{"长度(m)": "3", "宽度(m)": "4", "高度(m)": "5"})
    assert module.calculate_change_amount(volume) == "6000.00"
    fixed = change(计量方式="固定金额", **{"综合单价(元)": "99.995"})
    assert module.calculate_change_amount(fixed) == "100.00"
    reduction = change(变更类型="减项")
    assert module.calculate_change_amount(reduction) == "-1000.00"
    extension = change(变更类型="工期签证", **{"综合单价(元)": "0"})
    assert module.calculate_change_amount(extension) == "0.00"
    bad = change(计量方式="面积×单价", **{"宽度(m)": "0"})
    try:
        module.calculate_change_amount(bad)
    except ValueError as exc:
        assert "宽度" in str(exc)
    else:
        raise AssertionError("zero-width area calculation accepted")


def test_project_dates_percentages_and_contract_rules():
    item = module.normalize_project(project())
    assert item["合同金额(元)"] == "100000.00"
    bad = project()
    bad["合同竣工日期"] = "2025-12-31"
    try:
        module.normalize_project(bad)
    except ValueError as exc:
        assert "竣工日期" in str(exc)
    else:
        raise AssertionError("end date before start accepted")
    bad = project()
    bad["质保金比例(%)"] = "95"
    try:
        module.normalize_project(bad)
    except ValueError as exc:
        assert "不能高于" in str(exc)
    else:
        raise AssertionError("retention above payment ratio accepted")


def test_store_project_variation_claim_and_summary_roundtrip(tmp_path):
    path = tmp_path / "construction.json"
    store = module.ConstructionStore(path)
    store.add_project(project())
    evidence = tmp_path / "signed-order.txt"
    evidence.write_text("双方签认", encoding="utf-8")
    store.add_change(change(
        状态="已签认", 签认日期="2026-06-02", 证据文件=str(evidence)
    ))
    assert store.changes[0]["金额(元)"] == "1000.00"
    assert len(store.changes[0]["证据SHA256"]) == 64
    store.add_claim(claim())
    assert store.claims[0]["本期应付金额(元)"] == "40500.00"
    summary = store.project_summary("P001")
    assert summary["已签认变更净额(元)"] == "1000.00"
    assert summary["调整后合同额(元)"] == "101000.00"
    loaded = module.ConstructionStore(path)
    assert loaded.projects == store.projects
    assert loaded.changes == store.changes
    assert loaded.claims == store.claims
    assert loaded.audit == store.audit


def test_changed_evidence_is_reported_without_blocking_data_load(tmp_path):
    path = tmp_path / "construction.json"
    evidence = tmp_path / "photo.txt"
    evidence.write_text("original", encoding="utf-8")
    store = module.ConstructionStore(path)
    store.add_project(project())
    store.add_change(change(
        状态="已签认", 签认日期="2026-06-02", 证据文件=str(evidence)
    ))
    evidence.write_text("changed", encoding="utf-8")
    loaded = module.ConstructionStore(path)
    findings = loaded.risk_findings("2026-07-01")
    assert "EVIDENCE_MISSING_OR_CHANGED" in {item["规则编号"] for item in findings}


def test_risk_engine_flags_missing_evidence_outside_term_pending_and_overpayment(tmp_path):
    store = module.ConstructionStore(tmp_path / "construction.json")
    store.add_project(project())
    store.add_change(change(
        "V-SIGNED", 状态="已签认", 签认日期="2025-12-20",
        **{"发生日期": "2025-12-15"}
    ))
    store.add_change(change(
        "V-PENDING", **{"发生日期": "2026-01-01"}
    ))
    store.add_claim(claim(
        "P001-OVERPAID", **{"累计完成产值(元)": "10000", "累计已付款(元)": "9000",
                           "本期预付款抵扣(元)": "0"}
    ))
    codes = {item["规则编号"] for item in store.risk_findings("2026-02-01")}
    assert {
        "SIGNED_CHANGE_NO_EVIDENCE", "CHANGE_OUTSIDE_TERM",
        "CHANGE_PENDING_OVER_14_DAYS", "PAYMENT_EXCEEDS_CEILING",
    }.issubset(codes)


def test_progress_payment_formula_caps_negative_and_reports_overpayment():
    result = module.calculate_progress_payment("10000", "0", "500", "0", "90", "5")
    assert result["本期应付金额(元)"] == "8000.00"
    assert result["累计支付上限(元)"] == "8500.00"
    overpaid = module.calculate_progress_payment("10000", "9000", "0", "0", "90", "5")
    assert overpaid["本期应付金额(元)"] == "0.00"
    assert overpaid["超付金额(元)"] == "500.00"


def test_csv_roundtrip_for_all_three_ledgers_and_duplicate_rejection(tmp_path):
    source = module.ConstructionStore(tmp_path / "source.json")
    source.add_project(project())
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence", encoding="utf-8")
    source.add_change(change(状态="已签认", 签认日期="2026-06-02", 证据文件=str(evidence)))
    source.add_claim(claim())

    target = module.ConstructionStore(tmp_path / "target.json")
    for kind in ("projects", "changes", "claims"):
        csv_path = tmp_path / f"{kind}.csv"
        source.export_csv(kind, csv_path)
        assert target.import_csv(kind, csv_path) == 1
    assert target.projects == source.projects
    assert target.changes == source.changes
    assert target.claims == source.claims

    duplicate = tmp_path / "duplicate-projects.csv"
    source.export_csv("projects", duplicate)
    before = target.projects[:]
    try:
        target.import_csv("projects", duplicate)
    except ValueError as exc:
        assert "整批未导入" in str(exc)
    else:
        raise AssertionError("duplicate project import accepted")
    assert target.projects == before


def test_csv_import_rejects_wrong_calculation_and_bad_rows_atomically(tmp_path):
    source = module.ConstructionStore(tmp_path / "source.json")
    source.add_project(project())
    source.add_claim(claim())
    csv_path = tmp_path / "claims.csv"
    source.export_csv("claims", csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    rows[0]["本期应付金额(元)"] = "1.00"
    bad = tmp_path / "bad-claims.csv"
    with bad.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.CLAIM_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    target = module.ConstructionStore(tmp_path / "target.json")
    target.add_project(project())
    before = target.claims[:]
    try:
        target.import_csv("claims", bad)
    except ValueError as exc:
        assert "计算结果" in str(exc)
    else:
        raise AssertionError("tampered claim calculation accepted")
    assert target.claims == before


def test_backup_restore_validates_shapes_and_relationships_atomically(tmp_path):
    path = tmp_path / "construction.json"
    store = module.ConstructionStore(path)
    store.add_project(project())
    store.add_change(change())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    restored = module.ConstructionStore(tmp_path / "restored.json")
    restored.restore(backup)
    assert restored.projects == store.projects
    assert restored.changes == store.changes

    before = (restored.projects[:], restored.changes[:], restored.claims[:], restored.audit[:])
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["changes"][0]["项目编号"] = "MISSING"
    invalid = tmp_path / "orphan.json"
    invalid.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        restored.restore(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("orphan variation in backup accepted")
    assert (restored.projects, restored.changes, restored.claims, restored.audit) == before

    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["projects"] = "not-a-list"
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")
    try:
        restored.restore(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong backup collection shape accepted")
    assert (restored.projects, restored.changes, restored.claims, restored.audit) == before


def test_project_ids_are_immutable_and_linked_projects_cannot_be_deleted(tmp_path):
    store = module.ConstructionStore(tmp_path / "construction.json")
    store.add_project(project())
    store.add_change(change())
    try:
        store.update_project("P001", project("P002"))
    except ValueError as exc:
        assert "不能修改" in str(exc)
    else:
        raise AssertionError("project ID change accepted")
    try:
        store.delete_project("P001")
    except ValueError as exc:
        assert "关联" in str(exc)
    else:
        raise AssertionError("project with linked variation deleted")


def test_failed_write_rolls_back_records_and_full_audit_history(tmp_path):
    store = module.ConstructionStore(tmp_path / "construction.json")
    store.audit = [
        {"时间": f"2026-01-01T00:00:{i % 60:02d}", "类别": "项目",
         "编号": "OLD", "操作": "历史", "说明": str(i)}
        for i in range(module.AUDIT_LIMIT)
    ]
    before = store.audit[:]
    store.save = lambda: (_ for _ in ()).throw(OSError("simulated write failure"))
    try:
        store.add_project(project())
    except OSError as exc:
        assert "simulated write failure" in str(exc)
    else:
        raise AssertionError("write failure not propagated")
    assert store.projects == []
    assert store.audit == before
    assert len(store.audit) == module.AUDIT_LIMIT


def test_csv_and_backup_reject_tampered_change_amount_atomically(tmp_path):
    source = module.ConstructionStore(tmp_path / "source.json")
    source.add_project(project())
    source.add_change(change())

    csv_path = tmp_path / "changes.csv"
    source.export_csv("changes", csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    rows[0]["金额(元)"] = "1.00"
    tampered_csv = tmp_path / "tampered-changes.csv"
    with tampered_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.CHANGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    target = module.ConstructionStore(tmp_path / "target.json")
    target.add_project(project())
    before = target.changes[:]
    try:
        target.import_csv("changes", tampered_csv)
    except ValueError as exc:
        assert "计量规则计算结果不一致" in str(exc)
    else:
        raise AssertionError("tampered variation amount was accepted")
    assert target.changes == before

    backup = tmp_path / "backup.json"
    source.backup(backup)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["changes"][0]["金额(元)"] = "1.00"
    tampered_backup = tmp_path / "tampered-backup.json"
    tampered_backup.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before_disk = target.path.read_bytes()
    try:
        target.restore(tampered_backup)
    except ValueError as exc:
        assert "计量规则计算结果不一致" in str(exc)
    else:
        raise AssertionError("tampered variation amount in backup was accepted")
    assert target.changes == before
    assert target.path.read_bytes() == before_disk