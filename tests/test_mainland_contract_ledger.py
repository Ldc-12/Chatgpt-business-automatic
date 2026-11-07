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
