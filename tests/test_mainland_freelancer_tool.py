import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "apps" / "自由职业催款管理工具.py"

spec = importlib.util.spec_from_file_location("mainland_tool", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_amount_parsing():
    assert mod.parse_amount("￥2,000") == 2000
    assert mod.parse_amount("1,200.50") == 1200.5
    assert mod.parse_amount("") == 0


def test_date_helper():
    assert mod.days_until(mod.today()) == 0


def test_fields_are_mainland_chinese():
    assert "客户" in mod.FIELDS
    assert "下次跟进" in mod.FIELDS
