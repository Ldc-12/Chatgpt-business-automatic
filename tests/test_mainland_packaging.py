import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tools" / "write_mainland_readme.py"
spec = importlib.util.spec_from_file_location("mainland_readme", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_mainland_readme_contains_real_chinese_and_local_paths():
    text = module.render_mainland_readme("MainlandSalesFollowupTool")
    assert "Windows 单机版｜大陆版" in text
    assert "%LOCALAPPDATA%\\MainlandBusinessTools\\licenses\\产品名.json" in text
    assert "本工具无需 ChatGPT、VPN 或外部 AI 服务。" in text
    assert "å" not in text
