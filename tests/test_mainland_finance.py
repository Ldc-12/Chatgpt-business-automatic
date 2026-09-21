import importlib.util
from pathlib import Path
p=Path(__file__).parents[1]/"apps"/"小微企业经营收支管理.py";s=importlib.util.spec_from_file_location("m",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_helpers(): assert m.num("￥1,200")==1200 and "金额" in m.FIELDS
