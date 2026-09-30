import os, sys, shutil, tempfile, json, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP = "文件整理助手 Pro 1.1"
CATS = {
    "图片": {".jpg",".jpeg",".png",".gif",".webp",".bmp",".tif",".tiff",".heic"},
    "视频": {".mp4",".mov",".avi",".mkv",".wmv",".flv",".webm"},
    "音频": {".mp3",".wav",".flac",".aac",".m4a",".ogg"},
    "文档": {".doc",".docx",".xls",".xlsx",".ppt",".pptx",".pdf",".txt",".csv",".md",".rtf"},
    "压缩包": {".zip",".rar",".7z",".tar",".gz",".bz2"},
    "程序": {".exe",".msi",".bat",".cmd",".ps1",".py",".js",".html",".css"},
}
def category(p):
    e=p.suffix.lower()
    return next((n for n, exts in CATS.items() if e in exts), "其他")
def unique_target(p):
    if not p.exists(): return p
    for i in range(1,10000):
        q=p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists(): return q
    raise RuntimeError("同名文件过多")
def iter_files(base, recursive=False):
    if recursive:
        for p in base.rglob("*"):
            if p.is_file() and not any(part in CATS or part=="其他" for part in p.relative_to(base).parts[:-1]): yield p
    else:
        yield from (p for p in base.iterdir() if p.is_file())
def organize(folder, recursive=False):
    base=Path(folder); moved=[]
    for src in list(iter_files(base,recursive)):
        if src.name.startswith("~$") or src.name.startswith("."): continue
        dst=unique_target(base/category(src)/src.name); dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(src),str(dst)); moved.append((str(src),str(dst)))
    (base/"整理记录.json").write_text(json.dumps({"time":time.time(),"moves":moved},ensure_ascii=False,indent=2),encoding="utf-8")
    return moved
def undo(folder):
    base=Path(folder); log=base/"整理记录.json"
    if not log.exists(): return 0
    data=json.loads(log.read_text(encoding="utf-8")); n=0
    for src,dst in reversed(data.get("moves",[])):
        d=Path(dst); s=Path(src)
        if d.exists() and not s.exists(): s.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(d),str(s)); n+=1
    return n
def self_test():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); (p/"a.jpg").write_bytes(b"x"); (p/"a.pdf").write_bytes(b"x"); r=organize(p); assert len(r)==2 and (p/"图片/a.jpg").exists(); assert undo(p)==2 and (p/"a.jpg").exists()
    print("SELF-TEST OK")
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("940x620"); self.minsize(800,540); self.folder=tk.StringVar(); self.recursive=tk.BooleanVar(); self.status=tk.StringVar(value="请选择文件夹，然后扫描预览"); self.rows=[]; self.ui()
    def ui(self):
        s=ttk.Style(self); 
        try:s.theme_use("clam")
        except tk.TclError:pass
        r=ttk.Frame(self,padding=20); r.pack(fill="both",expand=True)
        ttk.Label(r,text=APP,font=("Microsoft YaHei UI",18,"bold")).pack(anchor="w")
        ttk.Label(r,text="按类型归类文件｜预览后执行｜自动避免覆盖｜支持撤销最近一次整理",foreground="#666").pack(anchor="w",pady=(3,14))
        box=ttk.LabelFrame(r,text="文件夹",padding=10); box.pack(fill="x"); row=ttk.Frame(box); row.pack(fill="x")
        ttk.Entry(row,textvariable=self.folder).pack(side="left",fill="x",expand=True); ttk.Button(row,text="选择",command=self.choose).pack(side="left",padx=8); ttk.Checkbutton(row,text="包含子文件夹",variable=self.recursive,command=self.scan).pack(side="left")
        bar=ttk.Frame(r); bar.pack(fill="x",pady=12); ttk.Button(bar,text="扫描预览",command=self.scan).pack(side="left"); ttk.Button(bar,text="开始整理",command=self.run).pack(side="left",padx=8); ttk.Button(bar,text="撤销最近整理",command=self.undo).pack(side="left"); ttk.Button(bar,text="打开文件夹",command=self.open).pack(side="left",padx=8)
        frame=ttk.Frame(r); frame.pack(fill="both",expand=True); self.tree=ttk.Treeview(frame,columns=("file","cat","target"),show="headings")
        for c,t,w in [("file","文件",280),("cat","分类",100),("target","整理后位置",430)]: self.tree.heading(c,text=t); self.tree.column(c,width=w,anchor="w")
        y=ttk.Scrollbar(frame,command=self.tree.yview); self.tree.configure(yscrollcommand=y.set); self.tree.pack(side="left",fill="both",expand=True); y.pack(side="right",fill="y"); ttk.Label(r,textvariable=self.status).pack(anchor="w",pady=(8,0))
    def choose(self):
        p=filedialog.askdirectory(title="选择需要整理的文件夹");
        if p:self.folder.set(p); self.scan()
    def scan(self):
        base=Path(self.folder.get()); self.tree.delete(*self.tree.get_children()); self.rows=[]
        if not base.is_dir(): self.status.set("请选择有效文件夹"); return
        for p in iter_files(base,self.recursive.get()):
            if p.name.startswith("~$") or p.name.startswith("."): continue
            cat=category(p); dst=base/cat/p.name; self.rows.append((p,dst)); self.tree.insert("","end",values=(p.name,cat,str(dst.relative_to(base))))
        self.status.set(f"扫描完成：{len(self.rows)} 个文件（仅预览，不会移动）")
    def run(self):
        if not self.rows:self.scan()
        if not self.rows:return
        if not messagebox.askyesno("确认整理",f"即将整理 {len(self.rows)} 个文件。\n同名文件会自动改名，不覆盖原文件。继续？"):return
        try:m=organize(self.folder.get(),self.recursive.get()); messagebox.showinfo("完成",f"成功整理 {len(m)} 个文件。\n已保存整理记录，可撤销。")
        except Exception as e: messagebox.showerror("错误",str(e))
        self.scan()
    def undo(self):
        n=undo(self.folder.get()); messagebox.showinfo("撤销完成",f"已恢复 {n} 个文件。" if n else "没有可撤销的整理记录。"); self.scan()
    def open(self):
        p=self.folder.get()
        if os.path.isdir(p) and hasattr(os,"startfile"): os.startfile(p)
if __name__=="__main__":
    if "--self-test" in sys.argv:self_test()
    else:App().mainloop()
