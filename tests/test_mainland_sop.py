import importlib.util
from pathlib import Path
p=Path(__file__).parents[1]/"apps"/"SOP项目执行管理.py";s=importlib.util.spec_from_file_location("m",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_helpers(): assert "SOP名称" in m.FIELDS and "阻塞" in m.ST
