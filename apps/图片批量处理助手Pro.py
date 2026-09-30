import sys, tempfile, os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image
APP="图片批量处理助手 Pro 1.1"
EXTS={".jpg",".jpeg",".png",".gif",".webp",".bmp",".tif",".tiff",".heic"}
def unique(dst):
    if not dst.exists(): return dst
    for i in range(1,10000):
        q=dst.with_name(f"{dst.stem} ({i}){dst.suffix}")
        if not q.exists(): return q
    raise RuntimeError("同名输出过多")
def process(src,outdir,max_width=1920,quality=85,fmt="JPEG"):
    src=Path(src); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    with Image.open(src) as im:
        im=im.convert("RGBA") if im.mode not in ("RGB","RGBA") else im.copy(); im.thumbnail((max_width,max_width),Image.Resampling.LANCZOS)
        if fmt=="JPEG":
            if im.mode=="RGBA":
                bg=Image.new("RGB",im.size,"white"); bg.paste(im,mask=im.getchannel("A")); im=bg
            else: im=im.convert("RGB")
            dst=unique(outdir/(src.stem+".jpg")); im.save(dst,format="JPEG",quality=quality,optimize=True)
        elif fmt=="WEBP": dst=unique(outdir/(src.stem+".webp")); im.save(dst,format="WEBP",quality=quality,method=6)
        else: dst=unique(outdir/(src.stem+".png")); im.save(dst,format="PNG",optimize=True)
    return dst
def self_test():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); src=p/"a.png"; Image.new("RGB",(3000,1000),"white").save(src); dst=process(src,p/"out",800,80,"JPEG"); assert dst.exists() and Image.open(dst).width<=800
        dst2=process(src,p/"out",800,80,"JPEG"); assert dst2.name!="a.jpg"
    print("SELF-TEST OK")
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("820x580"); self.folder=tk.StringVar(); self.width=tk.IntVar(value=1920); self.quality=tk.IntVar(value=85); self.fmt=tk.StringVar(value="JPEG"); self.ui()
    def ui(self):
        r=ttk.Frame(self,padding=20); r.pack(fill="both",expand=True); ttk.Label(r,text=APP,font=("Microsoft YaHei UI",18,"bold")).pack(anchor="w"); ttk.Label(r,text="批量缩放｜压缩｜格式转换｜不覆盖原图｜结果单独保存",foreground="#666").pack(anchor="w",pady=(3,18))
        box=ttk.LabelFrame(r,text="图片文件夹",padding=12); box.pack(fill="x"); row=ttk.Frame(box); row.pack(fill="x"); ttk.Entry(row,textvariable=self.folder).pack(side="left",fill="x",expand=True); ttk.Button(row,text="选择",command=self.choose).pack(side="left",padx=8); ttk.Button(row,text="扫描",command=self.scan).pack(side="left")
        opt=ttk.LabelFrame(r,text="处理参数",padding=12); opt.pack(fill="x",pady=12); a=ttk.Frame(opt); a.pack(fill="x"); ttk.Label(a,text="最长边(px)").pack(side="left"); ttk.Entry(a,textvariable=self.width,width=8).pack(side="left",padx=(5,18)); ttk.Label(a,text="质量 1-100").pack(side="left"); ttk.Entry(a,textvariable=self.quality,width=6).pack(side="left",padx=(5,18)); ttk.Label(a,text="输出").pack(side="left"); ttk.Combobox(a,textvariable=self.fmt,values=["JPEG","WEBP","PNG"],state="readonly",width=8).pack(side="left",padx=5)
        ttk.Button(r,text="开始批量处理",command=self.run).pack(anchor="w",pady=5); self.info=ttk.Label(r,text="等待选择文件夹"); self.info.pack(anchor="w",pady=8); self.list=ttk.Treeview(r,columns=("name","size"),show="headings"); self.list.heading("name",text="文件"); self.list.heading("size",text="大小"); self.list.pack(fill="both",expand=True)
    def choose(self):
        p=filedialog.askdirectory(title="选择图片文件夹");
        if p:self.folder.set(p); self.scan()
    def scan(self):
        self.list.delete(*self.list.get_children()); p=Path(self.folder.get()); n=0
        if not p.is_dir():return
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in EXTS:self.list.insert("","end",values=(f.name,f"{f.stat().st_size/1024:.0f} KB"));n+=1
        self.info.config(text=f"发现 {n} 张图片")
    def run(self):
        if not self.folder.get():return messagebox.showwarning("提示","请先选择文件夹")
        try:w=max(100,min(20000,int(self.width.get()))); q=max(1,min(100,int(self.quality.get())))
        except: return messagebox.showwarning("参数错误","最长边和质量必须是数字")
        out=Path(self.folder.get())/"处理结果"; ok=bad=0
        for f in Path(self.folder.get()).iterdir():
            if f.is_file() and f.suffix.lower() in EXTS:
                try:process(f,out,w,q,self.fmt.get());ok+=1
                except Exception:bad+=1
        messagebox.showinfo("完成",f"成功 {ok} 张，失败 {bad} 张。\n结果：{out}")
if __name__=="__main__":
    if "--self-test" in sys.argv:self_test()
    else:App().mainloop()
