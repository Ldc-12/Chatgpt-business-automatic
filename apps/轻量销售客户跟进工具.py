import csv, datetime as dt, io, json, math, os, shutil, sys, tempfile, tkinter as tk
from tkinter import filedialog, messagebox, ttk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.license import require_license


FIELDS=["客户","联系人","电话/微信","来源","阶段","预计金额","下次跟进","负责人","备注"]
STAGES=["新线索","已联系","需求确认","报价中","谈判中","成交","暂停","流失"]

def today(): return dt.date.today().isoformat()
def num(v):
    s = str(v).strip().replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    value = float(s) if s else 0.0
    if not math.isfinite(value):
        raise ValueError("金额必须是有限数字")
    return value
def due(v):
    try:return (dt.date.fromisoformat(str(v))-dt.date.today()).days
    except:return None

MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 50000


def spreadsheet_safe_cell(value):
    text = "" if value is None else str(value)
    if text.lstrip(" " + chr(9) + chr(13) + chr(10)).startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def restore_spreadsheet_safe_cell(value):
    text = "" if value is None else str(value)
    if text.startswith("'") and text[1:].lstrip(" " + chr(9) + chr(13) + chr(10)).startswith(("=", "+", "-", "@")):
        return text[1:]
    return text


def atomic_write_text(path, content):
    target = os.path.abspath(path)
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(target) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def export_csv(path, rows):
    clean = validate_rows(rows)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="raise")
    writer.writeheader()
    for row in clean:
        writer.writerow({field: spreadsheet_safe_cell(row[field]) for field in FIELDS})
    atomic_write_text(path, chr(65279) + buffer.getvalue())


def read_csv_rows(path):
    if os.path.getsize(path) > MAX_CSV_BYTES:
        raise ValueError("CSV 超过 25 MiB 安全上限")
    imported = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        if not headers:
            raise ValueError("CSV 缺少表头")
        if len(headers) != len(set(headers)):
            raise ValueError("CSV 存在重复字段名")
        missing = [field for field in FIELDS if field not in headers]
        extra = [field for field in headers if field not in FIELDS]
        if missing or extra:
            details = []
            if missing:
                details.append("缺少字段：" + "、".join(missing))
            if extra:
                details.append("存在未支持字段：" + "、".join(extra))
            raise ValueError("；".join(details))
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV 第 {line} 行包含多余列")
            values = list(row.values())
            if not values or all(value in (None, "") for value in values):
                continue
            if any(value is None for value in values):
                raise ValueError(f"CSV 第 {line} 行字段数量不足")
            if len(imported) >= MAX_CSV_ROWS:
                raise ValueError("CSV 超过 50000 条记录上限")
            imported.append({field: restore_spreadsheet_safe_cell(row[field]) for field in FIELDS})
    return validate_rows(imported)


def replace_rows_with_backup(data_path, imported_rows, current_rows):
    clean = validate_rows(imported_rows)
    backup_path = None
    if os.path.exists(data_path):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = data_path + ".before-csv-import-" + stamp + ".json"
        suffix = 1
        while os.path.exists(backup_path):
            backup_path = data_path + ".before-csv-import-" + stamp + f"-{suffix}.json"
            suffix += 1
        save_rows(backup_path, current_rows)
    save_rows(data_path, clean)
    return backup_path


def validate_rows(rows):
    if not isinstance(rows, list):
        raise ValueError("备份格式错误：顶层必须是记录列表")
    clean = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"第 {index} 条记录不是对象")
        missing = [field for field in FIELDS if field not in row]
        if missing:
            raise ValueError(f"第 {index} 条记录缺少字段：" + "、".join(missing))
        item = {field: str(row.get(field, "") or "") for field in FIELDS}
        if not item["客户"].strip():
            raise ValueError(f"第 {index} 条记录的客户名称为空")
        try:
            num(item["预计金额"])
        except ValueError as exc:
            raise ValueError(f"第 {index} 条记录的预计金额无效") from exc
        clean.append(item)
    return clean


def load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return validate_rows(json.load(f))


def save_rows(path, rows):
    clean = validate_rows(rows)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("轻量销售客户跟进工具｜大陆版"); self.geometry("1280x730"); self.minsize(1100,650)
        self.rows=[]; self.path=os.path.join(os.getenv("LOCALAPPDATA",os.path.expanduser("~")),"MainlandBusinessTools","sales.json")
        self.load_error = None
        self.load(); self.ui(); self.refresh()
        if self.load_error:
            messagebox.showerror("数据读取失败", f"本地数据文件无法读取，原文件已保留，没有被清空。\n\n{self.load_error}\n\n请使用“JSON恢复”选择有效备份。", parent=self)
    def ui(self):
        bar=ttk.Frame(self); bar.pack(fill="x",padx=10,pady=8)
        for t,c in [("新增",self.add),("编辑",self.edit),("删除",self.delete),("导入CSV",self.imp),("导出CSV",self.exp),("JSON备份",self.backup_json),("JSON恢复",self.restore_json),("销售统计",self.stats),("跟进话术",self.script)]:
            ttk.Button(bar,text=t,command=c).pack(side="left",padx=3)
        ttk.Label(bar,text="搜索").pack(side="left",padx=(18,4)); self.q=tk.StringVar(); ttk.Entry(bar,textvariable=self.q,width=24).pack(side="left"); self.q.trace_add("write",lambda *_:self.refresh())
        self.f=tk.StringVar(value="全部"); ttk.Combobox(bar,textvariable=self.f,values=["全部"]+STAGES+["7天内跟进"],state="readonly",width=12).pack(side="left",padx=6); self.f.trace_add("write",lambda *_:self.refresh())
        frame=ttk.Frame(self); frame.pack(fill="both",expand=True,padx=10)
        self.tree=ttk.Treeview(frame,columns=FIELDS,show="headings",selectmode="extended")
        for f,w in zip(FIELDS,[120,100,130,80,90,100,105,90,260]): self.tree.heading(f,text=f); self.tree.column(f,width=w,anchor="w")
        self.tree.pack(side="left",fill="both",expand=True); self.tree.bind("<Double-1>",lambda e:self.edit())
        sb=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview); sb.pack(side="right",fill="y"); self.tree.configure(yscrollcommand=sb.set)
        self.status=tk.StringVar(); ttk.Label(self,textvariable=self.status,anchor="w").pack(fill="x",padx=10,pady=7)
        ttk.Label(self,text="数据保存在本机；支持 CSV 交换和 JSON 完整备份。恢复 JSON 前会自动备份当前文件。",anchor="w").pack(fill="x",padx=10,pady=(0,8))
    def load(self):
        try:
            self.rows = load_rows(self.path)
        except Exception as exc:
            self.rows = []
            self.load_error = str(exc)
    def save(self):
        if self.load_error:
            raise RuntimeError("本机数据文件读取失败，请先使用 JSON恢复，避免覆盖原文件。")
        save_rows(self.path, self.rows)
    def ensure_writable(self):
        if self.load_error:
            messagebox.showerror("暂不可修改", "当前数据文件读取失败。请先使用“JSON恢复”载入有效备份；原始文件目前仍被保留。", parent=self)
            return False
        return True
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
        if not self.ensure_writable(): return
        d=self.dialog({"阶段":"新线索","下次跟进":today()})
        if d:self.rows.append(d);self.save();self.refresh()
    def edit(self):
        if not self.ensure_writable(): return
        i=self.index()
        if i is None:messagebox.showinfo("提示","请先选择客户");return
        d=self.dialog(self.rows[i])
        if d:self.rows[i]=d;self.save();self.refresh()
    def delete(self):
        if not self.ensure_writable(): return
        s=self.tree.selection()
        if not s:return
        vals=[list(self.tree.item(x,"values")) for x in s]
        self.rows=[r for r in self.rows if [r.get(x,"") for x in FIELDS] not in vals];self.save();self.refresh()
    def imp(self):
        if not self.ensure_writable(): return
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not p:
            return
        try:
            imported = read_csv_rows(p)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        if not messagebox.askyesno(
            "确认替换客户数据",
            f"CSV 已通过校验，共 {len(imported)} 条客户记录。\\n导入会替换当前全部 {len(self.rows)} 条记录；程序会先自动备份当前数据。是否继续？",
            parent=self,
        ):
            return
        try:
            backup_path = replace_rows_with_backup(self.path, imported, self.rows)
            self.rows = imported
            self.refresh()
            detail = f"\\n原数据备份：{backup_path}" if backup_path else "\\n当前没有旧数据文件，无需创建导入前备份。"
            messagebox.showinfo("导入完成", f"已导入 {len(imported)} 条客户记录。{detail}", parent=self)
        except Exception as exc:
            messagebox.showerror("导入失败", f"当前数据未被替换：{exc}", parent=self)

    def exp(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not p:
            return
        try:
            export_csv(p, self.rows)
            messagebox.showinfo("导出完成", "客户数据已安全导出（UTF-8 BOM、公式防护、原子替换）。", parent=self)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
    def backup_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="销售客户备份-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json",
            filetypes=[("JSON 备份", "*.json")],
        )
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(self.path):
            messagebox.showerror("备份失败", "请选择与当前数据文件不同的位置，避免把备份保存到原文件。", parent=self)
            return
        if self.load_error:
            messagebox.showerror("备份失败", "当前数据文件读取失败。请先使用“JSON恢复”；原始文件仍保留。", parent=self)
            return
        try:
            save_rows(path, self.rows)
            messagebox.showinfo("备份完成", "已保存完整 JSON 备份：\n" + path, parent=self)
        except Exception as exc:
            messagebox.showerror("备份失败", str(exc), parent=self)

    def restore_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(self.path):
            messagebox.showinfo("提示", "所选文件就是当前数据文件，无需恢复。", parent=self)
            return
        try:
            restored = load_rows(path)
        except Exception as exc:
            messagebox.showerror("恢复失败", "备份文件无效，当前数据未改变。\n\n" + str(exc), parent=self)
            return
        if not messagebox.askyesno("确认恢复", f"备份包含 {len(restored)} 条客户记录。恢复会替换当前列表，是否继续？", parent=self):
            return
        backup_path = self.path + ".before-restore-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"
        try:
            if os.path.exists(self.path):
                shutil.copy2(self.path, backup_path)
            else:
                save_rows(backup_path, self.rows)
            save_rows(self.path, restored)
            self.rows = restored
            self.load_error = None
            self.refresh()
            messagebox.showinfo("恢复完成", f"已恢复 {len(restored)} 条记录。\n恢复前数据备份：{backup_path}", parent=self)
        except Exception as exc:
            messagebox.showerror("恢复失败", f"未能完成恢复：{exc}\n恢复前备份（如已创建）：{backup_path}", parent=self)

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
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    else:
        require_license("轻量销售客户跟进工具")
        App().mainloop()
