import csv
import importlib.util
import json
import pytest
from decimal import Decimal
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps" / "门店排班考勤助手.py"
spec = importlib.util.spec_from_file_location("store_schedule", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(employee="E001", day="2026-11-06", **overrides):
    value = {
        "员工编号": employee, "员工姓名": "张三", "日期": day, "班次": "早班",
        "上班时间": "09:00", "下班时间": "18:00", "休息分钟": "60",
        "考勤状态": "出勤", "备注": "",
    }
    value.update(overrides)
    return value


def test_day_shift_hours_and_persistence(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    loaded = module.ScheduleStore(store.path)
    assert loaded.rows[0]["员工编号"] == "E001"
    assert module.shift_hours(loaded.rows[0]) == Decimal("8.00")


def test_overnight_shift_hours(tmp_path):
    normalized = module.normalize_shift(row(**{
        "上班时间": "22:00", "下班时间": "06:00", "休息分钟": "30",
    }))
    assert module.shift_hours(normalized) == Decimal("7.50")


def test_invalid_time_duration_and_break_are_rejected():
    invalid = [
        {"上班时间": "9:00"},
        {"下班时间": "25:00"},
        {"上班时间": "09:00", "下班时间": "09:00"},
        {"上班时间": "06:00", "下班时间": "23:00"},
        {"休息分钟": "-1"},
        {"休息分钟": "540"},
        {"休息分钟": "721"},
    ]
    for changes in invalid:
        try:
            module.normalize_shift(row(**changes))
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid shift accepted: {changes}")


def test_non_work_status_clears_time_fields():
    normalized = module.normalize_shift(row(**{
        "考勤状态": "请假", "上班时间": "09:00", "下班时间": "18:00",
    }))
    assert normalized["上班时间"] == ""
    assert normalized["下班时间"] == ""
    assert normalized["休息分钟"] == "0"
    assert module.shift_hours(normalized) == Decimal("0.00")


def test_one_record_per_employee_per_day(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    try:
        store.add(row(**{"班次": "晚班", "上班时间": "18:00", "下班时间": "23:00", "休息分钟": "0"}))
    except ValueError as exc:
        assert "每天只能" in str(exc)
    else:
        raise AssertionError("second same-day record accepted")


def test_overnight_overlap_with_next_day_is_rejected_and_rolled_back(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row(**{"上班时间": "22:00", "下班时间": "06:00", "休息分钟": "30"}))
    before = list(store.rows)
    try:
        store.add(row(day="2026-11-07", **{
            "上班时间": "05:00", "下班时间": "13:00", "休息分钟": "30",
        }))
    except ValueError as exc:
        assert "时间重叠" in str(exc)
    else:
        raise AssertionError("overlapping overnight shift accepted")
    assert store.rows == before
    assert len(module.ScheduleStore(store.path).rows) == 1


def test_different_employees_may_work_overlapping_times(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row("E001"))
    store.add(row("E002"))
    assert len(store.rows) == 2


def test_update_delete_and_reopen(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    store.update("E001", "2026-11-06", row(**{"班次": "中班"}))
    assert module.ScheduleStore(store.path).rows[0]["班次"] == "中班"
    store.delete("E001", "2026-11-06")
    assert module.ScheduleStore(store.path).rows == []


def test_csv_roundtrip_with_utf8_bom(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    exported = tmp_path / "schedule.csv"
    store.export_csv(exported)
    assert exported.read_bytes().startswith(b"\xef\xbb\xbf")
    imported = module.ScheduleStore(tmp_path / "imported.json")
    assert imported.import_csv(exported) == 1
    assert imported.rows == store.rows


def test_duplicate_csv_import_is_atomic(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    source = tmp_path / "duplicate.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow(row())
    before = list(store.rows)
    try:
        store.import_csv(source)
    except ValueError as exc:
        assert "每天只能" in str(exc)
    else:
        raise AssertionError("duplicate CSV import accepted")
    assert store.rows == before


def test_invalid_csv_does_not_change_existing_data(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    source = tmp_path / "bad.csv"
    source.write_text("员工编号,员工姓名\nE002,李四", encoding="utf-8-sig")
    try:
        store.import_csv(source)
    except ValueError:
        pass
    else:
        raise AssertionError("CSV with missing headers accepted")
    assert len(store.rows) == 1


def test_backup_restore_roundtrip(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    backup = tmp_path / "backup.json"
    store.backup(backup)
    store.add(row("E002"))
    store.restore(backup)
    assert len(module.ScheduleStore(store.path).rows) == 1


def test_invalid_backup_rejected_without_overwrite(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row())
    bad = tmp_path / "bad.json"
    bad.write_text('{"format":"unknown","version":99,"schedule":[]}', encoding="utf-8")
    try:
        store.restore(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported backup accepted")
    assert len(store.rows) == 1


def test_filter_and_summary():
    rows = [
        module.normalize_shift(row()),
        module.normalize_shift(row("E002", "2026-11-07", **{"考勤状态": "请假"})),
    ]
    filtered = module.filter_shifts(rows, keyword="张三", month="2026-11", status="出勤")
    summary = module.summarize_shifts(filtered)
    assert summary == {
        "count": 1,
        "counts": {"出勤": 1, "休息": 0, "请假": 0, "缺勤": 0},
        "hours": Decimal("8.00"),
    }


def test_invalid_month_filter_is_rejected():
    for month in ("2026/11", "2026-13"):
        try:
            module.filter_shifts([], month=month)
        except ValueError as exc:
            assert "YYYY-MM" in str(exc)
        else:
            raise AssertionError(f"invalid month accepted: {month}")


def test_failed_disk_write_rolls_back_memory(tmp_path, monkeypatch):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    def fail(*args, **kwargs):
        raise OSError("simulated disk full")
    monkeypatch.setattr(module, "atomic_write", fail)
    try:
        store.add(row())
    except OSError:
        pass
    else:
        raise AssertionError("disk write failure did not propagate")
    assert store.rows == []



def test_monthly_labor_report_aggregates_daily_hours_and_status_counts():
    rows = [
        module.normalize_shift(row(day="2026-11-06", **{
            "上班时间": "09:00", "下班时间": "20:00", "休息分钟": "60",
        })),
        module.normalize_shift(row(day="2026-11-07", **{
            "上班时间": "09:00", "下班时间": "16:00", "休息分钟": "0",
        })),
        module.normalize_shift(row("E002", "2026-11-07", **{"考勤状态": "请假"})),
        module.normalize_shift(row("E002", "2026-11-08", **{"考勤状态": "缺勤"})),
        module.normalize_shift(row(day="2026-12-01")),
    ]
    report = module.build_monthly_labor_report(rows, "2026-11", "8")
    assert report == [
        {
            "月份": "2026-11", "员工编号": "E001", "员工姓名": "张三",
            "出勤天数": "2", "休息天数": "0", "请假天数": "0", "缺勤天数": "0",
            "总工时": "17.00", "日标准工时": "8.00",
            "标准工时估算": "15.00", "超出标准工时估算": "2.00",
        },
        {
            "月份": "2026-11", "员工编号": "E002", "员工姓名": "张三",
            "出勤天数": "0", "休息天数": "0", "请假天数": "1", "缺勤天数": "1",
            "总工时": "0.00", "日标准工时": "8.00",
            "标准工时估算": "0.00", "超出标准工时估算": "0.00",
        },
    ]


@pytest.mark.parametrize("month", ["2026/11", "2026-13", "2026-1"])
def test_monthly_labor_report_rejects_invalid_month(month):
    with pytest.raises(ValueError, match="YYYY-MM"):
        module.build_monthly_labor_report([], month)


@pytest.mark.parametrize("hours", ["0", "-1", "16.01", "NaN", "abc"])
def test_monthly_labor_report_rejects_invalid_daily_standard(hours):
    with pytest.raises(ValueError):
        module.build_monthly_labor_report([], "2026-11", hours)


def test_monthly_report_csv_is_utf8_bom_and_formula_safe(tmp_path):
    source = module.normalize_shift(row(**{"员工姓名": "=HYPERLINK(\"https://example.invalid\",\"员工\")"}))
    report = module.build_monthly_labor_report([source], "2026-11")
    target = tmp_path / "monthly.csv"
    assert module.export_monthly_labor_report_csv(target, report) == 1
    content = target.read_text(encoding="utf-8-sig")
    assert content.startswith("月份,")
    assert "'=HYPERLINK(" in content


def test_monthly_report_empty_export_contains_headers(tmp_path):
    target = tmp_path / "empty.csv"
    assert module.export_monthly_labor_report_csv(target, []) == 0
    with target.open(encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == module.MONTHLY_REPORT_FIELDS


def test_existing_schedule_csv_export_protects_formula_cells(tmp_path):
    store = module.ScheduleStore(tmp_path / "schedule.json")
    store.add(row(**{"员工姓名": "  =1+1"}))
    target = tmp_path / "schedule.csv"
    store.export_csv(target)
    content = target.read_text(encoding="utf-8-sig")
    assert "'  =1+1" in content


def test_atomic_write_failure_preserves_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "report.csv"
    target.write_text("previous", encoding="utf-8")
    def fail(*args, **kwargs):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        module.atomic_write(target, "replacement")
    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob("report.csv.*.tmp")) == []
