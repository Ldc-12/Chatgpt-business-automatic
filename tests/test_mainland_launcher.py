import importlib.util
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "实用效率工具箱.py"
spec = importlib.util.spec_from_file_location("mainland_toolbox", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_launcher_lists_every_business_exe():
    expected = [
        "MainlandFileOrganizerPro.exe",
        "MainlandImageToolPro.exe",
        "MainlandPDFToolPro.exe",
        "MainlandFreelancerTool.exe",
        "MainlandSalesFollowupTool.exe",
        "MainlandJobTrackerPro.exe",
        "MainlandSmallBusinessFinance.exe",
        "MainlandMeetingActions.exe",
        "MainlandSOPManager.exe",
        "MainlandInventoryAssistant.exe",
        "MainlandPurchaseCompare.exe",
        "MainlandQuotationGenerator.exe",
        "MainlandExpenseReimbursement.exe",
    ]
    actual = [exe for _, exe in module.TOOLS]
    assert actual == expected
    assert len(module.TOOLS) == 13


def test_frozen_launcher_resolves_sibling_exes_next_to_launcher(tmp_path, monkeypatch):
    executable = tmp_path / "MainlandEfficiencyToolbox.exe"
    monkeypatch.setattr(module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(module.sys, "executable", str(executable))
    assert module.application_directory() == tmp_path


def test_source_launcher_uses_source_directory(monkeypatch):
    monkeypatch.delattr(module.sys, "frozen", raising=False)
    assert module.application_directory() == Path(module.__file__).resolve().parent


def test_launcher_manual_lists_all_thirteen_tools_and_same_folder_rule():
    manual = (Path(__file__).resolve().parents[1] / "docs" / "manuals" / "00-实用效率工具箱-用户说明书.md").read_text(encoding="utf-8")
    for name, _ in module.TOOLS:
        assert name in manual
    assert "同一目录" in manual
