import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"apps"/"轻量销售客户跟进工具.py"
s=importlib.util.spec_from_file_location("sales",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
def test_sales_helpers():
    assert m.num("￥1,200")==1200
    assert m.today()
    assert "客户" in m.FIELDS

def sample_customer(**overrides):
    row = {field: "" for field in m.FIELDS}
    row.update({"客户": "测试客户", "阶段": "新线索", "预计金额": "1200"})
    row.update(overrides)
    return row


def test_sales_json_backup_roundtrip(tmp_path):
    source = tmp_path / "sales.json"
    backup = tmp_path / "sales-backup.json"
    rows = [sample_customer(联系人="张先生", 备注="年度续约")]
    m.save_rows(source, rows)
    loaded = m.load_rows(source)
    assert loaded == rows

    m.save_rows(backup, loaded)
    assert m.load_rows(backup) == rows


def test_sales_json_rejects_corrupt_or_incomplete_data(tmp_path):
    source = tmp_path / "sales.json"
    source.write_text('{"not": "a list"}', encoding="utf-8")
    try:
        m.load_rows(source)
    except ValueError as exc:
        assert "顶层必须是记录列表" in str(exc)
    else:
        raise AssertionError("corrupt backup was accepted")

    source.write_text('[{"客户": "不完整"}]', encoding="utf-8")
    try:
        m.load_rows(source)
    except ValueError as exc:
        assert "缺少字段" in str(exc)
    else:
        raise AssertionError("incomplete record was accepted")


def test_sales_json_failed_save_preserves_previous_file(tmp_path):
    source = tmp_path / "sales.json"
    m.save_rows(source, [sample_customer()])
    original = source.read_bytes()
    try:
        m.save_rows(source, [{"客户": "缺少字段"}])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid rows were saved")
    assert source.read_bytes() == original


def test_sales_json_rejects_invalid_amount(tmp_path):
    try:
        m.validate_rows([sample_customer(预计金额="not-a-number")])
    except ValueError as exc:
        assert "预计金额无效" in str(exc)
    else:
        raise AssertionError("invalid amount was accepted")
