import csv, os, tkinter as tk
from tkinter import filedialog, messagebox, ttk
FIELDS=["client","invoice_id","amount","currency","due_date","status","last_contact","next_contact","notes"]
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Freelancer Invoice Follow-Up Kit"); self.geometry("1050x620"); self._build()
    def _build(self):
        bar=ttk.Frame(self); bar.pack(fill="x",padx=12,pady=10)
        for label,cmd in [("导入 CSV",self.import_csv),("新增",self.add_row),("删除选中",self.delete_row),("导出 CSV",self.export_csv),("逾期统计",self.stats)]:
            ttk.Button(bar,text=label,command=cmd).pack(side="left",padx=4)
        self.tree=ttk.Treeview(self,columns=FIELDS,show="headings")
        widths={"client":130,"invoice_id":100,"amount":90,"currency":70,"due_date":100,"status":100,"last_contact":100,"next_contact":100,"notes":200}
        for f in FIELDS: self.tree.heading(f,text=f); self.tree.column(f,width=widths[f],anchor="w")
        self.tree.pack(fill="both",expand=True,padx=12,pady=5)
        ttk.Label(self,text="可导入/导出 CSV；示例数据不会自动写入磁盘。",anchor="w").pack(fill="x",padx=12,pady=8)
    def add_row(self): self.tree.insert("", "end", values=[""]*len(FIELDS))
    def delete_row(self):
        for item in self.tree.selection(): self.tree.delete(item)
    def import_csv(self):
        p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not p:return
        try:
            with open(p,encoding="utf-8-sig",newline="") as f:
                r=csv.DictReader(f); missing=[x for x in FIELDS if x not in (r.fieldnames or [])]
                if missing: raise ValueError("缺少字段: "+", ".join(missing))
                for item in self.tree.get_children(): self.tree.delete(item)
                for row in r:self.tree.insert("", "end", values=[row.get(x,"") for x in FIELDS])
        except Exception as e: messagebox.showerror("导入失败",str(e))
    def export_csv(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        try:
            with open(p,"w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader()
                for item in self.tree.get_children(): w.writerow(dict(zip(FIELDS,self.tree.item(item,"values"))))
            messagebox.showinfo("完成","已导出: "+os.path.basename(p))
        except Exception as e: messagebox.showerror("导出失败",str(e))
    def stats(self):
        rows=[dict(zip(FIELDS,self.tree.item(i,"values"))) for i in self.tree.get_children()]
        overdue=[r for r in rows if r["status"].lower() in ("overdue","逾期")]
        total=sum(float(r["amount"]) for r in overdue if str(r["amount"]).replace(".","",1).isdigit())
        messagebox.showinfo("逾期统计",f"逾期发票: {len(overdue)}\n逾期金额合计: {total:g}")
if __name__=="__main__": App().mainloop()
