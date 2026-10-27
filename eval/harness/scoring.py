"""Matches reviewer findings to golden cases and computes the metrics in eval/README.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean

from .cases import Case, Task

# Titles/categories that REVIEW.md section 4 says are nitpicks.
NITPICK_CATEGORIES = {"style", "naming", "nitpick", "formatting", "docs", "typo"}
NITPICK_PATTERNS = re.compile(
    r"\b(naming|rename|typo|docstring|type hint|type annotation|import order|line length|formatting|"
    r"whitespace|comment wording|consider (adding|using) (a )?(try|logging|constant)|extra validation|"
    r"defensive|list comprehension|early return)\b", re.I)


@dataclass
class Finding:
    file: str
    line: int
    severity: str = "medium"
    category: str = ""
    title: str = ""
    evidence: str = ""
    failure_scenario: str = ""
    fix: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Finding":
        try:
            line = int(d.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        return Finding(file=str(d.get("file", "")).replace("\\", "/").lstrip("./"), line=line,
                       severity=str(d.get("severity", "medium")).lower(), category=str(d.get("category", "")),
                       title=str(d.get("title", "")), evidence=str(d.get("evidence", "")),
                       failure_scenario=str(d.get("failure_scenario", "")), fix=str(d.get("fix", "")))

    @property
    def text(self) -> str:
        return f"{self.title} {self.evidence} {self.failure_scenario}".lower()

    @property
    def is_nitpick(self) -> bool:
        return (self.severity == "low" or self.category.lower() in NITPICK_CATEGORIES
                or bool(NITPICK_PATTERNS.search(self.title)))

    @property
    def has_scenario(self) -> bool:
        return bool(self.failure_scenario.strip())


def case_matches(case: Case, f: Finding) -> bool:
    if case.line is None or f.file != case.file or abs(f.line - case.line) > case.tolerance:
        return False
    return f.category == case.category or any(k in f.text for k in case.keywords)


@dataclass
class TaskScore:
    task_id: str
    kind: str
    matched: list[str] = field(default_factory=list)       # open case ids found
    missed: list[str] = field(default_factory=list)        # open case ids not found
    regressions: list[str] = field(default_factory=list)   # fixed case ids reported again
    unlabelled: int = 0     # in-scope, non-nitpick findings that match no case (positive tasks)
    false_positives: int = 0  # any non-nitpick finding in a clean/bait task
    nitpicks: int = 0
    no_scenario: int = 0    # findings without a failure scenario (REVIEW.md section 5)
    out_of_scope: int = 0
    total_in_scope: int = 0
    unlabelled_detail: list[dict] = field(default_factory=list)  # for triage: real bug missing from the set, or noise?


def score_task(task: Task, findings: list[Finding]) -> TaskScore:
    s = TaskScore(task.id, task.kind)
    scope = set(task.files)
    in_scope = [f for f in findings if f.file in scope]
    s.out_of_scope = len(findings) - len(in_scope)
    s.total_in_scope = len(in_scope)
    s.no_scenario = sum(1 for f in in_scope if not f.has_scenario)

    used: set[int] = set()
    for case in task.cases:
        candidates = [(abs(f.line - (case.line or 0)), i) for i, f in enumerate(in_scope)
                      if i not in used and case_matches(case, f)]
        if candidates:
            used.add(min(candidates)[1])
            (s.matched if case.is_open else s.regressions).append(case.id)
        elif case.is_open:
            s.missed.append(case.id)

    for i, f in enumerate(in_scope):
        if i in used:
            continue
        if f.is_nitpick:
            s.nitpicks += 1
        elif task.kind == "positive":
            s.unlabelled += 1
            s.unlabelled_detail.append(vars(f))
        else:
            s.false_positives += 1
            s.unlabelled_detail.append(vars(f))
    if task.kind != "positive":
        s.nitpicks += sum(1 for i, f in enumerate(in_scope) if i in used and f.is_nitpick)
    return s


def _ratio(num: float, den: float) -> float | None:
    return None if den == 0 else round(num / den, 4)


def aggregate(scores: list[TaskScore], cases: list[Case], usage: dict, stability: float | None,
              errors: int) -> dict:
    open_cases = {c.id: c for c in cases if c.is_open}
    matched = {cid for s in scores for cid in s.matched}
    high = {cid for cid, c in open_cases.items() if c.severity in ("critical", "high")}
    by_cat: dict[str, list[int]] = {}
    for cid, c in open_cases.items():
        by_cat.setdefault(c.category, []).append(int(cid in matched))
    total_findings = sum(s.total_in_scope for s in scores)
    labelled = sum(len(s.matched) for s in scores)
    unlabelled = sum(s.unlabelled for s in scores)
    return {
        "cases_open": len(open_cases),
        "recall": _ratio(len(matched), len(open_cases)),
        "recall_critical_high": _ratio(len(matched & high), len(high)),
        "recall_by_category": {k: round(mean(v), 4) for k, v in sorted(by_cat.items())},
        "labelled_precision": _ratio(labelled, labelled + unlabelled),  # lower bound: golden set is not exhaustive
        "unlabelled_findings": unlabelled,
        "false_positives_on_clean": sum(s.false_positives for s in scores),
        "nitpicks": sum(s.nitpicks for s in scores),
        "nitpick_rate": _ratio(sum(s.nitpicks for s in scores), total_findings),
        "regressions": sum(len(s.regressions) for s in scores),
        "findings_without_scenario": sum(s.no_scenario for s in scores),
        "total_findings": total_findings,
        "stability": stability,
        "cost_usd": round(usage.get("cost_usd", 0.0), 4),
        "seconds": round(usage.get("seconds", 0.0), 2),
        "reviewer_errors": errors,
        "missed": sorted(cid for cid in open_cases if cid not in matched),
    }


def mean_metrics(per_run: list[dict]) -> dict:
    """Mean of every numeric metric across runs (a single run is returned unchanged). Adds the spread of the
    two headline numbers, and splits missed cases into always-missed and sometimes-missed."""
    if len(per_run) == 1:
        return dict(per_run[0], always_missed=per_run[0]["missed"], sometimes_missed=[])
    out = dict(per_run[0])
    for key, first in per_run[0].items():
        vals = [r[key] for r in per_run]
        if isinstance(first, (int, float)) and not isinstance(first, bool) and all(v is not None for v in vals):
            out[key] = round(mean(vals), 4)
    out["recall_by_category"] = {k: round(mean(r["recall_by_category"].get(k, 0) for r in per_run), 4)
                                 for k in per_run[0]["recall_by_category"]}
    for key in ("recall", "recall_critical_high", "labelled_precision"):
        vals = [r[key] for r in per_run if r[key] is not None]
        out[f"{key}_range"] = [min(vals), max(vals)] if vals else None
    sets = [set(r["missed"]) for r in per_run]
    out["always_missed"] = sorted(set.intersection(*sets))
    out["sometimes_missed"] = sorted(set.union(*sets) - set.intersection(*sets))
    out["missed"] = out["always_missed"] + out["sometimes_missed"]
    return out


def stability_of(runs: list[list[TaskScore]], run_findings: list[list[Finding]]) -> float | None:
    """Mean Jaccard similarity of each later run's finding keys against the first run."""
    if len(runs) < 2:
        return None

    def keys(fs: list[Finding]) -> set:
        return {(f.file, f.line // 10, f.category or f.title[:20].lower()) for f in fs}

    base = keys(run_findings[0])
    sims = []
    for fs in run_findings[1:]:
        k = keys(fs)
        sims.append(1.0 if not base and not k else len(base & k) / len(base | k))
    return round(mean(sims), 4)


TOLERANCES = {"recall": 0.02, "recall_critical_high": 0.0, "labelled_precision": 0.05}
MUST_NOT_RISE = ("false_positives_on_clean", "nitpicks", "regressions", "findings_without_scenario",
                 "reviewer_errors")


def compare_to_baseline(current: dict, baseline: dict) -> list[str]:
    """Returns the ways `current` is worse than `baseline`; empty means no regression."""
    bad = []
    for key, tol in TOLERANCES.items():
        b, c = baseline.get(key), current.get(key)
        if b is not None and (c is None or c < b - tol):
            bad.append(f"{key} fell from {b} to {c} (allowed drop {tol})")
    for key in MUST_NOT_RISE:
        if current.get(key, 0) > baseline.get(key, 0):
            bad.append(f"{key} rose from {baseline.get(key, 0)} to {current.get(key)}")
    return bad
