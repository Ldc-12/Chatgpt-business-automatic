import csv,json,os,sys,datetime,tkinter as tk
from tkinter import ttk,filedialog,messagebox
FIELDS=["会议日期","会议名称","行动项","负责人","截止日期","状态","优先级","备注"];ST=["未开始","进行中","已完成","延期"];PR=["高","中","低"]
def today():return datetime.date.today().isoformat()
def days(x):
 try:return (datetime.date.fromisoformat(x)-datetime.date.today()).days
 except:return None
class App:
 def __init__(self,root):
  self.root=root;root.title("会议行动项管理｜大陆版");root.geometry("1200x700");self.rows=[];self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","meetings.json");os.makedirs(os.path.dirname(self.path),exist_ok=True);self.load()
  b=tk.Frame(root);b.pack(fill="x",padx=8,pady=8)
  for t,c in [("新增",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("执行统计",self.stats),("提醒话术",self.script)]:tk.Button(b,text=t,command=c).pack(side="left",padx=3)
  self.q=tk.StringVar();tk.Label(b,text="搜索").pack(side="left",padx=(20,3));tk.Entry(b,textvariable=self.q,width=25).pack(side="left");self.q.trace_add("write",lambda *_:self.refresh())
  self.tree=ttk.Treeview(root,columns=FIELDS,show="headings");[self.tree.heading(f,text=f) or self.tree.column(f,width=125) for f in FIELDS];self.tree.pack(fill="both",expand=True,padx=8);self.refresh()
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
  w=tk.Toplevel(self.root);v={f:tk.StringVar(value=(r or {}).get(f,today() if f in ("会议日期","截止日期") else "")) for f in FIELDS}
  for i,f in enumerate(FIELDS):tk.Label(w,text=f).grid(row=i,column=0,padx=8,pady=4);(ttk.Combobox(w,textvariable=v[f],values=ST if f=="状态" else PR,state="readonly") if f in ("状态","优先级") else tk.Entry(w,textvariable=v[f],width=40)).grid(row=i,column=1,padx=8,pady=4)
  def ok():
   d={f:v[f].get().strip() for f in FIELDS};idx=self.tree.focus()
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
  overdue=sum(1 for r in self.rows if r.get("状态")!="已完成" and (days(r.get("截止日期")) is not None and days(r.get("截止日期"))<0));open_n=sum(r.get("状态")!="已完成" for r in self.rows)
  messagebox.showinfo("执行统计",f"行动项：{len(self.rows)}\n未完成：{open_n}\n已完成：{len(self.rows)-open_n}\n已逾期：{overdue}")
 def script(self):messagebox.showinfo("提醒话术","您好，提醒一下会议行动项【行动项】，截止日期为【截止日期】，请更新当前进度；如有困难请及时反馈，谢谢。")
def self_test():assert days(today())==0 and "负责人" in FIELDS;print("SELF_TEST_OK")
if __name__ == "__main__":
    require_license("会议行动项管理")
    if "--self-test" in sys.argv:
        self_test()
    else:
        App(tk.Tk()).root.mainloop()
