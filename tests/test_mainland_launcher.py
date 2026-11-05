from pathlib import Path


def test_launcher_lists_every_business_exe():
    source = Path("apps/实用效率工具箱.py").read_text(encoding="utf-8")
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
    for executable in expected:
        assert executable in source
    assert "assert len(TOOLS) == 13" in source
