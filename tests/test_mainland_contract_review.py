import csv
import importlib.util
import json
from pathlib import Path

import pytest

from src.contract_document_parser import REVIEW_FIELDS, parse_contract_document
from src.contract_review import (
    REVIEW_CSV_FIELDS,
    REVIEW_DECISIONS,
    ReviewStore,
    findings_sha256,
    sha256_file,
)

APP_PATH = Path(__file__).resolve().parents[1] / "apps" / "合同台账与到期提醒助手.py"
SPEC = importlib.util.spec_from_file_location("contract_ledger_for_review_tests", APP_PATH)
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


def source_text():
    return (
        "合同编号：RV-001\n"
        "合同名称：办公服务合同\n"
        "甲方：甲方公司\n"
        "乙方：乙方公司\n"
        "签订日期：2026-01-01\n"
        "生效日期：2026-01-02\n"
        "到期日期：2026-12-31\n"
        "合同金额：10000.00元\n"
        "保证金：人民币1000元。\n"
    )


def parsed_row(tmp_path):
    source = tmp_path / "合同-复核.txt"
    source.write_text(source_text(), encoding="utf-8")
    row = parse_contract_document(source)
    row["人工结论"] = REVIEW_DECISIONS[1]
    row["复核人"] = "测试复核员"
    row["复核备注"] = "请补充保证金退还条件"
    return source, row


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REVIEW_CSV_FIELDS})


def test_parser_records_source_and_risk_fingerprints(tmp_path):
    source = tmp_path / "合同-复核.txt"
    source.write_text(source_text(), encoding="utf-8")
    row = parse_contract_document(source)
    findings = json.loads(row["风险明细"])
    assert row["来源SHA256"] == sha256_file(source)
    assert row["风险明细SHA256"] == findings_sha256(findings)
    assert set(REVIEW_FIELDS).issubset(row)
    assert row["人工结论"] == ""
    assert row["复核人"] == ""
    assert row["复核备注"] == ""


def test_review_csv_import_persists_traceable_decision_and_allows_distinct_rereview(tmp_path):
    _, row = parsed_row(tmp_path)
    csv_path = tmp_path / "review.csv"
    write_csv(csv_path, [row])
    store = ReviewStore(tmp_path / "reviews.json")
    assert store.import_csv(csv_path) == 1
    loaded = ReviewStore(tmp_path / "reviews.json")
    item = loaded.records[0]
    assert item["来源SHA256"] == row["来源SHA256"]
    assert item["规则版本"] == row["规则版本"]
    assert item["人工结论"] == REVIEW_DECISIONS[1]
    assert item["复核备注"] == "请补充保证金退还条件"
    assert item["风险明细"][0]["规则编号"] == "DEPOSIT_RETURN_NOT_FOUND"

    row["人工结论"] = REVIEW_DECISIONS[0]
    row["复核备注"] = "已与签署原件逐项核对"
    write_csv(csv_path, [row])
    assert loaded.import_csv(csv_path) == 1
    assert len(ReviewStore(tmp_path / "reviews.json").records) == 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("来源SHA256", "not-a-hash", "来源 SHA256"),
        ("规则版本", "", "规则版本"),
        ("复核人", "", "复核人"),
        ("人工结论", "通过", "人工结论"),
        ("复核备注", "", "必须填写复核备注"),
    ],
)
def test_invalid_review_rows_are_rejected_atomically(tmp_path, field, value, message):
    _, row = parsed_row(tmp_path)
    row["人工结论"] = REVIEW_DECISIONS[1]
    row["复核备注"] = "基础复核备注"
    bad = dict(row)
    bad[field] = value
    csv_path = tmp_path / "bad.csv"
    write_csv(csv_path, [row, bad])
    store = ReviewStore(tmp_path / "reviews.json")
    with pytest.raises(ValueError, match=message):
        store.import_csv(csv_path)
    assert store.records == []
    assert not (tmp_path / "reviews.json").exists()


def test_review_import_rejects_tampered_risk_detail_digest(tmp_path):
    _, row = parsed_row(tmp_path)
    findings = json.loads(row["风险明细"])
    findings[0]["风险说明"] = "被修改的风险说明"
    row["风险明细"] = json.dumps(findings, ensure_ascii=False, separators=(",", ":"))
    csv_path = tmp_path / "tampered.csv"
    write_csv(csv_path, [row])
    store = ReviewStore(tmp_path / "reviews.json")
    with pytest.raises(ValueError, match="风险明细 SHA256 不匹配"):
        store.import_csv(csv_path)
    assert store.records == []


def test_duplicate_import_is_rejected_without_duplicate_history(tmp_path):
    _, row = parsed_row(tmp_path)
    csv_path = tmp_path / "review.csv"
    write_csv(csv_path, [row])
    store = ReviewStore(tmp_path / "reviews.json")
    assert store.import_csv(csv_path) == 1
    with pytest.raises(ValueError, match="完全重复"):
        store.import_csv(csv_path)
    assert len(store.records) == 1


def test_review_csv_export_escapes_spreadsheet_formulas(tmp_path):
    _, row = parsed_row(tmp_path)
    row["复核人"] = '=HYPERLINK("https://evil.invalid","click")'
    row["复核备注"] = "  @SUM(1,1)"
    csv_path = tmp_path / "review.csv"
    write_csv(csv_path, [row])
    store = ReviewStore(tmp_path / "reviews.json")
    store.import_csv(csv_path)
    exported = tmp_path / "export.csv"
    store.export_csv(exported)
    with exported.open("r", encoding="utf-8-sig", newline="") as handle:
        exported_row = next(csv.DictReader(handle))
    assert exported_row["复核人"].startswith("'=")
    assert exported_row["复核备注"].startswith("'@")


def test_review_store_restore_payload_is_atomic_on_write_failure(tmp_path, monkeypatch):
    _, row = parsed_row(tmp_path)
    csv_path = tmp_path / "review.csv"
    write_csv(csv_path, [row])
    store = ReviewStore(tmp_path / "reviews.json")
    store.import_csv(csv_path)
    original = store.records[:]
    invalid = {"format": "wrong", "version": 1, "records": []}
    with pytest.raises(ValueError, match="格式不受支持"):
        store.restore_payload(invalid)
    assert store.records == original

    new_payload = store.payload()
    new_payload["records"] = []
    monkeypatch.setattr(store, "save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        store.restore_payload(new_payload)
    assert store.records == original


def test_combined_backup_restores_review_history_and_rejects_bad_review_backup_atomically(tmp_path):
    contract_path = tmp_path / "contracts.json"
    workflow_path = tmp_path / "workflow.json"
    review_path = tmp_path / "reviews.json"
    contracts = APP.ContractStore(contract_path)
    workflow = APP.WorkflowStore(workflow_path)
    reviews = ReviewStore(review_path)
    contract = {
        "合同编号": "C001", "合同名称": "合同", "甲方/客户": "甲方", "乙方/供应商": "乙方",
        "签订日期": "2026-01-01", "生效日期": "2026-01-01", "到期日期": "2026-12-31",
        "合同金额": "1000", "续约提醒提前天数": "30", "状态": "执行中",
    }
    contracts.add(contract)
    _, row = parsed_row(tmp_path)
    review_csv = tmp_path / "review.csv"
    write_csv(review_csv, [row])
    reviews.import_csv(review_csv)
    backup = tmp_path / "workspace.json"
    contracts.backup(backup, workflow, reviews)

    contracts.add({**contract, "合同编号": "C002"})
    payload = json.loads(backup.read_text(encoding="utf-8"))
    contracts.restore(backup, workflow, reviews)
    assert [item["合同编号"] for item in contracts.rows] == ["C001"]
    assert len(reviews.records) == 1
    assert len(ReviewStore(review_path).records) == 1

    before_contracts = contracts.rows[:]
    before_workflow = workflow.payload()
    before_reviews = reviews.records[:]
    payload["reviews"]["records"][0]["人工结论"] = "篡改结论"
    bad = tmp_path / "bad-workspace.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="人工结论无效"):
        contracts.restore(bad, workflow, reviews)
    assert contracts.rows == before_contracts
    assert workflow.payload() == before_workflow
    assert reviews.records == before_reviews


def test_legacy_v2_backup_restores_without_review_history(tmp_path):
    contract_path = tmp_path / "contracts.json"
    workflow_path = tmp_path / "workflow.json"
    review_path = tmp_path / "reviews.json"
    contracts = APP.ContractStore(contract_path)
    workflow = APP.WorkflowStore(workflow_path)
    reviews = ReviewStore(review_path)
    contract = {
        "合同编号": "OLD", "合同名称": "旧合同", "签订日期": "2026-01-01",
        "生效日期": "2026-01-01", "到期日期": "2026-12-31",
        "合同金额": "100", "续约提醒提前天数": "30", "状态": "执行中",
    }
    contracts.add(contract)
    legacy = {
        "format": APP.BACKUP_FORMAT, "version": 2,
        "contracts": [APP.normalize(contract)], "workflow": workflow.payload(),
    }
    path = tmp_path / "legacy-v2.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    contracts.restore(path, workflow, reviews)
    assert [item["合同编号"] for item in contracts.rows] == ["OLD"]
    assert reviews.records == []


def test_draft_csv_escapes_formula_like_contract_fields(tmp_path):
    source = tmp_path / "formula.txt"
    source.write_text(
        source_text().replace("办公服务合同", '=HYPERLINK("https://evil.invalid","click")'),
        encoding="utf-8",
    )
    output = tmp_path / "draft.csv"
    from src.contract_document_parser import write_draft_csv
    write_draft_csv([source], output)
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["合同名称"].startswith("'=")


def test_contract_and_milestone_csv_exports_escape_formula_like_cells(tmp_path):
    contract = {
        "合同编号": "=1+1", "合同名称": "合同", "甲方/客户": "甲方", "乙方/供应商": "乙方",
        "签订日期": "2026-01-01", "生效日期": "2026-01-01", "到期日期": "2026-12-31",
        "合同金额": "100", "续约提醒提前天数": "30", "状态": "执行中",
    }
    contracts = APP.ContractStore(tmp_path / "contracts.json")
    contracts.add(contract)
    contract_csv = tmp_path / "contracts.csv"
    contracts.export_csv(contract_csv)
    with contract_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        assert next(csv.DictReader(handle))["合同编号"] == "'=1+1"

    workflow = APP.WorkflowStore(tmp_path / "workflow.json")
    milestone = {
        "节点编号": "M001", "合同编号": "=1+1", "节点名称": "节点", "节点类型": "其他",
        "计划日期": "2026-12-01", "金额": "0", "状态": "待处理", "完成日期": "", "备注": "@SUM(1,1)",
    }
    workflow.milestones = [APP.normalize_milestone(milestone)] if hasattr(APP, "normalize_milestone") else [
        {"节点编号": "M001", "合同编号": "=1+1", "节点名称": "节点", "节点类型": "其他",
         "计划日期": "2026-12-01", "金额": "0.00", "状态": "待处理", "完成日期": "", "备注": "@SUM(1,1)"}
    ]
    milestone_csv = tmp_path / "milestones.csv"
    workflow.export_csv(milestone_csv)
    with milestone_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["合同编号"] == "'=1+1"
    assert row["备注"] == "'@SUM(1,1)"


def test_combined_restore_rolls_back_all_stores_when_review_write_fails(tmp_path, monkeypatch):
    contract_path = tmp_path / "contracts.json"
    workflow_path = tmp_path / "workflow.json"
    review_path = tmp_path / "reviews.json"
    contracts = APP.ContractStore(contract_path)
    workflow = APP.WorkflowStore(workflow_path)
    reviews = ReviewStore(review_path)
    contract = {
        "合同编号": "C001", "合同名称": "合同", "甲方/客户": "甲方", "乙方/供应商": "乙方",
        "签订日期": "2026-01-01", "生效日期": "2026-01-01", "到期日期": "2026-12-31",
        "合同金额": "1000", "续约提醒提前天数": "30", "状态": "执行中",
    }
    contracts.add(contract)
    node = {
        "节点编号": "", "合同编号": "C001", "节点名称": "首付款", "节点类型": "付款",
        "计划日期": "2026-02-01", "金额": "100.00", "状态": "待处理", "完成日期": "", "备注": "",
    }
    workflow.add("C001", node)
    _, row = parsed_row(tmp_path)
    review_csv = tmp_path / "review.csv"
    write_csv(review_csv, [row])
    reviews.import_csv(review_csv)
    backup = tmp_path / "workspace.json"
    contracts.backup(backup, workflow, reviews)

    contracts.add({**contract, "合同编号": "C002"})
    workflow.add("C002", {**node, "节点编号": "", "合同编号": "C002"})
    row["复核备注"] = "第二次复核记录"
    write_csv(review_csv, [row])
    reviews.import_csv(review_csv)
    before_contracts = contracts.rows[:]
    before_milestones = workflow.milestones[:]
    before_audit = workflow.audit[:]
    before_reviews = reviews.records[:]

    monkeypatch.setattr(reviews, "save", lambda: (_ for _ in ()).throw(OSError("review disk full")))
    with pytest.raises(OSError, match="review disk full"):
        contracts.restore(backup, workflow, reviews)
    assert contracts.rows == before_contracts
    assert workflow.milestones == before_milestones
    assert workflow.audit == before_audit
    assert reviews.records == before_reviews
    assert len(ReviewStore(review_path).records) == 2
