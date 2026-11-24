"""Offline store shift scheduling and attendance ledger."""
import csv
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.license import require_license

PRODUCT = "门店排班考勤助手"
FIELDS = ["员工编号", "员工姓名", "日期", "班次", "上班时间", "下班时间", "休息分钟", "考勤状态", "备注"]
STATUSES = ["出勤", "休息", "请假", "缺勤"]
MONTHLY_REPORT_FIELDS = ["月份", "员工编号", "员工姓名", "出勤天数", "休息天数", "请假天数", "缺勤天数", "总工时", "日标准工时", "标准工时估算", "超出标准工时估算"]
BACKUP_FORMAT = "mainland-store-schedule-backup"
BACKUP_VERSION = 1


def parse_date(value):
    value = str(value or "").strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
    if parsed.isoformat() != value:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式")
    return value


def parse_time(value, field):
    value = str(value or "").strip()
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"{field}必须使用 HH:MM 格式") from exc
    if parsed.strftime("%H:%M") != value:
        raise ValueError(f"{field}必须使用 HH:MM 格式")
    return parsed


def normalize_shift(row):
    if not isinstance(row, dict):
        raise ValueError("排班记录格式错误")
    item = {field: str(row.get(field, "") or "").strip() for field in FIELDS}
    for field in ("员工编号", "员工姓名", "日期", "班次", "考勤状态"):
        if not item[field]:
            raise ValueError(f"{field}不能为空")
    item["日期"] = parse_date(item["日期"])
    if item["考勤状态"] not in STATUSES:
        raise ValueError("考勤状态不正确")
    if item["考勤状态"] != "出勤":
        item["上班时间"] = ""
        item["下班时间"] = ""
        item["休息分钟"] = "0"
        return item
    start = parse_time(item["上班时间"], "上班时间")
    end = parse_time(item["下班时间"], "下班时间")
    try:
        break_minutes = int(item["休息分钟"] or "0")
    except (TypeError, ValueError) as exc:
        raise ValueError("休息分钟必须是整数") from exc
    if break_minutes < 0 or break_minutes > 720:
        raise ValueError("休息分钟必须在 0 到 720 之间")
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    duration = end_minutes - start_minutes
    if duration <= 0:
        duration += 24 * 60
    if duration > 16 * 60:
        raise ValueError("单班时长不能超过 16 小时")
    if break_minutes >= duration:
        raise ValueError("休息分钟必须少于班次总时长")
    item["休息分钟"] = str(break_minutes)
    return item


def shift_interval(row):
    day = datetime.strptime(row["日期"], "%Y-%m-%d")
    start = parse_time(row["上班时间"], "上班时间")
    end = parse_time(row["下班时间"], "下班时间")
    start_at = day.replace(hour=start.hour, minute=start.minute)
    end_at = day.replace(hour=end.hour, minute=end.minute)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


def shift_hours(row):
    if row["考勤状态"] != "出勤":
        return Decimal("0.00")
    start_at, end_at = shift_interval(row)
    minutes = int((end_at - start_at).total_seconds() // 60) - int(row["休息分钟"])
    return (Decimal(minutes) / Decimal(60)).quantize(Decimal("0.01"))


def check_schedule(rows):
    keys = [(row["员工编号"], row["日期"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("同一员工每天只能登记一条排班记录")
    by_employee = {}
    for row in rows:
        if row["考勤状态"] == "出勤":
            by_employee.setdefault(row["员工编号"], []).append((shift_interval(row), row))
    for employee_id, entries in by_employee.items():
        entries.sort(key=lambda entry: entry[0][0])
        previous_end = None
        for (start_at, end_at), row in entries:
            if previous_end is not None and start_at < previous_end:
                raise ValueError(f"员工 {employee_id} 的班次时间重叠，请检查跨日班次")
            previous_end = end_at


def spreadsheet_safe_cell(value):
    """Prefix spreadsheet formula-like text without altering ordinary values."""
    text = str(value if value is not None else "")
    probe = text.lstrip(" \t\r\n")
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class ScheduleStore:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.load()

    def load(self):
        if not self.path.exists():
            self.rows = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("排班数据文件格式错误")
            rows = [normalize_shift(row) for row in data]
            check_schedule(rows)
            self.rows = rows
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"排班数据无法读取，原文件未修改：{exc}") from exc

    def save(self):
        check_schedule(self.rows)
        atomic_write(self.path, json.dumps(self.rows, ensure_ascii=False, indent=2))

    def add(self, row):
        item = normalize_shift(row)
        previous = self.rows
        self.rows = previous + [item]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise

    def update(self, employee_id, day, row):
        item = normalize_shift(row)
        index = next((i for i, old in enumerate(self.rows)
                      if old["员工编号"] == employee_id and old["日期"] == day), None)
        if index is None:
            raise ValueError("找不到要修改的排班记录")
        previous = self.rows[index]
        self.rows[index] = item
        try:
            self.save()
        except Exception:
            self.rows[index] = previous
            raise

    def delete(self, employee_id, day):
        previous = self.rows
        self.rows = [row for row in self.rows
                     if not (row["员工编号"] == employee_id and row["日期"] == day)]
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise

    def import_csv(self, path):
        incoming = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(FIELDS) or set(headers) != set(FIELDS):
                raise ValueError("CSV 必须且只能包含全部规定字段：" + "、".join(FIELDS))
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValueError(f"第 {line} 行包含多余列")
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    incoming.append(normalize_shift(row))
                except ValueError as exc:
                    raise ValueError(f"第 {line} 行：{exc}") from exc
        previous = self.rows
        self.rows = previous + incoming
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise
        return len(incoming)

    def export_csv(self, path, rows=None):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for row in self.rows if rows is None else rows:
            writer.writerow({field: spreadsheet_safe_cell(row.get(field, "")) for field in FIELDS})
        atomic_write(path, "\ufeff" + output.getvalue())

    def backup(self, path):
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "schedule": self.rows,
        }
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def restore(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if (not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT
                or payload.get("version") != BACKUP_VERSION):
            raise ValueError("备份文件版本或格式不受支持")
        source = payload.get("schedule")
        if not isinstance(source, list):
            raise ValueError("备份排班列表格式错误")
        rows = [normalize_shift(row) for row in source]
        check_schedule(rows)
        previous = self.rows
        self.rows = rows
        try:
            self.save()
        except Exception:
            self.rows = previous
            raise


def filter_shifts(rows, keyword="", month="", status="全部"):
    query = str(keyword or "").casefold().strip()
    month = str(month or "").strip()
    if month:
        try:
            parsed = datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("月份筛选请使用有效的 YYYY-MM 格式") from exc
        if parsed.strftime("%Y-%m") != month:
            raise ValueError("月份筛选请使用有效的 YYYY-MM 格式")
    result = []
    for row in rows:
        if month and not row["日期"].startswith(month):
            continue
        if status != "全部" and row["考勤状态"] != status:
            continue
        if query and query not in " ".join(str(row[field]) for field in FIELDS).casefold():
            continue
        result.append(row)
    return result


def summarize_shifts(rows):
    counts = {status: sum(1 for row in rows if row["考勤状态"] == status) for status in STATUSES}
    hours = sum((shift_hours(row) for row in rows), Decimal("0.00"))
    return {"count": len(rows), "counts": counts, "hours": hours}


def parse_month(value):
    month = str(value or "").strip()
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("月份必须使用 YYYY-MM 格式") from exc
    if parsed.strftime("%Y-%m") != month:
        raise ValueError("月份必须使用有效的 YYYY-MM 格式")
    return month


def parse_standard_daily_hours(value):
    try:
        hours = Decimal(str(value).strip())
    except Exception as exc:
        raise ValueError("每日标准工时必须是数字") from exc
    if not hours.is_finite() or hours <= 0 or hours > Decimal("16"):
        raise ValueError("每日标准工时必须大于 0 且不超过 16 小时")
    return hours.quantize(Decimal("0.01"))


def build_monthly_labor_report(rows, month, standard_daily_hours="8"):
    """Build a payroll-preparation timesheet; overtime is a configurable estimate, not a legal conclusion."""
    month = parse_month(month)
    daily_standard = parse_standard_daily_hours(standard_daily_hours)
    grouped = {}
    for raw in rows:
        item = normalize_shift(raw)
        if not item["日期"].startswith(month):
            continue
        employee_id = item["员工编号"]
        bucket = grouped.setdefault(employee_id, {
            "name": item["员工姓名"],
            "出勤天数": 0,
            "休息天数": 0,
            "请假天数": 0,
            "缺勤天数": 0,
            "total": Decimal("0.00"),
            "standard": Decimal("0.00"),
            "overtime": Decimal("0.00"),
        })
        if bucket["name"] != item["员工姓名"]:
            raise ValueError(f"员工编号 {employee_id} 在统计月份对应多个姓名，请先统一员工档案")
        status_field = {
            "出勤": "出勤天数",
            "休息": "休息天数",
            "请假": "请假天数",
            "缺勤": "缺勤天数",
        }[item["考勤状态"]]
        bucket[status_field] += 1
        if item["考勤状态"] == "出勤":
            hours = shift_hours(item)
            bucket["total"] += hours
            bucket["standard"] += min(hours, daily_standard)
            bucket["overtime"] += max(Decimal("0.00"), hours - daily_standard)
    report = []
    for employee_id, bucket in sorted(grouped.items()):
        report.append({
            "月份": month,
            "员工编号": employee_id,
            "员工姓名": bucket["name"],
            "出勤天数": str(bucket["出勤天数"]),
            "休息天数": str(bucket["休息天数"]),
            "请假天数": str(bucket["请假天数"]),
            "缺勤天数": str(bucket["缺勤天数"]),
            "总工时": f"{bucket['total']:.2f}",
            "日标准工时": f"{daily_standard:.2f}",
            "标准工时估算": f"{bucket['standard']:.2f}",
            "超出标准工时估算": f"{bucket['overtime']:.2f}",
        })
    return report


def export_monthly_labor_report_csv(path, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=MONTHLY_REPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: spreadsheet_safe_cell(row.get(field, "")) for field in MONTHLY_REPORT_FIELDS})
    atomic_write(path, "\ufeff" + output.getvalue())
    return len(rows)


def default_data_path():
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "MainlandBusinessTools" / "store_schedule.json"


class App:
    def __init__(self, root):
        self.root = root
        root.title("门店排班考勤助手｜大陆版")
        root.geometry("1260x700")
        self.store = ScheduleStore(default_data_path())
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        for label, command in [
            ("新增排班", self.add), ("编辑", self.edit), ("删除", self.delete),
            ("导入 CSV", self.import_csv), ("导出 CSV", self.export_csv),
            ("导出月度工时汇总", self.export_monthly_report),
            ("备份", self.backup), ("恢复备份", self.restore),
        ]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)
        filters = ttk.Frame(root, padding=(8, 0, 8, 8))
        filters.pack(fill="x")
        self.query = tk.StringVar()
        self.month = tk.StringVar()
        self.status = tk.StringVar(value="全部")
        ttk.Label(filters, text="搜索").pack(side="left")
        ttk.Entry(filters, textvariable=self.query, width=22).pack(side="left", padx=4)
        ttk.Label(filters, text="月份 YYYY-MM").pack(side="left", padx=(12, 2))
        ttk.Entry(filters, textvariable=self.month, width=10).pack(side="left")
        ttk.Label(filters, text="状态").pack(side="left", padx=(12, 2))
        ttk.Combobox(filters, textvariable=self.status, values=["全部"] + STATUSES,
                     state="readonly", width=9).pack(side="left")
        self.query.trace_add("write", lambda *_: self.refresh())
        self.month.trace_add("write", lambda *_: self.refresh())
        self.status.trace_add("write", lambda *_: self.refresh())
        self.tree = ttk.Treeview(root, columns=FIELDS, show="headings", height=22)
        widths = [100, 100, 105, 95, 90, 90, 85, 85, 220]
        for field, width in zip(FIELDS, widths):
            self.tree.heading(field, text=field)
            self.tree.column(field, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.visible_rows = []
        self.summary = tk.StringVar()
        ttk.Label(root, textvariable=self.summary, anchor="w", padding=8).pack(fill="x")
        self.refresh()

    def refresh(self):
        try:
            rows = filter_shifts(self.store.rows, self.query.get(), self.month.get(), self.status.get())
        except ValueError:
            rows = filter_shifts(self.store.rows, self.query.get(), "", self.status.get())
        self.visible_rows = rows
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(rows):
            self.tree.insert("", "end", iid=str(index), values=[row[field] for field in FIELDS])
        summary = summarize_shifts(rows)
        counts = "  ".join(f"{key} {value}" for key, value in summary["counts"].items())
        self.summary.set(f"记录：{summary['count']}    {counts}    出勤工时：{summary['hours']} 小时")

    def form(self, existing=None):
        win = tk.Toplevel(self.root)
        win.title("排班记录")
        values = {field: tk.StringVar(value=str((existing or {}).get(field, ""))) for field in FIELDS}
        if not existing:
            values["日期"].set(date.today().isoformat())
            values["班次"].set("早班")
            values["休息分钟"].set("60")
            values["考勤状态"].set("出勤")
        for index, field in enumerate(FIELDS):
            ttk.Label(win, text=field).grid(row=index, column=0, padx=8, pady=4, sticky="e")
            if field == "考勤状态":
                ttk.Combobox(win, textvariable=values[field], values=STATUSES,
                             state="readonly", width=34).grid(row=index, column=1, padx=8, pady=4)
            else:
                ttk.Entry(win, textvariable=values[field], width=38).grid(row=index, column=1, padx=8, pady=4)

        def save():
            try:
                row = {field: values[field].get() for field in FIELDS}
                if existing:
                    self.store.update(existing["员工编号"], existing["日期"], row)
                else:
                    self.store.add(row)
                self.refresh()
                win.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=win)

        ttk.Button(win, text="保存", command=save).grid(row=len(FIELDS), column=0, columnspan=2, pady=8)

    def selected_row(self):
        selected = self.tree.selection()
        if not selected:
            return None
        index = int(selected[0])
        return self.visible_rows[index]

    def add(self):
        self.form()

    def edit(self):
        row = self.selected_row()
        if row:
            self.form(row)

    def delete(self):
        row = self.selected_row()
        if row and messagebox.askyesno("确认删除", f"删除 {row['员工姓名']} 在 {row['日期']} 的排班记录？"):
            try:
                self.store.delete(row["员工编号"], row["日期"])
                self.refresh()
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = self.store.import_csv(path)
                self.refresh()
                messagebox.showinfo("导入完成", f"成功追加 {count} 条记录")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导入失败", str(exc))

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                self.store.export_csv(path, filter_shifts(
                    self.store.rows, self.query.get(), self.month.get(), self.status.get()
                ))
                messagebox.showinfo("导出完成", "当前筛选结果已导出为 CSV")
            except (ValueError, OSError) as exc:
                messagebox.showerror("导出失败", str(exc))

    def export_monthly_report(self):
        month = simpledialog.askstring(
            "统计月份", "请输入统计月份（YYYY-MM）",
            initialvalue=date.today().strftime("%Y-%m"), parent=self.root,
        )
        if month is None:
            return
        standard = simpledialog.askstring(
            "每日标准工时", "请输入每日标准工时（小时，默认 8）",
            initialvalue="8", parent=self.root,
        )
        if standard is None:
            return
        try:
            report = build_monthly_labor_report(self.store.rows, month, standard)
        except ValueError as exc:
            messagebox.showerror("统计参数无效", str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"门店月度工时汇总-{month}.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if path:
            try:
                count = export_monthly_labor_report_csv(path, report)
                messagebox.showinfo("导出完成", f"已导出 {count} 名员工的月度工时汇总。")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.root)

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 备份", "*.json")])
        if path:
            try:
                self.store.backup(path)
                messagebox.showinfo("备份完成", "排班数据已备份")
            except OSError as exc:
                messagebox.showerror("备份失败", str(exc))

    def restore(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 备份", "*.json")])
        if path and messagebox.askyesno("确认恢复", "恢复会替换当前全部排班数据，建议先备份。继续？"):
            try:
                self.store.restore(path)
                self.refresh()
                messagebox.showinfo("恢复完成", "排班数据已恢复")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("恢复失败", str(exc))


def self_test():
    row = normalize_shift({
        "员工编号": "E001", "员工姓名": "测试员工", "日期": "2026-11-06",
        "班次": "早班", "上班时间": "09:00", "下班时间": "18:00",
        "休息分钟": "60", "考勤状态": "出勤",
    })
    assert shift_hours(row) == Decimal("8.00")
    long_shift = normalize_shift({
        "员工编号": "E002", "员工姓名": "测试员工二", "日期": "2026-11-06",
        "班次": "长班", "上班时间": "09:00", "下班时间": "20:00",
        "休息分钟": "60", "考勤状态": "出勤",
    })
    report = build_monthly_labor_report([long_shift], "2026-11", "8")
    assert report[0]["总工时"] == "10.00"
    assert report[0]["标准工时估算"] == "8.00"
    assert report[0]["超出标准工时估算"] == "2.00"
    assert PRODUCT == "门店排班考勤助手"
    print("SELF_TEST_OK", flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv or os.environ.get("MAINLAND_EXE_SELF_TEST") == "1":
        self_test()
        os._exit(0)
    require_license(PRODUCT)
    App(tk.Tk()).root.mainloop()
