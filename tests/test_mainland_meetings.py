import importlib.util
from pathlib import Path
p=Path(__file__).parents[1]/"apps"/"会议行动项管理.py";s=importlib.util.spec_from_file_location("m",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_helpers(): assert m.days(m.today())==0 and "负责人" in m.FIELDS
