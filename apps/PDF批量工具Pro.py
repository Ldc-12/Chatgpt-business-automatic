import sys, os, tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pypdf import PdfReader, PdfWriter
APP="PDF批量工具 Pro 1.1"
def merge(files,out):
    w=PdfWriter()
    for f in files:
        for page in PdfReader(str(f)).pages:w.add_page(page)
    with open(out,"wb") as h:w.write(h)
def split(src,outdir):
    r=PdfReader(str(src)); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True); paths=[]
    for i,page in enumerate(r.pages,1):
        w=PdfWriter(); w.add_page(page); p=outdir/f"{Path(src).stem}_{i:03d}.pdf"
        with open(p,"wb") as h:w.write(h)
        paths.append(p)
    return paths
def self_test():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); a=p/"a.pdf"; b=p/"b.pdf"
        for f,n in [(a,2),(b,1)]:
            w=PdfWriter(); [w.add_blank_page(300,400) for _ in range(n)]; open(f,"wb").write(b"") if False else None
            with open(f,"wb") as h:w.write(h)
        out=p/"merged.pdf"; merge([a,b],out); assert len(PdfReader(out).pages)==3; assert len(split(a,p/"parts"))==2
    print("SELF-TEST OK")
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("860x600"); self.folder=tk.StringVar(); self.ui()
    def ui(self):
        r=ttk.Frame(self,padding=20); r.pack(fill="both",expand=True); ttk.Label(r,text=APP,font=("Microsoft YaHei UI",18,"bold")).pack(anchor="w"); ttk.Label(r,text="批量合并｜批量拆分｜页数预览｜自动排除历史输出文件",foreground="#666").pack(anchor="w",pady=(3,18))
        box=ttk.LabelFrame(r,text="PDF 文件夹",padding=10); box.pack(fill="x"); row=ttk.Frame(box); row.pack(fill="x"); ttk.Entry(row,textvariable=self.folder).pack(side="left",fill="x",expand=True); ttk.Button(row,text="选择",command=self.choose).pack(side="left",padx=8); ttk.Button(row,text="扫描",command=self.scan).pack(side="left")
        bar=ttk.Frame(r); bar.pack(fill="x",pady=12); ttk.Button(bar,text="合并全部 PDF",command=self.merge_all).pack(side="left"); ttk.Button(bar,text="全部拆分成单页",command=self.split_all).pack(side="left",padx=8); ttk.Button(bar,text="打开文件夹",command=self.open).pack(side="left",padx=8)
        self.tree=ttk.Treeview(r,columns=("name","pages","size"),show="headings");
        for c,t,w in [("name","文件",400),("pages","页数",100),("size","大小",120)]:self.tree.heading(c,text=t);self.tree.column(c,width=w,anchor="w")
        self.tree.pack(fill="both",expand=True); self.info=ttk.Label(r,text="请选择文件夹"); self.info.pack(anchor="w",pady=(8,0))
    def choose(self):
        p=filedialog.askdirectory(title="选择 PDF 文件夹");
        if p:self.folder.set(p);self.scan()
    def files(self):
        p=Path(self.folder.get()); return [f for f in sorted(p.glob("*.pdf")) if f.name not in {"合并结果.pdf"} and not f.parent.name=="拆分结果"]
    def scan(self):
        self.tree.delete(*self.tree.get_children()); p=Path(self.folder.get()); n=0
        if not p.is_dir():return
        for f in self.files():
            try:pages=len(PdfReader(str(f)).pages)
            except Exception:pages="错误"
            self.tree.insert("","end",values=(f.name,pages,f"{f.stat().st_size/1024:.0f} KB"));n+=1
        self.info.config(text=f"发现 {n} 个可处理 PDF")
    def merge_all(self):
        fs=self.files()
        if not fs:return messagebox.showwarning("提示","没有找到可合并的 PDF")
        out=Path(self.folder.get())/"合并结果.pdf"
        if out.exists() and not messagebox.askyesno("覆盖确认","合并结果.pdf 已存在，是否覆盖？"):return
        try:merge(fs,out);messagebox.showinfo("完成",f"已合并 {len(fs)} 个 PDF，共 {len(PdfReader(out).pages)} 页")
        except Exception as e:messagebox.showerror("处理失败",str(e))
        self.scan()
    def split_all(self):
        fs=self.files()
        if not fs:return messagebox.showwarning("提示","没有找到 PDF")
        out=Path(self.folder.get())/"拆分结果"
        try:
            n=sum(len(split(f,out/f.stem)) for f in fs);messagebox.showinfo("完成",f"已拆分 {len(fs)} 个 PDF，共生成 {n} 页文件")
        except Exception as e:messagebox.showerror("处理失败",str(e))
    def open(self):
        p=self.folder.get()
        if os.path.isdir(p) and hasattr(os,"startfile"):os.startfile(p)
if __name__=="__main__":
    if "--self-test" in sys.argv:self_test()
    else:App().mainloop()
