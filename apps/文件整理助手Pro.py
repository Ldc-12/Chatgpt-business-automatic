import os, sys, shutil, tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP = "文件整理助手 Pro"
CATS = {
    "图片": {".jpg",".jpeg",".png",".gif",".webp",".bmp",".tif",".tiff"},
    "视频": {".mp4",".mov",".avi",".mkv",".wmv",".flv"},
    "音频": {".mp3",".wav",".flac",".aac",".m4a",".ogg"},
    "文档": {".doc",".docx",".xls",".xlsx",".ppt",".pptx",".pdf",".txt",".csv",".md"},
    "压缩包": {".zip",".rar",".7z",".tar",".gz"},
    "程序": {".exe",".msi",".bat",".cmd",".ps1",".py",".js",".html",".css"},
}
def category(p):
    e=p.suffix.lower()
    for name, exts in CATS.items():
        if e in exts: return name
    return "其他"
def unique_target(p):
    if not p.exists(): return p
    for i in range(1,10000):
        q=p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists(): return q
    raise RuntimeError("同名文件过多")
def organize(folder, recursive=False):
    base=Path(folder)
    files=(p for p in base.rglob("*") if p.is_file()) if recursive else (p for p in base.iterdir() if p.is_file())
    moved=[]
    for src in list(files):
        if src.name.startswith("~$") or src.name.startswith("."): continue
        dst=unique_target(base/category(src)/src.name)
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(src),str(dst))
        moved.append((src,dst))
    return moved

def self_test():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); (p/"a.jpg").write_bytes(b"x"); (p/"a.pdf").write_bytes(b"x"); (p/"a.xyz").write_bytes(b"x")
        r=organize(p)
        assert len(r)==3
        assert (p/"图片/a.jpg").exists()
        assert (p/"文档/a.pdf").exists()
        assert (p/"其他/a.xyz").exists()
    print("SELF-TEST OK")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP); self.geometry("900x600"); self.minsize(760,500)
        self.folder=tk.StringVar(); self.recursive=tk.BooleanVar()
        self.status=tk.StringVar(value="请选择文件夹，然后先扫描预览")
        self.rows=[]
        self.ui()
    def ui(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except tk.TclError:pass
        root=ttk.Frame(self,padding=20); root.pack(fill="both",expand=True)
        ttk.Label(root,text=APP,font=("Microsoft YaHei UI",18,"bold")).pack(anchor="w")
        ttk.Label(root,text="本地批量归类文件：图片 / 视频 / 音频 / 文档 / 压缩包 / 程序 / 其他",foreground="#666").pack(anchor="w",pady=(3,14))
        box=ttk.LabelFrame(root,text="选择文件夹",padding=10); box.pack(fill="x")
        row=ttk.Frame(box); row.pack(fill="x")
        ttk.Entry(row,textvariable=self.folder).pack(side="left",fill="x",expand=True)
        ttk.Button(row,text="选择文件夹",command=self.choose).pack(side="left",padx=8)
        ttk.Checkbutton(row,text="包含子文件夹",variable=self.recursive).pack(side="left")
        bar=ttk.Frame(root); bar.pack(fill="x",pady=12)
        ttk.Button(bar,text="扫描预览",command=self.scan).pack(side="left")
        ttk.Button(bar,text="开始整理",command=self.run).pack(side="left",padx=8)
        ttk.Button(bar,text="打开文件夹",command=self.open).pack(side="left")
        frame=ttk.Frame(root); frame.pack(fill="both",expand=True)
        cols=("file","cat","target")
        self.tree=ttk.Treeview(frame,columns=cols,show="headings")
        for c,t,w in [("file","文件",260),("cat","分类",100),("target","整理后位置",400)]:
            self.tree.heading(c,text=t); self.tree.column(c,width=w,anchor="w")
        y=ttk.Scrollbar(frame,command=self.tree.yview); self.tree.configure(yscrollcommand=y.set)
        self.tree.pack(side="left",fill="both",expand=True); y.pack(side="right",fill="y")
        ttk.Label(root,textvariable=self.status).pack(anchor="w",pady=(8,0))
    def choose(self):
        p=filedialog.askdirectory(title="选择需要整理的文件夹")
        if p:self.folder.set(p); self.scan()
    def scan(self):
        if not self.folder.get(): return messagebox.showwarning("提示","请先选择文件夹")
        base=Path(self.folder.get()); self.tree.delete(*self.tree.get_children()); self.rows=[]
        if not base.is_dir(): return
        it=base.rglob("*") if self.recursive.get() else base.iterdir()
        for p in it:
            if p.is_file() and not p.name.startswith("~$"):
                cat=category(p); dst=base/cat/p.name
                self.rows.append((p,dst)); self.tree.insert("", "end", values=(p.name,cat,str(dst.relative_to(base))))
        self.status.set(f"扫描完成：{len(self.rows)} 个文件")
    def run(self):
        if not self.rows:self.scan()
        if not self.rows:return
        if not messagebox.askyesno("确认","将移动这些文件到分类文件夹，是否继续？"):return
        ok=0; err=0
        for src,dst in self.rows:
            try:
                dst=unique_target(dst); dst.parent.mkdir(exist_ok=True); shutil.move(str(src),str(dst)); ok+=1
            except Exception:err+=1
        self.scan(); messagebox.showinfo("完成",f"整理完成：成功 {ok} 个，失败 {err} 个")
    def open(self):
        p=self.folder.get()
        if os.path.isdir(p) and hasattr(os,"startfile"):os.startfile(p)

if __name__=="__main__":
    if "--self-test" in sys.argv:self_test()
    else:App().mainloop()
