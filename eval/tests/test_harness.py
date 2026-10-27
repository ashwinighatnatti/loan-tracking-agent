"""Tests of the review-eval harness itself: if the scorer is wrong, every number built on it is wrong."""
import json
import sys

import pytest

from harness import cases as cases_mod
from harness import reviewers, scoring
from harness.cases import Case, Task
from harness.scoring import Finding, score_task


def mk_case(**kw) -> Case:
    base = dict(id="C-X", finding="F-X", severity="high", category="BT-01", file="a.py", keywords=["escrow"],
                summary="s", scenario="sc", anchor="x", line=100, tolerance=8)
    base.update(kw)
    return Case(**base)


def mk_finding(**kw) -> Finding:
    base = dict(file="a.py", line=100, severity="high", category="BT-01", title="t", failure_scenario="boom")
    base.update(kw)
    return Finding(**base)


def run_all(reviewer) -> dict:
    tasks = cases_mod.load_tasks()
    scores = [score_task(t, [Finding.from_dict(d) for d in reviewer(t)["findings"]]) for t in tasks]
    all_cases = [c for t in tasks for c in t.cases]
    return scoring.aggregate(scores, all_cases, {}, None, 0)


# ---- the real case set ----------------------------------------------------------------------

def test_cases_are_consistent_with_the_repo():
    assert cases_mod.validate() == []


def test_oracle_is_perfect():
    m = run_all(reviewers.oracle)
    assert m["recall"] == 1.0 and m["recall_critical_high"] == 1.0
    assert m["false_positives_on_clean"] == 0 and m["nitpicks"] == 0 and m["regressions"] == 0


def test_null_finds_nothing():
    m = run_all(reviewers.null)
    assert m["recall"] == 0.0 and m["total_findings"] == 0 and len(m["missed"]) == m["cases_open"]


def test_noisy_is_penalised_on_noise_but_keeps_recall():
    m = run_all(reviewers.noisy)
    assert m["recall"] == 1.0
    assert m["nitpicks"] > 0 and m["false_positives_on_clean"] > 0 and m["unlabelled_findings"] > 0
    assert m["labelled_precision"] < 1.0 and m["findings_without_scenario"] > 0


def test_reviewer_payload_does_not_leak_the_answer_key():
    for t in cases_mod.load_tasks():
        blob = json.dumps(t.reviewer_payload())
        for c in t.cases:
            assert c.anchor not in blob and c.scenario not in blob and c.id not in blob


def test_every_category_in_cases_exists_in_review_md():
    assert {c.category for c in cases_mod.load_cases()} <= cases_mod.catalog_ids()


# ---- matching rules ---------------------------------------------------------------------------

def test_match_requires_same_file_and_line_window():
    c = mk_case()
    assert scoring.case_matches(c, mk_finding(line=108))
    assert not scoring.case_matches(c, mk_finding(line=109))
    assert not scoring.case_matches(c, mk_finding(file="b.py"))


def test_match_accepts_category_or_keyword():
    c = mk_case()
    assert scoring.case_matches(c, mk_finding(category="BT-01"))
    assert scoring.case_matches(c, mk_finding(category="BT-09", title="escrow compared as Yes"))
    assert not scoring.case_matches(c, mk_finding(category="BT-09", title="something else"))


def test_one_finding_cannot_satisfy_two_cases():
    t = Task("T", "positive", ["a.py"], cases=[mk_case(id="C1", line=100), mk_case(id="C2", line=102)])
    s = score_task(t, [mk_finding(line=101)])
    assert len(s.matched) == 1 and len(s.missed) == 1


def test_unmatched_in_positive_task_is_unlabelled_not_false_positive():
    t = Task("T", "positive", ["a.py"], cases=[mk_case()])
    s = score_task(t, [mk_finding(line=500, category="BT-02", title="other bug")])
    assert s.unlabelled == 1 and s.false_positives == 0 and s.missed == ["C-X"]


def test_any_real_finding_in_clean_task_is_a_false_positive():
    t = Task("T", "clean", ["a.py"])
    s = score_task(t, [mk_finding(), mk_finding(severity="low", category="naming")])
    assert s.false_positives == 1 and s.nitpicks == 1


def test_out_of_scope_findings_are_ignored():
    t = Task("T", "positive", ["a.py"], cases=[mk_case()])
    s = score_task(t, [mk_finding(file="other.py")])
    assert s.out_of_scope == 1 and s.total_in_scope == 0 and s.unlabelled == 0


def test_reporting_a_fixed_case_again_is_a_regression_not_a_hit():
    t = Task("T", "positive", ["a.py"], cases=[mk_case(status="fixed")])
    s = score_task(t, [mk_finding()])
    assert s.regressions == ["C-X"] and s.matched == [] and s.missed == []


@pytest.mark.parametrize("finding, nit", [
    (dict(severity="low"), True),
    (dict(category="Naming"), True),
    (dict(title="Rename this variable"), True),
    (dict(title="Missing docstring"), True),
    (dict(title="Escrow compared with Yes", severity="critical"), False),
])
def test_nitpick_classification(finding, nit):
    assert mk_finding(**finding).is_nitpick is nit


def test_finding_parsing_is_forgiving():
    f = Finding.from_dict({"file": ".\\loan_agent\\x.py", "line": "12", "severity": "HIGH"})
    assert f.file == "loan_agent/x.py" and f.line == 12 and f.severity == "high"
    assert Finding.from_dict({"line": "n/a"}).line == 0


# ---- validation catches drift -------------------------------------------------------------------

def test_validate_flags_a_missing_or_ambiguous_anchor(monkeypatch):
    base = cases_mod.load_cases()
    gone = mk_case(id="C-GONE", file="REVIEW.md", anchor="THIS TEXT IS NOT THERE", category="BT-01")
    twice = mk_case(id="C-TWICE", file="REVIEW.md", anchor="the", category="BT-01")
    monkeypatch.setattr(cases_mod, "load_cases", lambda: base + [gone, twice])
    problems = "\n".join(cases_mod.validate())
    assert "C-GONE" in problems and "C-TWICE" in problems


def test_validate_flags_fixed_case_whose_anchor_is_still_present(monkeypatch):
    base = cases_mod.load_cases()
    c = mk_case(id="C-STILL", file="REVIEW.md", anchor="Blast radius", status="fixed", category="BT-01")
    monkeypatch.setattr(cases_mod, "load_cases", lambda: base + [c])
    assert any("C-STILL" in p and "still in" in p for p in cases_mod.validate())


# ---- aggregate, stability, baseline -------------------------------------------------------------

def test_stability_is_jaccard_against_first_run():
    a = [mk_finding(line=10), mk_finding(line=50)]
    b = [mk_finding(line=10)]
    assert scoring.stability_of([[], []], [a, a]) == 1.0
    assert scoring.stability_of([[], []], [a, b]) == 0.5
    assert scoring.stability_of([[]], [a]) is None


def test_mean_metrics_reports_spread_and_flaky_misses():
    def run(recall, missed, nit):
        return {"recall": recall, "recall_critical_high": recall, "labelled_precision": None, "nitpicks": nit,
                "recall_by_category": {"BT-01": recall}, "missed": missed, "cost_usd": 1.0, "stability": 0.8}
    m = scoring.mean_metrics([run(0.8, ["A", "B"], 0), run(0.6, ["A", "C"], 2)])
    assert m["recall"] == 0.7 and m["recall_range"] == [0.6, 0.8] and m["nitpicks"] == 1.0
    assert m["always_missed"] == ["A"] and m["sometimes_missed"] == ["B", "C"]
    assert m["labelled_precision"] is None and m["recall_by_category"] == {"BT-01": 0.7}
    one = scoring.mean_metrics([run(0.5, ["A"], 0)])
    assert one["recall"] == 0.5 and one["always_missed"] == ["A"] and one["sometimes_missed"] == []


def test_baseline_comparison():
    base = {"recall": 0.8, "recall_critical_high": 1.0, "labelled_precision": 0.9, "nitpicks": 2,
            "false_positives_on_clean": 0}
    ok = dict(base, recall=0.79)
    assert scoring.compare_to_baseline(ok, base) == []
    bad = dict(base, recall=0.5, recall_critical_high=0.9, nitpicks=3, false_positives_on_clean=1)
    msgs = "\n".join(scoring.compare_to_baseline(bad, base))
    for key in ("recall ", "recall_critical_high", "nitpicks", "false_positives_on_clean"):
        assert key in msgs


# ---- command reviewers ---------------------------------------------------------------------------

def _cmd(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_command_reviewer_round_trip():
    code = ("import sys,json; p=json.load(sys.stdin); "
            "print(json.dumps({'findings':[{'file':p['files'][0],'line':1,'severity':'high','title':'x',"
            "'failure_scenario':'y'}],'usage':{'cost_usd':0.5}}))")
    t = Task("T", "positive", ["a.py"])
    r = reviewers.command_reviewer(_cmd(code))(t)
    assert r["error"] is None and r["findings"][0]["file"] == "a.py" and r["usage"]["cost_usd"] == 0.5
    assert r["usage"]["seconds"] >= 0


def test_command_reviewer_failure_is_reported_not_raised():
    t = Task("T", "positive", ["a.py"])
    assert "exit 3" in reviewers.command_reviewer(_cmd("import sys; sys.exit(3)"))(t)["error"]
    assert "JSONDecodeError" in reviewers.command_reviewer(_cmd("print('not json')"))(t)["error"]
