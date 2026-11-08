import csv
import importlib.util
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
