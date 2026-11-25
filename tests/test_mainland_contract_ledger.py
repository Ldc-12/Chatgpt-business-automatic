import csv
import importlib.util
import pytest
from datetime import date
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "合同台账与到期提醒助手.py"
spec = importlib.util.spec_from_file_location("contract_ledger", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(cid="C001", expiry="2026-12-31"):
    return {"合同编号":cid,"合同名称":"办公租赁合同","甲方/客户":"甲方","乙方/供应商":"乙方",
            "签订日期":"2026-01-01","生效日期":"2026-01-01","到期日期":expiry,
            "合同金额":"1200.50","续约提醒提前天数":"30","状态":"执行中",
            "负责人":"张三","联系方式":"13800000000","备注":""}


def test_money_decimal_rounding_and_validation():
    assert module.money("1,234.565") == "1234.57"
    for bad in ("-1", "NaN", "abc"):
        try: module.money(bad)
        except ValueError: pass
        else: raise AssertionError(f"invalid money accepted: {bad}")


def test_date_order_and_reminder_boundaries():
    item = module.normalize(row())
    assert module.reminder_state(item, date(2026,12,1)) == ("即将到期",30)
    assert module.reminder_state(item, date(2026,12,31)) == ("即将到期",0)
    assert module.reminder_state(item, date(2027,1,1)) == ("已逾期",-1)
    bad=row(); bad["生效日期"]="2027-01-01"
    try: module.normalize(bad)
    except ValueError: pass
    else: raise AssertionError("invalid date order accepted")


def test_add_reload_update_and_delete(tmp_path):
    p=tmp_path/"contracts.json"; store=module.ContractStore(p); store.add(row())
    loaded=module.ContractStore(p); assert loaded.rows[0]["合同编号"]=="C001"
    loaded.update("C001", row(expiry="2027-01-31"))
    assert module.ContractStore(p).rows[0]["到期日期"]=="2027-01-31"
    loaded.delete("C001"); assert module.ContractStore(p).rows==[]


def test_csv_roundtrip_and_duplicate_import_atomic(tmp_path):
    store=module.ContractStore(tmp_path/"contracts.json")
    csvpath=tmp_path/"contracts.csv"
    with csvpath.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=module.FIELDS); w.writeheader(); w.writerow(row())
    assert store.import_csv(csvpath)==1
    before=store.rows[:]
    try: store.import_csv(csvpath)
    except ValueError as e: assert "整批未导入" in str(e)
    else: raise AssertionError("duplicate import accepted")
    assert store.rows==before


def test_contract_csv_export_is_atomic_and_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    store = module.ContractStore(tmp_path / "contracts.json")
    store.add(row())
    target = tmp_path / "exports" / "contracts.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous-valid-csv")

    def fail_replace(source, destination):
        raise OSError("simulated CSV replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated CSV replace failure"):
        store.export_csv(target)

    assert target.read_bytes() == b"previous-valid-csv"
    assert list(target.parent.glob("contracts.csv*.tmp")) == []


def test_contract_csv_export_keeps_utf8_bom_and_roundtrips_formula_and_literal_apostrophe_text(tmp_path):
    store = module.ContractStore(tmp_path / "contracts.json")
    item = row()
    item["合同名称"] = "'=手工合同名称"
    item["备注"] = "=1+1"
    store.add(item)
    target = tmp_path / "exports" / "contracts.csv"

    store.export_csv(target)

    raw = target.read_bytes()
    assert raw.startswith(bytes((0xEF, 0xBB, 0xBF)))
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["备注"] == "'=1+1"
    assert exported["合同名称"] == "''=手工合同名称"

    roundtrip = module.ContractStore(tmp_path / "roundtrip.json")
    assert roundtrip.import_csv(target) == 1
    assert roundtrip.rows[0]["备注"] == "=1+1"
    assert roundtrip.rows[0]["合同名称"] == "'=手工合同名称"


def test_contract_workflow_csv_export_roundtrips_formula_and_literal_apostrophe_text(tmp_path):
    workflow = module.WorkflowStore(tmp_path / "workflow.json")
    workflow.milestones = [{
        "节点编号": "M001",
        "合同编号": "C001",
        "节点名称": "=付款节点",
        "节点类型": "付款",
        "计划日期": "2026-12-01",
        "金额": "100.00",
        "状态": "待处理",
        "完成日期": "",
        "备注": "'@原始备注",
    }]
    target = tmp_path / "milestones.csv"

    workflow.export_csv(target)

    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["节点名称"] == "'=付款节点"
    assert exported["备注"] == "''@原始备注"

    roundtrip = module.WorkflowStore(tmp_path / "workflow-roundtrip.json")
    assert roundtrip.import_csv(target, {"C001"}) == 1
    assert roundtrip.milestones[0]["节点名称"] == "=付款节点"
    assert roundtrip.milestones[0]["备注"] == "'@原始备注"


def test_bad_csv_row_does_not_mutate_store(tmp_path):
    store=module.ContractStore(tmp_path/"contracts.json"); store.add(row())
    bad=tmp_path/"bad.csv"
    with bad.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=module.FIELDS); w.writeheader(); r=row("C002"); r["到期日期"]="not-a-date"; w.writerow(r)
    try: store.import_csv(bad)
    except ValueError: pass
    else: raise AssertionError("bad CSV accepted")
    assert [r["合同编号"] for r in store.rows]==["C001"]


def test_backup_restore_and_invalid_backup_atomic(tmp_path):
    store=module.ContractStore(tmp_path/"contracts.json"); store.add(row())
    backup=tmp_path/"backup.json"; store.backup(backup)
    store.add(row("C002")); store.restore(backup)
    assert len(module.ContractStore(tmp_path/"contracts.json").rows)==1
    invalid=tmp_path/"invalid.json"; invalid.write_text('{"format":"wrong","version":99,"contracts":[]}',encoding="utf-8")
    try: store.restore(invalid)
    except ValueError: pass
    else: raise AssertionError("invalid backup accepted")
    assert len(store.rows)==1


def test_backup_write_is_atomic_and_preserves_existing_backup_on_replace_failure(tmp_path, monkeypatch):
    store = module.ContractStore(tmp_path / "contracts.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    backup.write_text("previous-valid-backup", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated atomic replace failure"):
        store.backup(backup)

    assert backup.read_text(encoding="utf-8") == "previous-valid-backup"
    assert list(tmp_path.glob("backup.json*.tmp")) == []


def test_backup_creates_missing_parent_directory_and_writes_valid_json(tmp_path):
    store = module.ContractStore(tmp_path / "contracts.json")
    store.add(row())
    backup = tmp_path / "exports" / "nested" / "backup.json"
    store.backup(backup)
    payload = __import__("json").loads(backup.read_text(encoding="utf-8"))
    assert payload["format"] == module.BACKUP_FORMAT
    assert payload["version"] == module.BACKUP_VERSION
    assert payload["contracts"][0]["合同编号"] == "C001"


def test_reminder_exclusions_for_renewed_or_terminated():
    item=module.normalize(row())
    item["状态"]="已续约"
    assert module.reminder_state(item,date(2026,12,31))[0]=="无需提醒"
    item["状态"]="已终止"
    assert module.reminder_state(item,date(2026,12,31))[0]=="无需提醒"


def test_restore_rejects_invalid_json_shapes_and_rows_atomically(tmp_path):
    path = tmp_path / "contracts.json"
    store = module.ContractStore(path)
    store.add(row())
    before = store.rows[:]
    valid_header = {"format": module.BACKUP_FORMAT, "version": module.BACKUP_VERSION}
    invalid_payloads = [
        "[]",
        '{"format":"mainland-contract-ledger","version":1}',
        '{"format":"mainland-contract-ledger","version":1,"contracts":"not-a-list"}',
        '{"format":"mainland-contract-ledger","version":1,"contracts":[null]}',
        '{"format":"mainland-contract-ledger","version":true,"contracts":[]}',
        "{not-json",
    ]
    for index, payload in enumerate(invalid_payloads):
        backup = tmp_path / f"invalid-{index}.json"
        backup.write_text(payload, encoding="utf-8")
        try:
            store.restore(backup)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid backup accepted: {payload}")
        assert store.rows == before
        assert module.ContractStore(path).rows == before


def milestone(mid, cid="C001", kind="付款", due="2026-12-05", amount="50.00", status="待处理", completed=""):
    return {
        "节点编号": mid, "合同编号": cid, "节点名称": f"{kind}节点",
        "节点类型": kind, "计划日期": due, "金额": amount,
        "状态": status, "完成日期": completed, "备注": ""
    }


def test_workflow_store_add_complete_reload_and_audit(tmp_path):
    workflow_path = tmp_path / "contract_workflow.json"
    store = module.WorkflowStore(workflow_path)
    item = store.add("C001", milestone("", due="2026-12-05"))
    assert item["节点编号"]
    assert item["合同编号"] == "C001"
    assert len(store.audit) == 1
    store.complete(item["节点编号"], "2026-12-04")
    loaded = module.WorkflowStore(workflow_path)
    assert loaded.milestones[0]["状态"] == "已完成"
    assert loaded.milestones[0]["完成日期"] == "2026-12-04"
    assert [event["操作"] for event in loaded.audit] == ["新增节点", "标记完成"]


def test_workflow_csv_roundtrip_and_atomic_rejection(tmp_path):
    store = module.WorkflowStore(tmp_path / "workflow.json")
    valid = tmp_path / "valid.csv"
    with valid.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.MILESTONE_FIELDS)
        writer.writeheader()
        writer.writerow(milestone("M001"))
    assert store.import_csv(valid, {"C001"}) == 1
    before = store.milestones[:]
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.MILESTONE_FIELDS)
        writer.writeheader()
        writer.writerow(milestone("M001"))
    try:
        store.import_csv(duplicate, {"C001"})
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate milestone import accepted")
    orphan = tmp_path / "orphan.csv"
    with orphan.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.MILESTONE_FIELDS)
        writer.writeheader()
        writer.writerow(milestone("M002", cid="MISSING"))
    try:
        store.import_csv(orphan, {"C001"})
    except ValueError as exc:
        assert "找不到合同" in str(exc)
    else:
        raise AssertionError("orphan milestone import accepted")
    assert store.milestones == before
    exported = tmp_path / "export.csv"
    store.export_csv(exported)
    other = module.WorkflowStore(tmp_path / "other.json")
    assert other.import_csv(exported, {"C001"}) == 1
    assert other.milestones == store.milestones


def test_workflow_rejects_invalid_status_dates_and_duplicate_ids(tmp_path):
    path = tmp_path / "workflow.json"
    payload = {
        "format": module.WORKFLOW_FORMAT, "version": module.WORKFLOW_VERSION,
        "milestones": [milestone("M001", status="已完成", completed="")], "audit": []
    }
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        module.WorkflowStore(path)
    except ValueError as exc:
        assert "完成日期" in str(exc)
    else:
        raise AssertionError("completed milestone without completion date accepted")
    payload["milestones"] = [milestone("M001"), milestone("M001")]
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        module.WorkflowStore(path)
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate milestone IDs accepted")


def test_risk_engine_flags_overdue_soon_outside_term_and_excess_plan():
    contract = row("C100", expiry="2026-12-31")
    contract["合同金额"] = "120.00"
    contract["乙方/供应商"] = ""
    nodes = [
        milestone("M1", "C100", "付款", "2026-11-30", "80.00"),
        milestone("M2", "C100", "付款", "2026-12-05", "50.00"),
        milestone("M3", "C100", "收款", "2027-01-01", "10.00"),
    ]
    findings = module.risk_findings([module.normalize(contract)], nodes, date(2026, 12, 1))
    codes = {item["规则编号"] for item in findings}
    assert {"PARTY_MISSING", "MILESTONE_OVERDUE", "MILESTONE_DUE_SOON",
            "MILESTONE_OUTSIDE_TERM", "PAYMENT_PLAN_EXCEEDS_AMOUNT"}.issubset(codes)
    assert findings[0]["等级"] == "高"


def test_finance_summary_separates_pending_and_completed_amounts():
    nodes = [
        milestone("M1", kind="付款", amount="100.25"),
        milestone("M2", kind="付款", amount="20.00", status="已完成", completed="2026-12-01"),
        milestone("M3", kind="收款", amount="300.00"),
        milestone("M4", kind="收款", amount="50.00", status="已取消"),
    ]
    assert module.finance_summary(nodes) == {
        "待付款": "100.25", "待收款": "300.00",
        "已完成付款": "20.00", "已完成收款": "0.00"
    }


def test_combined_backup_restores_contracts_milestones_and_audit_atomically(tmp_path):
    contract_path = tmp_path / "contracts.json"
    workflow_path = tmp_path / "contract_workflow.json"
    store = module.ContractStore(contract_path)
    workflow = module.WorkflowStore(workflow_path)
    store.add(row("C001"))
    workflow.add("C001", milestone("", cid="C001"))
    backup = tmp_path / "workspace.json"
    store.backup(backup, workflow)
    store.add(row("C002"))
    workflow.add("C002", milestone("", cid="C002", due="2026-12-06"))
    store.restore(backup, workflow)
    assert [item["合同编号"] for item in module.ContractStore(contract_path).rows] == ["C001"]
    restored = module.WorkflowStore(workflow_path)
    assert len(restored.milestones) == 1
    assert len(restored.audit) == 1
    bad = tmp_path / "bad-workspace.json"
    payload = __import__("json").loads(backup.read_text(encoding="utf-8"))
    payload["workflow"]["milestones"] = [milestone("M1", cid="UNKNOWN")]
    bad.write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
    before_contracts = store.rows[:]
    before_nodes = workflow.milestones[:]
    try:
        store.restore(bad, workflow)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid combined backup accepted")
    assert store.rows == before_contracts
    assert workflow.milestones == before_nodes


def test_workflow_mutations_restore_full_audit_history_when_save_fails_at_limit(tmp_path):
    def make_store():
        store = module.WorkflowStore(tmp_path / "workflow.json")
        store.milestones = [milestone("M001")]
        store.audit = [
            {
                "时间": f"2026-01-01T00:00:{index % 60:02d}",
                "合同编号": "C001",
                "节点编号": "",
                "操作": "历史操作",
                "说明": str(index),
            }
            for index in range(5000)
        ]
        return store

    operations = [
        lambda store: store.add("C001", milestone("M002")),
        lambda store: store.update("M001", milestone("M001", amount="60.00")),
        lambda store: store.delete("M001"),
    ]
    for operation in operations:
        store = make_store()
        before_milestones = store.milestones[:]
        before_audit = store.audit[:]

        def fail_save():
            raise OSError("simulated disk write failure")

        store.save = fail_save
        try:
            operation(store)
        except OSError as exc:
            assert "simulated disk write failure" in str(exc)
        else:
            raise AssertionError("write failure was not propagated")

        assert store.milestones == before_milestones
        assert store.audit == before_audit
        assert len(store.audit) == 5000
        assert store.audit[0]["说明"] == "0"
        assert store.audit[-1]["说明"] == "4999"



def test_finance_aging_report_uses_exact_overdue_bucket_boundaries_and_excludes_closed_nodes(tmp_path):
    today = date(2026, 11, 25)
    contract = module.normalize(row("C001"))
    workflow = module.WorkflowStore(tmp_path / "workflow.json")

    def add_node(node_id, kind, due, amount="10.00", status="待处理", completed=""):
        return workflow.add("C001", {
            "节点编号": node_id,
            "合同编号": "C001",
            "节点名称": node_id,
            "节点类型": kind,
            "计划日期": due,
            "金额": amount,
            "状态": status,
            "完成日期": completed,
            "备注": "",
        })

    cases = [
        ("M091", "付款", "2026-08-26", "91", "逾期91天以上"),
        ("M090", "收款", "2026-08-27", "90", "逾期31-90天"),
        ("M031", "付款", "2026-10-25", "31", "逾期31-90天"),
        ("M030", "收款", "2026-10-26", "30", "逾期8-30天"),
        ("M008", "付款", "2026-11-17", "8", "逾期8-30天"),
        ("M007", "收款", "2026-11-18", "7", "逾期1-7天"),
        ("M001", "付款", "2026-11-24", "1", "逾期1-7天"),
        ("M000", "收款", "2026-11-25", "0", "未逾期（含统计日）"),
        ("M-FUTURE", "付款", "2026-11-26", "0", "未逾期（含统计日）"),
    ]
    for node_id, kind, due, days, bucket in cases:
        add_node(node_id, kind, due)
    add_node("M-DONE", "收款", "2026-11-20", status="已完成", completed="2026-11-20")
    add_node("M-CANCEL", "付款", "2026-11-20", status="已取消")
    add_node("M-DELIVERY", "交付", "2026-11-20")

    report = module.finance_aging_report([contract], workflow.milestones, today)
    assert len(report) == len(cases)
    by_id = {item["节点编号"]: item for item in report}
    for node_id, _, _, days, bucket in cases:
        assert by_id[node_id]["逾期天数"] == days
        assert by_id[node_id]["账龄分组"] == bucket
    assert by_id["M091"]["方向"] == "待付款"
    assert by_id["M090"]["方向"] == "待收款"
    assert by_id["M091"]["往来方"] == "乙方"
    assert by_id["M090"]["往来方"] == "甲方"
    assert "M-DONE" not in by_id and "M-CANCEL" not in by_id and "M-DELIVERY" not in by_id
    assert [item["计划日期"] for item in report] == sorted(item["计划日期"] for item in report)


def test_finance_aging_report_keeps_orphan_contract_nodes_visible(tmp_path):
    workflow = module.WorkflowStore(tmp_path / "workflow.json")
    workflow.add("MISSING", {
        "节点编号": "ORPHAN-1", "合同编号": "MISSING", "节点名称": "历史应收款",
        "节点类型": "收款", "计划日期": "2026-11-01", "金额": "88.00",
        "状态": "待处理", "完成日期": "", "备注": "请核对合同档案",
    })
    report = module.finance_aging_report([], workflow.milestones, date(2026, 11, 25))
    assert len(report) == 1
    assert report[0]["合同编号"] == "MISSING"
    assert report[0]["合同名称"] == ""
    assert report[0]["往来方"] == ""
    assert report[0]["备注"] == "请核对合同档案；合同记录不存在"


def test_finance_aging_csv_is_formula_safe_atomic_and_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    contract = module.normalize(row("C001"))
    contract["合同名称"] = "=HYPERLINK(\"https://evil.invalid\",\"合同\")"
    contract["乙方/供应商"] = "@SUM(1,1)"
    workflow = module.WorkflowStore(tmp_path / "workflow.json")
    workflow.add("C001", {
        "节点编号": "M001", "合同编号": "C001", "节点名称": "=收款节点",
        "节点类型": "付款", "计划日期": "2026-11-24", "金额": "100.00",
        "状态": "待处理", "完成日期": "", "备注": "'@原始备注",
    })
    target = tmp_path / "exports" / "finance-aging.csv"
    assert module.export_finance_aging_csv(target, [contract], workflow.milestones, date(2026, 11, 25)) == 1
    assert target.read_bytes().startswith(bytes((0xEF, 0xBB, 0xBF)))
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["合同名称"].startswith("'=")
    assert exported["往来方"].startswith("'@")
    assert exported["节点名称"] == "'=收款节点"
    assert exported["备注"] == "''@原始备注"

    target.write_bytes(b"previous-valid-report")

    def fail_replace(source, destination):
        raise OSError("simulated aging CSV replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated aging CSV replace failure"):
        module.export_finance_aging_csv(target, [contract], workflow.milestones, date(2026, 11, 25))
    assert target.read_bytes() == b"previous-valid-report"
    assert list(target.parent.glob("finance-aging.csv*.tmp")) == []


def test_finance_aging_summary_groups_by_contract_counterparty_direction_and_bucket(tmp_path):
    today = date(2026, 11, 25)
    contract_one = module.normalize(row("C001"))
    contract_one["乙方/供应商"] = "=供应商A"
    contract_one["甲方/客户"] = "@客户A"
    contract_two = module.normalize(row("C002"))
    contract_two["乙方/供应商"] = "=供应商A"
    workflow = module.WorkflowStore(tmp_path / "workflow.json")

    def add(contract_id, node_id, kind, due, amount, status="待处理"):
        workflow.add(contract_id, {
            "节点编号": node_id,
            "合同编号": contract_id,
            "节点名称": node_id,
            "节点类型": kind,
            "计划日期": due,
            "金额": amount,
            "状态": status,
            "完成日期": "2026-11-20" if status == "已完成" else "",
            "备注": "",
        })

    add("C001", "P-7", "付款", "2026-11-18", "100.00")
    add("C001", "P-20", "付款", "2026-11-05", "50.00")
    add("C001", "P-FUTURE", "付款", "2026-11-26", "25.00")
    add("C001", "R-31", "收款", "2026-10-25", "40.00")
    add("C001", "R-TODAY", "收款", "2026-11-25", "10.00")
    add("C002", "P-1", "付款", "2026-11-24", "30.00")
    add("C001", "P-DONE", "付款", "2026-11-01", "999.00", status="已完成")
    add("C001", "P-CANCEL", "付款", "2026-11-01", "888.00", status="已取消")
    add("C001", "DELIVERY", "交付", "2026-11-01", "777.00")

    summary = module.finance_aging_summary(
        [contract_one, contract_two], workflow.milestones, today
    )
    by_key = {
        (item["合同编号"], item["方向"]): item
        for item in summary
    }
    assert len(summary) == 3
    pay_one = by_key[("C001", "待付款")]
    assert pay_one["待处理节点数"] == "3"
    assert pay_one["最早计划日期"] == "2026-11-05"
    assert pay_one["未逾期金额"] == "25.00"
    assert pay_one["逾期1-7天金额"] == "100.00"
    assert pay_one["逾期8-30天金额"] == "50.00"
    assert pay_one["待处理金额"] == "175.00"
    assert pay_one["逾期金额"] == "150.00"
    receipt_one = by_key[("C001", "待收款")]
    assert receipt_one["逾期31-90天金额"] == "40.00"
    assert receipt_one["未逾期金额"] == "10.00"
    assert receipt_one["待处理金额"] == "50.00"
    pay_two = by_key[("C002", "待付款")]
    assert pay_two["待处理金额"] == "30.00"
    assert pay_two["往来方"] == "=供应商A"
    assert summary[0]["逾期金额"] == "150.00"


def test_finance_aging_summary_csv_is_formula_safe_atomic_and_writes_header_when_empty(tmp_path, monkeypatch):
    contract = module.normalize(row("C001"))
    contract["合同名称"] = "=HYPERLINK(\"https://evil.invalid\",\"合同\")"
    contract["乙方/供应商"] = "@供应商A"
    workflow = module.WorkflowStore(tmp_path / "workflow.json")
    workflow.add("C001", {
        "节点编号": "P001", "合同编号": "C001", "节点名称": "首付款",
        "节点类型": "付款", "计划日期": "2026-11-24", "金额": "80.00",
        "状态": "待处理", "完成日期": "", "备注": "",
    })
    target = tmp_path / "exports" / "counterparty-aging.csv"
    assert module.export_finance_aging_summary_csv(
        target, [contract], workflow.milestones, date(2026, 11, 25)
    ) == 1
    assert target.read_bytes().startswith(bytes((0xEF, 0xBB, 0xBF)))
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = next(csv.DictReader(handle))
    assert exported["合同名称"].startswith("'=")
    assert exported["往来方"].startswith("'@")
    assert exported["待处理金额"] == "80.00"

    target.write_bytes(b"previous-valid-summary")

    def fail_replace(source, destination):
        raise OSError("simulated summary CSV replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated summary CSV replace failure"):
        module.export_finance_aging_summary_csv(
            target, [contract], workflow.milestones, date(2026, 11, 25)
        )
    assert target.read_bytes() == b"previous-valid-summary"
    assert list(target.parent.glob("counterparty-aging.csv*.tmp")) == []
    monkeypatch.undo()

    empty_target = tmp_path / "exports" / "empty-summary.csv"
    assert module.export_finance_aging_summary_csv(empty_target, [], [], date(2026, 11, 25)) == 0
    with empty_target.open("r", encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
