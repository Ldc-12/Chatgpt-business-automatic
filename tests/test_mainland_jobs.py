import importlib.util
from pathlib import Path
p=Path(__file__).parents[1]/"apps"/"求职申请管理Pro.py";s=importlib.util.spec_from_file_location("m",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_helpers(): assert m.num("￥12,000")==12000 and m.due(m.today())==0 and "公司" in m.FIELDS
