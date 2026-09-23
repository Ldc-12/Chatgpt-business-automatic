import csv,json,os,sys,datetime,tkinter as tk
from tkinter import ttk,filedialog,messagebox
FIELDS=["日期","类型","客户/供应商","项目","金额","收付款方式","状态","备注"];TYPES=["收入","支出","应收","应付"];ST=["已完成","待处理","部分完成","逾期"]
def num(x):
 try:return float(str(x).replace(",","").replace("，","").replace("￥","").strip() or 0)
 except:return 0
def today():return datetime.date.today().isoformat()
class App:
 def __init__(self,root):
  self.root=root;root.title("小微企业经营收支管理｜大陆版");root.geometry("1200x700");self.rows=[];self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","finance.json");os.makedirs(os.path.dirname(self.path),exist_ok=True);self.load()
  bar=tk.Frame(root);bar.pack(fill="x",padx=8,pady=8)
  for t,c in [("新增",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("经营统计",self.stats)]:tk.Button(bar,text=t,command=c).pack(side="left",padx=3)
  self.q=tk.StringVar();tk.Label(bar,text="搜索").pack(side="left",padx=(20,3));tk.Entry(bar,textvariable=self.q,width=25).pack(side="left");self.q.trace_add("write",lambda *_:self.refresh())
  self.tree=ttk.Treeview(root,columns=FIELDS,show="headings");[self.tree.heading(f,text=f) or self.tree.column(f,width=120) for f in FIELDS];self.tree.pack(fill="both",expand=True,padx=8);self.refresh()
 def load(self):
  try:self.rows=json.load(open(self.path,encoding="utf-8"))
  except:self.rows=[]
 def save(self):json.dump(self.rows,open(self.path,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
 def refresh(self):
  self.tree.delete(*self.tree.get_children());q=self.q.get().lower()
  for i,r in enumerate(self.rows):
   if q and q not in " ".join(r.get(f,"") for f in FIELDS).lower():continue
   self.tree.insert("", "end",iid=str(i),values=[r.get(f,"") for f in FIELDS])
 def form(self,r=None):
  w=tk.Toplevel(self.root);w.title("经营记录");v={f:tk.StringVar(value=(r or {}).get(f,today() if f=="日期" else "")) for f in FIELDS}
  for i,f in enumerate(FIELDS):tk.Label(w,text=f).grid(row=i,column=0,padx=8,pady=4);(ttk.Combobox(w,textvariable=v[f],values=TYPES if f=="类型" else ST,state="readonly") if f in ("类型","状态") else tk.Entry(w,textvariable=v[f],width=38)).grid(row=i,column=1,padx=8,pady=4)
  def ok():
   d={f:v[f].get().strip() for f in FIELDS};d["金额"]=str(num(d["金额"]));idx=self.tree.focus()
   if r is None:self.rows.append(d)
   elif idx:self.rows[int(idx)]=d
   self.save();self.refresh();w.destroy()
  tk.Button(w,text="保存",command=ok).grid(row=len(FIELDS),columnspan=2,pady=8)
 def add(self):self.form()
 def edit(self):
  s=self.tree.selection()
  if s:self.form(self.rows[int(s[0])])
 def delete(self):
  s=self.tree.selection()
  if s and messagebox.askyesno("确认","删除？"):self.rows.pop(int(s[0]));self.save();self.refresh()
 def imp(self):
  p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
  if p:
   with open(p,encoding="utf-8-sig",newline="") as f:self.rows=list(csv.DictReader(f))
   self.save();self.refresh()
 def exp(self):
  p=filedialog.asksaveasfilename(defaultextension=".csv")
  if p:
   with open(p,"w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(self.rows)
 def stats(self):
  inc=sum(num(r.get("金额")) for r in self.rows if r.get("类型")=="收入");out=sum(num(r.get("金额")) for r in self.rows if r.get("类型")=="支出");ar=sum(num(r.get("金额")) for r in self.rows if r.get("类型")=="应收" and r.get("状态")!="已完成");ap=sum(num(r.get("金额")) for r in self.rows if r.get("类型")=="应付" and r.get("状态")!="已完成")
  messagebox.showinfo("经营统计",f"收入：￥{inc:,.2f}\n支出：￥{out:,.2f}\n经营结余：￥{inc-out:,.2f}\n未收：￥{ar:,.2f}\n未付：￥{ap:,.2f}")
def self_test():assert num("￥1,200")==1200 and "金额" in FIELDS;print("SELF_TEST_OK")
if __name__ == "__main__":
    require_license("小微企业经营收支管理")
    if "--self-test" in sys.argv:self_test()
     else:App(tk.Tk()).root.mainloop()
    