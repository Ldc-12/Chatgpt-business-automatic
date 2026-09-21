import csv,json,os,sys,datetime,tkinter as tk
from tkinter import ttk,filedialog,messagebox
FIELDS=["公司","职位","联系人","联系方式","招聘来源","阶段","期望薪资","面试日期","简历版本","备注"]
STAGES=["待申请","已申请","笔试","一面","二面","谈薪","Offer","入职","拒绝","放弃"]
def today(): return datetime.date.today().isoformat()
def num(x):
    try:return float(str(x).replace(",","").replace("，","").replace("￥","").strip() or 0)
    except:return 0
def due(x):
    try:return (datetime.date.fromisoformat(x)-datetime.date.today()).days
    except:return None
class App:
 def __init__(self,root):
  self.root=root;root.title("求职申请管理 Pro｜大陆版");root.geometry("1250x720");self.rows=[];self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","jobs.json");os.makedirs(os.path.dirname(self.path),exist_ok=True);self.load()
  top=tk.Frame(root);top.pack(fill="x",padx=8,pady=8)
  for t,c in [("新增",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("统计",self.stats),("面试话术",self.script)]:tk.Button(top,text=t,command=c).pack(side="left",padx=3)
  tk.Label(top,text="搜索").pack(side="left",padx=(20,3));self.q=tk.StringVar();tk.Entry(top,textvariable=self.q,width=25).pack(side="left");self.q.trace_add("write",lambda *_:self.refresh())
  self.stage=tk.StringVar(value="全部");ttk.Combobox(top,textvariable=self.stage,values=["全部"]+STAGES,width=10,state="readonly").pack(side="left",padx=5);self.stage.trace_add("write",lambda *_:self.refresh())
  self.tree=ttk.Treeview(root,columns=FIELDS,show="headings");[self.tree.heading(f,text=f) or self.tree.column(f,width=110) for f in FIELDS];self.tree.pack(fill="both",expand=True,padx=8)
  self.refresh()
 def load(self):
  try:self.rows=json.load(open(self.path,encoding="utf-8"))
  except:self.rows=[]
 def save(self):json.dump(self.rows,open(self.path,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
 def refresh(self):
  self.tree.delete(*self.tree.get_children());q=self.q.get().lower();st=self.stage.get()
  for i,r in enumerate(self.rows):
   if q and q not in " ".join(r.get(f,"") for f in FIELDS).lower():continue
   if st!="全部" and r.get("阶段")!=st:continue
   self.tree.insert("", "end",iid=str(i),values=[r.get(f,"") for f in FIELDS])
 def form(self,r=None):
  w=tk.Toplevel(self.root);w.title("求职记录");vs={f:tk.StringVar(value=(r or {}).get(f,"")) for f in FIELDS}
  for i,f in enumerate(FIELDS):tk.Label(w,text=f).grid(row=i,column=0,padx=8,pady=4,sticky="e");(ttk.Combobox(w,textvariable=vs[f],values=STAGES,state="readonly") if f=="阶段" else tk.Entry(w,textvariable=vs[f],width=40)).grid(row=i,column=1,padx=8,pady=4)
  def ok():
   if not vs["公司"].get() or not vs["职位"].get():return messagebox.showwarning("提示","公司和职位不能为空")
   data={f:vs[f].get().strip() for f in FIELDS};data["期望薪资"]=str(num(data["期望薪资"]));self.rows.append(data) if r is None else self.rows.__setitem__(self.tree.focus() and int(self.tree.focus()) or 0,data);self.save();self.refresh();w.destroy()
  tk.Button(w,text="保存",command=ok).grid(row=len(FIELDS),columnspan=2,pady=8)
 def add(self):self.form()
 def edit(self):
  s=self.tree.selection()
  if s:self.form(self.rows[int(s[0])])
 def delete(self):
  s=self.tree.selection()
  if s and messagebox.askyesno("确认","删除选中记录？"):self.rows.pop(int(s[0]));self.save();self.refresh()
 def imp(self):
  p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
  if not p:return
  with open(p,encoding="utf-8-sig",newline="") as f:self.rows=list(csv.DictReader(f))
  self.save();self.refresh()
 def exp(self):
  p=filedialog.asksaveasfilename(defaultextension=".csv")
  if not p:return
  with open(p,"w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(self.rows)
 def stats(self):messagebox.showinfo("求职统计",f"总申请：{len(self.rows)}\n已获Offer：{sum(r.get('阶段')=='Offer' for r in self.rows)}\n面试中：{sum(r.get('阶段') in ('一面','二面','笔试') for r in self.rows)}\n待处理：{sum(r.get('阶段') in ('待申请','已申请') for r in self.rows)}")
 def script(self):
  messagebox.showinfo("面试/跟进话术","您好，我是XXX，应聘【职位】。想确认一下目前招聘进度及后续安排，如需补充材料我可以随时提供，谢谢！")
def self_test(): assert "公司" in FIELDS and num("￥12,000")==12000 and due(today())==0;print("SELF_TEST_OK")
if __name__=="__main__":
 if "--self-test" in sys.argv:self_test()
 else:App(tk.Tk()).root.mainloop()
