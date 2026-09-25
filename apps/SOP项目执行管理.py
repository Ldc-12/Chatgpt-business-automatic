import csv,json,os,sys,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from src.license import require_license

FIELDS=["项目","SOP名称","步骤","负责人","截止日期","状态","优先级","备注"];ST=["未开始","进行中","已完成","阻塞"];PR=["高","中","低"]
class App:
 def __init__(self,root):
  self.root=root;root.title("SOP项目执行管理｜大陆版");root.geometry("1200x700");self.rows=[];self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","sop.json");os.makedirs(os.path.dirname(self.path),exist_ok=True);self.load()
  b=tk.Frame(root);b.pack(fill="x",padx=8,pady=8)
  for t,c in [("新增步骤",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("项目统计",self.stats)]:tk.Button(b,text=t,command=c).pack(side="left",padx=3)
  self.q=tk.StringVar();tk.Label(b,text="搜索").pack(side="left",padx=(20,3));tk.Entry(b,textvariable=self.q,width=28).pack(side="left");self.q.trace_add("write",lambda *_:self.refresh())
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
  w=tk.Toplevel(self.root);v={f:tk.StringVar(value=(r or {}).get(f,"")) for f in FIELDS}
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
  total=len(self.rows);done=sum(r.get("状态")=="已完成" for r in self.rows);block=sum(r.get("状态")=="阻塞" for r in self.rows);rate=done/total*100 if total else 0
  messagebox.showinfo("SOP统计",f"步骤：{total}\n已完成：{done}\n阻塞：{block}\n完成率：{rate:.1f}%")
def self_test():assert "SOP名称" in FIELDS and len(ST)==4;print("SELF_TEST_OK")
if __name__ == "__main__":
    require_license("SOP项目执行管理")
    if "--self-test" in sys.argv:
        self_test()
    else:
        App(tk.Tk()).root.mainloop()
