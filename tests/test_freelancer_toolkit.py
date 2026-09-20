import importlib.util, pathlib
p=pathlib.Path("apps/freelancer_toolkit.py")
spec=importlib.util.spec_from_file_location("app",p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def test_fields_are_stable():
    assert len(m.FIELDS)==9 and m.FIELDS[0]=="client" and m.FIELDS[-1]=="notes"
def test_overdue_total_contract():
    rows=[{"status":"overdue","amount":"500"},{"status":"paid","amount":"999"},{"status":"逾期","amount":"200.5"}]
    overdue=[r for r in rows if r["status"].lower() in ("overdue","逾期")]
    assert len(overdue)==2
    assert sum(float(r["amount"]) for r in overdue)==700.5
