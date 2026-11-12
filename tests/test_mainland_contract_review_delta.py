from pathlib import Path

import pytest

from src.contract_review import ReviewStore, findings_sha256, normalize_record, REVIEW_DECISIONS


def finding(rule_id, detail=None):
    return {
        "等级": "中",
        "规则编号": rule_id,
        "检查项": f"检查 {rule_id}",
        "风险说明": detail or f"{rule_id} 风险说明",
        "证据摘录": f"{rule_id} 证据",
        "建议动作": f"核对 {rule_id}",
    }


def make_record(record_id, source_hash, ruleset, findings, *, contract_id="C001", reviewed_at="2026-01-01T09:00:00+08:00"):
    decision = REVIEW_DECISIONS[1] if findings else REVIEW_DECISIONS[0]
    return normalize_record({
        "复核编号": record_id,
        "复核时间": reviewed_at,
        "合同编号": contract_id,
        "合同名称": "测试合同",
        "来源文件": f"{record_id}.txt",
        "来源SHA256": source_hash,
        "规则版本": ruleset,
        "风险命中数": str(len(findings)),
        "风险明细SHA256": findings_sha256(findings),
        "人工结论": decision,
        "复核人": "测试复核员",
        "复核备注": "请核对风险变化" if findings else "",
        "风险明细": findings,
    })


def test_compare_previous_reports_added_resolved_and_unchanged_findings(tmp_path):
    store = ReviewStore(tmp_path / "reviews.json")
    store.records = [
        make_record("rev-1", "a" * 64, "RULESET-1", [finding("KEEP"), finding("OLD")]),
        make_record("rev-2", "b" * 64, "RULESET-1", [finding("KEEP"), finding("NEW")],
                    reviewed_at="2026-02-01T09:00:00+08:00"),
    ]
    store.save()
    result = ReviewStore(tmp_path / "reviews.json").compare_previous("rev-2")
    assert result["status"] == "ok"
    assert result["previous"]["复核编号"] == "rev-1"
    assert [item["规则编号"] for item in result["added"]] == ["NEW"]
    assert [item["规则编号"] for item in result["resolved"]] == ["OLD"]
    assert [item["规则编号"] for item in result["unchanged"]] == ["KEEP"]


def test_compare_previous_skips_same_source_rereviews(tmp_path):
    store = ReviewStore(tmp_path / "reviews.json")
    store.records = [
        make_record("rev-1", "a" * 64, "RULESET-1", [finding("KEEP")]),
        make_record("rev-2", "a" * 64, "RULESET-1", [finding("KEEP")],
                    reviewed_at="2026-01-02T09:00:00+08:00"),
        make_record("rev-3", "b" * 64, "RULESET-1", [finding("KEEP"), finding("NEW")],
                    reviewed_at="2026-02-01T09:00:00+08:00"),
    ]
    store.save()
    result = ReviewStore(tmp_path / "reviews.json").compare_previous("rev-3")
    assert result["status"] == "ok"
    assert result["previous"]["复核编号"] == "rev-2"
    assert [item["规则编号"] for item in result["added"]] == ["NEW"]


def test_compare_previous_refuses_different_rulesets(tmp_path):
    store = ReviewStore(tmp_path / "reviews.json")
    store.records = [
        make_record("rev-1", "a" * 64, "RULESET-OLD", [finding("OLD")]),
        make_record("rev-2", "b" * 64, "RULESET-NEW", [finding("NEW")],
                    reviewed_at="2026-02-01T09:00:00+08:00"),
    ]
    store.save()
    result = ReviewStore(tmp_path / "reviews.json").compare_previous("rev-2")
    assert result["status"] == "no_previous"
    assert "规则版本不同" in result["reason"]


def test_compare_previous_requires_contract_number_and_known_record(tmp_path):
    store = ReviewStore(tmp_path / "reviews.json")
    store.records = [
        make_record("rev-1", "a" * 64, "RULESET-1", [finding("OLD")], contract_id=""),
        make_record("rev-2", "b" * 64, "RULESET-1", [finding("NEW")], contract_id="",
                    reviewed_at="2026-02-01T09:00:00+08:00"),
    ]
    store.save()
    loaded = ReviewStore(tmp_path / "reviews.json")
    result = loaded.compare_previous("rev-2")
    assert result["status"] == "no_previous"
    assert "合同编号" in result["reason"]
    with pytest.raises(ValueError, match="找不到所选复核记录"):
        loaded.compare_previous("missing")


def test_compare_previous_preserves_duplicate_finding_counts(tmp_path):
    repeated = [finding("REPEAT"), finding("REPEAT")]
    store = ReviewStore(tmp_path / "reviews.json")
    store.records = [
        make_record("rev-1", "a" * 64, "RULESET-1", repeated),
        make_record("rev-2", "b" * 64, "RULESET-1", [finding("REPEAT")],
                    reviewed_at="2026-02-01T09:00:00+08:00"),
    ]
    store.save()
    result = ReviewStore(tmp_path / "reviews.json").compare_previous("rev-2")
    assert len(result["unchanged"]) == 1
    assert len(result["resolved"]) == 1
    assert result["added"] == []
