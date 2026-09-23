import csv, datetime as dt, json, os, sys, tkinter as tk
from tkinter import filedialog, messagebox, ttk

FIELDS=["客户","联系人","电话/微信","来源","阶段","预计金额","下次跟进","负责人","备注"]
STAGES=["新线索","已联系","需求确认","报价中","谈判中","成交","暂停","流失"]

def today(): return dt.date.today().isoformat()
def num(v):
    s=str(v).strip().replace(",","").replace("，","").replace("￥","").replace("¥","")
    return float(s) if s else 0.0
def due(v):
    try:return (dt.date.fromisoformat(str(v))-dt.date.today()).days
    except:return None

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("轻量销售客户跟进工具｜大陆版"); self.geometry("1280x730"); self.minsize(1100,650)
        self.rows=[]; self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","sales.json")
        self.load(); self.ui(); self.refresh()
    def ui(self):
        bar=ttk.Frame(self); bar.pack(fill="x",padx=10,pady=8)
        for t,c in [("新增",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("销售统计",self.stats),("跟进话术",self.script)]:
            ttk.Button(bar,text=t,command=c).pack(side="left",padx=3)
        ttk.Label(bar,text="搜索").pack(side="left",padx=(18,4)); self.q=tk.StringVar(); ttk.Entry(bar,textvariable=self.q,width=24).pack(side="left"); self.q.trace_add("write",lambda *_:self.refresh())
        self.f=tk.StringVar(value="全部"); ttk.Combobox(bar,textvariable=self.f,values=["全部"]+STAGES+["7天内跟进"],state="readonly",width=12).pack(side="left",padx=6); self.f.trace_add("write",lambda *_:self.refresh())
        frame=ttk.Frame(self); frame.pack(fill="both",expand=True,padx=10)
        self.tree=ttk.Treeview(frame,columns=FIELDS,show="headings",selectmode="extended")
        for f,w in zip(FIELDS,[120,100,130,80,90,100,105,90,260]): self.tree.heading(f,text=f); self.tree.column(f,width=w,anchor="w")
        self.tree.pack(side="left",fill="both",expand=True); self.tree.bind("<Double-1>",lambda e:self.edit())
        sb=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview); sb.pack(side="right",fill="y"); self.tree.configure(yscrollcommand=sb.set)
        self.status=tk.StringVar(); ttk.Label(self,textvariable=self.status,anchor="w").pack(fill="x",padx=10,pady=7)
        ttk.Label(self,text="数据默认保存在本机 LOCALAPPDATA，可随时导出 CSV 备份。",anchor="w").pack(fill="x",padx=10,pady=(0,8))
    def load(self):
        try:
            with open(self.path,encoding="utf-8") as f:self.rows=json.load(f)
        except:self.rows=[]
    def save(self):
        os.makedirs(os.path.dirname(self.path),exist_ok=True)
        with open(self.path,"w",encoding="utf-8") as f:json.dump(self.rows,f,ensure_ascii=False,indent=2)
    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        q=self.q.get().strip().lower(); f=self.f.get(); n=0
        for r in self.rows:
            if q and q not in " ".join(str(r.get(x,"")) for x in FIELDS).lower():continue
            if f in STAGES and r.get("阶段")!=f:continue
            d=due(r.get("下次跟进",""))
            if f=="7天内跟进" and (d is None or not 0<=d<=7):continue
            self.tree.insert("", "end",values=[r.get(x,"") for x in FIELDS]); n+=1
        self.status.set(f"共 {len(self.rows)} 条客户｜当前显示 {n} 条")
    def dialog(self,old=None):
        w=tk.Toplevel(self); w.title("客户资料"); w.transient(self); w.grab_set(); old=old or {}; vs=[]
        for i,f in enumerate(FIELDS):
            ttk.Label(w,text=f).grid(row=i,column=0,padx=10,pady=5,sticky="w"); v=tk.StringVar(value=str(old.get(f,""))); vs.append(v)
            if f=="阶段":ttk.Combobox(w,textvariable=v,values=STAGES,state="readonly",width=34).grid(row=i,column=1,padx=10,pady=5)
            else:ttk.Entry(w,textvariable=v,width=36).grid(row=i,column=1,padx=10,pady=5)
        result=[None]
        def ok():
            d={f:v.get().strip() for f,v in zip(FIELDS,vs)}
            if not d["客户"]:messagebox.showwarning("提示","客户名称不能为空",parent=w);return
            try:num(d["预计金额"])
            except:messagebox.showwarning("提示","预计金额格式错误",parent=w);return
            result[0]=d;w.destroy()
        ttk.Button(w,text="保存",command=ok).grid(row=len(FIELDS),column=0,pady=12); ttk.Button(w,text="取消",command=w.destroy).grid(row=len(FIELDS),column=1,pady=12,sticky="e")
        w.wait_window(); return result[0]
    def index(self):
        s=self.tree.selection()
        if not s:return None
        vals=list(self.tree.item(s[0],"values"))
        for i,r in enumerate(self.rows):
            if [r.get(x,"") for x in FIELDS]==vals:return i
        return None
    def add(self):
        d=self.dialog({"阶段":"新线索","下次跟进":today()})
        if d:self.rows.append(d);self.save();self.refresh()
    def edit(self):
        i=self.index()
        if i is None:messagebox.showinfo("提示","请先选择客户");return
        d=self.dialog(self.rows[i])
        if d:self.rows[i]=d;self.save();self.refresh()
    def delete(self):
        s=self.tree.selection()
        if not s:return
        vals=[list(self.tree.item(x,"values")) for x in s]
        self.rows=[r for r in self.rows if [r.get(x,"") for x in FIELDS] not in vals];self.save();self.refresh()
    def imp(self):
        p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not p:return
        try:
            with open(p,encoding="utf-8-sig",newline="") as f:
                rd=csv.DictReader(f); missing=[x for x in FIELDS if x not in (rd.fieldnames or [])]
                if missing:raise ValueError("缺少字段："+",".join(missing))
                self.rows=[{x:r.get(x,"") for x in FIELDS} for r in rd]
            self.save();self.refresh()
        except Exception as e:messagebox.showerror("导入失败",str(e))
    def exp(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        with open(p,"w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(self.rows)
        messagebox.showinfo("完成","已导出客户数据")
    def stats(self):
        total=sum(num(r.get("预计金额","")) for r in self.rows); won=sum(num(r.get("预计金额","")) for r in self.rows if r.get("阶段")=="成交")
        d7=sum(1 for r in self.rows if due(r.get("下次跟进","")) is not None and 0<=due(r.get("下次跟进",""))<=7)
        messagebox.showinfo("销售统计",f"客户数：{len(self.rows)}\n预计总金额：￥{total:,.2f}\n已成交金额：￥{won:,.2f}\n未来7天需跟进：{d7}")
    def script(self):
        i=self.index()
        if i is None:messagebox.showinfo("提示","请先选择客户");return
        r=self.rows[i]; text=f"您好，{r['联系人'] or r['客户']}，我是负责跟进{r['客户']}的。想确认一下目前项目进展，如果需要补充资料或调整报价，我这边可以马上配合。"
        self.clipboard_clear();self.clipboard_append(text);self.update();messagebox.showinfo("跟进话术","已复制到剪贴板")
def self_test():
    assert num("￥1,200")==1200
    assert today()
    assert "客户" in FIELDS
if __name__ == "__main__":
    require_license("轻量销售客户跟进工具")
    if "--self-test" in sys.argv:self_test()
        else:App().mainloop()
    