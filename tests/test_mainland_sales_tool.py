import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"apps"/"轻量销售客户跟进工具.py"
s=importlib.util.spec_from_file_location("sales",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
def test_sales_helpers():
    assert m.num("￥1,200")==1200
    assert m.today()
    assert "客户" in m.FIELDS
