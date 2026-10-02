import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

TOOLS = [
("文件整理助手 Pro","MainlandFileOrganizerPro.exe"),
("图片批量处理助手 Pro","MainlandImageToolPro.exe"),
("PDF 批量工具 Pro","MainlandPDFToolPro.exe"),
("自由职业催款管理工具","MainlandFreelancerTool.exe"),
("轻量销售客户跟进工具","MainlandSalesFollowupTool.exe"),
("求职申请管理 Pro","MainlandJobTrackerPro.exe"),
("小微企业经营收支管理","MainlandSmallBusinessFinance.exe"),
("会议行动项管理","MainlandMeetingActions.exe"),
("SOP 项目执行管理","MainlandSOPManager.exe"),
]

def self_test():
    assert len(TOOLS) == 9
    names = [name for name, _ in TOOLS]
    exes = [exe for _, exe in TOOLS]
    assert len(set(names)) == len(names)
    assert len(set(exes)) == len(exes)
    assert all(exe.lower().endswith(".exe") for exe in exes)
    print("SELF_TEST_OK")

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("实用效率工具箱"); self.geometry("700x560"); self.resizable(False,False)
        ttk.Label(self,text="Windows 实用效率工具箱",font=("Microsoft YaHei UI",20,"bold")).pack(anchor="w",padx=24,pady=(22,4))
        ttk.Label(self,text="双击即可启动已安装的工具；工具均为本地运行。",foreground="#666").pack(anchor="w",padx=24,pady=(0,18))
        box=ttk.Frame(self,padding=18); box.pack(fill="both",expand=True)
        for name,exe in TOOLS:
            row=ttk.Frame(box); row.pack(fill="x",pady=5)
            ttk.Label(row,text=name,width=28).pack(side="left")
            ttk.Button(row,text="启动",command=lambda e=exe:self.launch(e)).pack(side="right")
    def launch(self,exe):
        p=Path(__file__).with_name(exe)
        if not p.exists(): messagebox.showwarning("未找到工具",f"当前套餐未包含：{exe}")
        else: os.startfile(str(p))

if __name__=="__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        App().mainloop()
