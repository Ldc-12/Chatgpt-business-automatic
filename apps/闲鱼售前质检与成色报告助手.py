"""Tkinter desktop UI for the offline Xianyu pre-sale condition report tool."""
import os, sys, tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license
from src.xianyu_condition_report import FIELDS, FUNCTION_VALUES, GRADE_VALUES, MULTILINE_FIELDS, PRODUCT, ConditionStore, default_data_path, disclosure_text, generate_report_pdf, generate_batch_reports_zip, self_test

DISPLAY_COLUMNS=("商品编号","商品名称","品类","成色等级","功能检测结论","检测日期","建议售价")


class App:
    def __init__(self, root):
        self.root=root; root.title("闲鱼售前质检与成色报告助手｜大陆离线版"); root.geometry("1280x760")
        self.store=ConditionStore(default_data_path())
        toolbar=ttk.Frame(root,padding=8); toolbar.pack(fill="x")
        actions=[("新增记录",self.add),("编辑记录",self.edit),("删除记录",self.delete),("导入 CSV",self.import_csv),("导出 CSV",self.export_csv),("生成质检 PDF",self.export_pdf),("批量导出报告包",self.export_batch_pdf),("复制披露文案",self.copy_disclosure),("备份",self.backup),("恢复备份",self.restore)]
        for label,action in actions: ttk.Button(toolbar,text=label,command=action).pack(side="left",padx=2)
        search=ttk.Frame(root,padding=(8,0,8,6)); search.pack(fill="x")
        ttk.Label(search,text="搜索商品编号、名称、品类、型号或瑕疵：").pack(side="left")
        self.search_var=tk.StringVar(); entry=ttk.Entry(search,textvariable=self.search_var,width=48); entry.pack(side="left",padx=6); entry.bind("<KeyRelease>",lambda _event:self.refresh())
        area=ttk.Frame(root,padding=(8,0,8,4)); area.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(area,columns=DISPLAY_COLUMNS,show="headings",selectmode="extended")
        for column,width in zip(DISPLAY_COLUMNS,(125,190,100,105,120,105,100)):
            self.tree.heading(column,text=column); self.tree.column(column,width=width,minwidth=75,stretch=True)
        yscroll=ttk.Scrollbar(area,orient="vertical",command=self.tree.yview); self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0,column=0,sticky="nsew"); yscroll.grid(row=0,column=1,sticky="ns"); area.rowconfigure(0,weight=1); area.columnconfigure(0,weight=1)
        self.status=tk.StringVar(); ttk.Label(root,textvariable=self.status,anchor="w",padding=8).pack(fill="x"); self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children()); query=self.search_var.get().strip().casefold()
        rows=[row for row in self.store.rows if not query or query in " ".join(str(row.get(k,"")) for k in FIELDS).casefold()]
        rows.sort(key=lambda row:(row["检测日期"],row["商品编号"].casefold()),reverse=True)
        for row in rows: self.tree.insert("","end",iid=row["记录编号"],values=tuple(row[field] for field in DISPLAY_COLUMNS))
        pending=sum(1 for row in self.store.rows if row["功能检测结论"]=="未完成检测" or row["成色等级"]=="待检测")
        self.status.set(f"显示：{len(rows)}/{len(self.store.rows)}｜待完成检测：{pending}｜本地数据：{self.store.path}")

    def selected_rows(self):
        selected=set(self.tree.selection())
        return [row for row in self.store.rows if row["记录编号"] in selected]

    def selected_row(self):
        rows=self.selected_rows()
        return rows[0] if rows else None

    def form(self, existing=None):
        values={field:(existing or {}).get(field,"") for field in FIELDS}
        if not existing: values.update({"检测日期":date.today().isoformat(),"成色等级":"待检测","功能检测结论":"未完成检测"})
        window=tk.Toplevel(self.root); window.title("编辑质检记录" if existing else "新增质检记录"); window.geometry("1040x780"); window.transient(self.root); window.grab_set()
        canvas=tk.Canvas(window,highlightthickness=0); scrollbar=ttk.Scrollbar(window,orient="vertical",command=canvas.yview); frame=ttk.Frame(canvas,padding=14)
        frame.bind("<Configure>",lambda _event:canvas.configure(scrollregion=canvas.bbox("all"))); canvas.create_window((0,0),window=frame,anchor="nw"); canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left",fill="both",expand=True); scrollbar.pack(side="right",fill="y"); frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)
        variables={}; text_widgets={}; fields=[field for field in FIELDS if field!="记录编号"]
        for index,field in enumerate(fields):
            row_index,group=divmod(index,2); label_col=group*2; ttk.Label(frame,text=field).grid(row=row_index,column=label_col,sticky="e",padx=7,pady=5)
            if field=="成色等级":
                variable=tk.StringVar(value=values[field]); widget=ttk.Combobox(frame,textvariable=variable,values=GRADE_VALUES,state="readonly",width=35); variables[field]=variable
            elif field=="功能检测结论":
                variable=tk.StringVar(value=values[field]); widget=ttk.Combobox(frame,textvariable=variable,values=FUNCTION_VALUES,state="readonly",width=35); variables[field]=variable
            elif field in MULTILINE_FIELDS:
                widget=tk.Text(frame,width=42,height=3,wrap="word"); widget.insert("1.0",values[field]); text_widgets[field]=widget
            else:
                variable=tk.StringVar(value=values[field]); widget=ttk.Entry(frame,textvariable=variable,width=42); variables[field]=variable
            widget.grid(row=row_index,column=label_col+1,sticky="ew",padx=7,pady=5)
        ttk.Label(frame,text="只记录序列号尾号（最多 6 位），不要录入完整序列号。功能检查、瑕疵和维修史应如实填写；空白不代表检测通过。",wraplength=900,foreground="#555").grid(row=(len(fields)+1)//2,column=0,columnspan=4,sticky="w",padx=7,pady=10)
        def save():
            row={field:variable.get() for field,variable in variables.items()}
            for field,widget in text_widgets.items(): row[field]=widget.get("1.0","end-1c")
            try:
                if existing: self.store.update(existing["记录编号"],row)
                else: self.store.add(row)
                self.refresh(); window.destroy()
            except (ValueError,OSError) as exc: messagebox.showerror("保存失败",str(exc),parent=window)
        ttk.Button(frame,text="保存记录",command=save).grid(row=(len(fields)+1)//2+1,column=0,columnspan=4,pady=12)

    def add(self): self.form()
    def edit(self):
        row=self.selected_row()
        if row: self.form(row)
    def delete(self):
        row=self.selected_row()
        if row and messagebox.askyesno("确认删除","删除所选质检记录？"):
            try: self.store.delete(row["记录编号"]); self.refresh()
            except (ValueError,OSError) as exc: messagebox.showerror("删除失败",str(exc))
    def import_csv(self):
        path=filedialog.askopenfilename(filetypes=[("CSV 文件","*.csv")])
        if path:
            try:
                count=self.store.import_csv(path); self.refresh(); messagebox.showinfo("导入完成",f"整批导入 {count} 条质检记录")
            except (ValueError,OSError) as exc: messagebox.showerror("导入失败",str(exc))
    def export_csv(self):
        path=filedialog.asksaveasfilename(initialfile="闲鱼售前质检记录.csv",defaultextension=".csv",filetypes=[("CSV 文件","*.csv")])
        if path:
            try:
                count=self.store.export_csv(path); messagebox.showinfo("导出完成",f"已导出 {count} 行（UTF-8 BOM，公式安全处理）")
            except (ValueError,OSError) as exc: messagebox.showerror("导出失败",str(exc))
    def export_pdf(self):
        row=self.selected_row()
        if not row: messagebox.showwarning("请选择商品","请先选择一条质检记录"); return
        path=filedialog.asksaveasfilename(initialfile=f"{row['商品编号']}-质检报告.pdf",defaultextension=".pdf",filetypes=[("PDF 文件","*.pdf")])
        if path:
            try: generate_report_pdf(row,Path(path)); messagebox.showinfo("报告已生成",f"PDF 报告已保存：\n{path}")
            except Exception as exc: messagebox.showerror("生成失败",str(exc))

    def export_batch_pdf(self):
        rows=self.selected_rows()
        if not rows: messagebox.showwarning("请选择商品","请按 Ctrl 或 Shift 多选至少一条质检记录"); return
        path=filedialog.asksaveasfilename(initialfile=f"闲鱼质检报告包-{len(rows)}件.zip",defaultextension=".zip",filetypes=[("ZIP 报告包","*.zip")])
        if path:
            try:
                generate_batch_reports_zip(rows,Path(path))
                messagebox.showinfo("报告包已生成",f"已导出 {len(rows)} 份 PDF，并附带 CSV 索引与 SHA256 清单：\\n{path}")
            except Exception as exc: messagebox.showerror("批量导出失败",str(exc))

    def copy_disclosure(self):
        row=self.selected_row()
        if not row: messagebox.showwarning("请选择商品","请先选择一条质检记录"); return
        try:
            self.root.clipboard_clear(); self.root.clipboard_append(disclosure_text(row)); messagebox.showinfo("已复制","商品披露文案已复制，可粘贴到商品描述中")
        except tk.TclError as exc: messagebox.showerror("复制失败",str(exc))
    def backup(self):
        path=filedialog.asksaveasfilename(initialfile="闲鱼售前质检台账备份.json",defaultextension=".json",filetypes=[("JSON 备份","*.json")])
        if path:
            try: self.store.backup(Path(path)); messagebox.showinfo("备份完成","已生成带 SHA256 校验的本地备份")
            except (ValueError,OSError) as exc: messagebox.showerror("备份失败",str(exc))
    def restore(self):
        path=filedialog.askopenfilename(filetypes=[("JSON 备份","*.json")])
        if path and messagebox.askyesno("确认恢复","恢复会替换当前本地质检台账，建议先备份。继续？"):
            try:
                count=self.store.restore(Path(path)); self.refresh(); messagebox.showinfo("恢复完成",f"已恢复 {count} 条记录")
            except (ValueError,OSError) as exc: messagebox.showerror("恢复失败",str(exc))


def main():
    require_license(PRODUCT); root=tk.Tk(); App(root); root.mainloop()


if __name__=="__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST")=="1":
        self_test(); os._exit(0)
    main()
