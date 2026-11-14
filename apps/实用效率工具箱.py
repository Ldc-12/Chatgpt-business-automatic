import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

TOOLS = [
    ("文件整理助手 Pro", "MainlandFileOrganizerPro.exe"),
    ("图片批量处理助手 Pro", "MainlandImageToolPro.exe"),
    ("PDF 批量工具 Pro", "MainlandPDFToolPro.exe"),
    ("自由职业催款管理工具", "MainlandFreelancerTool.exe"),
    ("轻量销售客户跟进工具", "MainlandSalesFollowupTool.exe"),
    ("求职申请管理 Pro", "MainlandJobTrackerPro.exe"),
    ("小微企业经营收支管理", "MainlandSmallBusinessFinance.exe"),
    ("会议行动项管理", "MainlandMeetingActions.exe"),
    ("SOP 项目执行管理", "MainlandSOPManager.exe"),
    ("小店库存盘点助手", "MainlandInventoryAssistant.exe"),
    ("食品批次与保质期追踪助手", "MainlandFoodBatchExpiryAssistant.exe"),
    ("门店食品安全巡检与整改闭环助手", "MainlandFoodSafetyInspectionAssistant.exe"),
    ("供应商采购比价助手", "MainlandPurchaseCompare.exe"),
    ("报价单生成器", "MainlandQuotationGenerator.exe"),
    ("费用报销管理助手", "MainlandExpenseReimbursement.exe"),
    ("售后维修工单管理助手", "MainlandRepairWorkOrderManager.exe"),
    ("售后纠纷证据链管理助手", "MainlandAfterSalesEvidenceAssistant.exe"),
    ("门店排班考勤助手", "MainlandStoreScheduleAssistant.exe"),
    ("合同台账与到期提醒助手", "MainlandContractLedgerAssistant.exe"),
    ("装修工程签证与进度款管理助手", "MainlandConstructionSettlementAssistant.exe"),
    ("物业租金与押金管理助手", "MainlandRentalLedgerAssistant.exe"),
    ("设备维保巡检与保养计划助手", "MainlandEquipmentMaintenanceAssistant.exe"),
]


def application_directory():
    """Return the directory containing the launcher and sibling EXEs.

    PyInstaller one-file extracts __file__ into a temporary _MEIPASS folder.
    The packaged sibling tools remain beside sys.executable, not in _MEIPASS.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def self_test():
    assert len(TOOLS) == 22
    names = [name for name, _ in TOOLS]
    exes = [exe for _, exe in TOOLS]
    assert len(set(names)) == len(names)
    assert len(set(exes)) == len(exes)
    assert all(exe.lower().endswith(".exe") for exe in exes)
    if sys.stdout is not None:
        print("SELF_TEST_OK", flush=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("实用效率工具箱")
        self.geometry("780x720")
        self.resizable(False, False)
        ttk.Label(
            self, text="Windows 实用效率工具箱",
            font=("Microsoft YaHei UI", 20, "bold")
        ).pack(anchor="w", padx=24, pady=(22, 4))
        ttk.Label(
            self, text="双击即可启动已安装的工具；工具均为本地运行。",
            foreground="#666"
        ).pack(anchor="w", padx=24, pady=(0, 18))
        box = ttk.Frame(self, padding=18)
        box.pack(fill="both", expand=True)
        for name, exe in TOOLS:
            row = ttk.Frame(box)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=name, width=30).pack(side="left")
            ttk.Button(row, text="启动", command=lambda e=exe: self.launch(e)).pack(side="right")

    def launch(self, exe):
        path = application_directory() / exe
        if not path.exists():
            messagebox.showwarning("未找到工具", f"当前套餐未包含：{exe}")
        else:
            os.startfile(str(path))


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    App().mainloop()
