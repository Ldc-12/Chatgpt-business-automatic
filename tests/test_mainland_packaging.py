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


APP_ENTRYPOINTS = [
    "文件整理助手Pro.py",
    "图片批量处理助手Pro.py",
    "PDF批量工具Pro.py",
    "自由职业催款管理工具.py",
    "轻量销售客户跟进工具.py",
    "求职申请管理Pro.py",
    "小微企业经营收支管理.py",
    "会议行动项管理.py",
    "SOP项目执行管理.py",
    "实用效率工具箱.py",
    "小店库存盘点助手.py",
]


def test_all_frozen_apps_support_noninteractive_exe_smoke_mode():
    apps_dir = Path(__file__).resolve().parents[1] / "apps"
    for filename in APP_ENTRYPOINTS:
        source = (apps_dir / filename).read_text(encoding="utf-8")
        entrypoint = source.rsplit('if __name__', 1)[-1]
        assert 'MAINLAND_EXE_SELF_TEST' in entrypoint, filename
        assert 'os._exit(0)' in entrypoint, filename
