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
    "费用报销管理助手.py",
    "售后维修工单管理助手.py",
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


def test_package_chunking_uploads_only_actual_split_parts():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'if [ "$parts_count" -gt 15 ]; then' in workflow
    assert "Package exceeds the supported 15 x 18 MiB chunk size." in workflow
    assert "split -b 18m" in workflow
    assert "parts_count=${#parts[@]}" in workflow
    assert "parts=%s" in workflow
    assert "name: mainland-phase1-package-parts" in workflow
    assert "path: release/Phase1-Mainland-Windows-Tools.zip.part-*" in workflow
    assert "for part in 00 01 02" not in workflow
    assert "mainland-phase1-package-part-14" not in workflow


def test_quotation_product_is_in_build_matrix_and_reportlab_is_declared():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    assert "报价单生成器" in workflow
    assert "MainlandQuotationGenerator" in workflow
    assert "reportlab" in requirements


def test_expense_reimbursement_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'key: expense-reimbursement' in workflow
    assert 'product: "费用报销管理助手"' in workflow
    assert "tests/test_mainland_expense_reimbursement.py" in workflow
    assert "MainlandExpenseReimbursement" in workflow
    assert "15 款 Windows EXE（14 款业务工具及工具箱启动器）" in workflow
    assert "费用报销管理助手.json" in workflow


def test_mainland_windows_workflow_runs_push_builds_on_main_and_feature_branches():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'push:\n    branches: [main, "feat/**"]' in workflow
    assert "pull_request:" in workflow


def test_internal_release_status_updates_do_not_trigger_windows_rebuilds():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    triggers = workflow.split("jobs:", 1)[0]
    assert '"docs/RELEASE_STATUS.md"' not in triggers


def test_repair_work_order_product_is_in_build_matrix_and_customer_package():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "mainland-exe.yml").read_text(encoding="utf-8")
    assert 'key: repair-work-order' in workflow
    assert 'product: "售后维修工单管理助手"' in workflow
    assert "tests/test_mainland_repair_work_orders.py" in workflow
    assert "MainlandRepairWorkOrderManager" in workflow
    assert "15 款 Windows EXE（14 款业务工具及工具箱启动器）" in workflow
    assert "售后维修工单管理助手.json" in workflow
    launcher = (root / "apps" / "实用效率工具箱.py").read_text(encoding="utf-8")
    assert "MainlandRepairWorkOrderManager.exe" in launcher
    assert "assert len(TOOLS) == 14" in launcher
