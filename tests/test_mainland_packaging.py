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
    "供应商采购比价助手.py",
    "报价单生成器.py",
]


def test_all_frozen_apps_support_noninteractive_exe_smoke_mode():
    apps_dir = Path(__file__).resolve().parents[1] / "apps"
    for filename in APP_ENTRYPOINTS:
        source = (apps_dir / filename).read_text(encoding="utf-8")
        entrypoint = source.rsplit('if __name__', 1)[-1]
        assert 'MAINLAND_EXE_SELF_TEST' in entrypoint, filename
        assert 'os._exit(0)' in entrypoint, filename


def test_frozen_exe_build_includes_license_module_and_checks_real_exit_code():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert "--paths ." in workflow
    assert "--hidden-import src.license" in workflow
    assert 'EnvironmentVariables["MAINLAND_EXE_SELF_TEST"] = "1"' in workflow
    assert "WaitForExit(30000)" in workflow
    assert "$p.ExitCode -ne 0" in workflow
    assert "FROZEN_EXE_SELF_TEST_OK" in workflow


def test_package_chunking_uses_real_part_count_and_supports_twelve_parts():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'if [ "$parts_count" -gt 12 ]; then' in workflow
    assert "split -b 18m" in workflow
    assert "parts_count=${#parts[@]}" in workflow
    assert "parts=%s" in workflow
    assert "mainland-phase1-package-part-07" in workflow
    assert "mainland-phase1-package-part-08" in workflow
    assert "mainland-phase1-package-part-09" in workflow
    assert "mainland-phase1-package-part-10" in workflow
    assert "mainland-phase1-package-part-11" in workflow


def test_quotation_product_is_in_build_matrix_and_reportlab_is_declared():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    assert "报价单生成器" in workflow
    assert "MainlandQuotationGenerator" in workflow
    assert "reportlab" in requirements
