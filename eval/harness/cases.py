"""Loads golden cases, resolves anchors to line numbers, and validates them against the repo."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parent
CASES_DIR = EVAL_DIR / "cases"
REVIEW_MD = REPO_ROOT / "REVIEW.md"

SEVERITIES = ("critical", "high", "medium", "low")
TASK_KINDS = ("positive", "clean", "nitpick_bait")
DEFAULT_TOLERANCE = 8


@dataclass
class Case:
    id: str
    finding: str
    severity: str
    category: str
    file: str
    keywords: list[str]
    summary: str
    scenario: str
    anchor: str = ""
    status: str = "open"
    tolerance: int = DEFAULT_TOLERANCE
    context_files: list[str] = field(default_factory=list)
    line: int | None = None  # resolved from the anchor, or given for status: fixed

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass
class Task:
    """One unit of review work: a scope of files and the cases expected inside it."""
    id: str
    kind: str
    files: list[str]
    description: str = ""
    cases: list[Case] = field(default_factory=list)

    def reviewer_payload(self) -> dict:
        """What a reviewer is allowed to see. Never includes the expected cases."""
        return {
            "task_id": self.id,
            "files": self.files,
            "repo_root": str(REPO_ROOT),
            "rubric": str(REVIEW_MD),
            "instructions": "Review the listed files against the rubric. Report findings in the format of "
                            "REVIEW.md section 5 as JSON: {\"findings\": [{file, line, severity, category, "
                            "title, evidence, failure_scenario, fix}], \"usage\": {cost_usd, input_tokens, "
                            "output_tokens}}. file is relative to repo_root. Report nothing you cannot support.",
        }


def _read_yaml(name: str) -> list[dict]:
    return yaml.safe_load((CASES_DIR / name).read_text(encoding="utf-8")) or []


def _case_from_dict(raw: dict) -> Case:
    raw = dict(raw)
    raw["keywords"] = [k.lower() for k in raw.get("keywords", [])]
    raw.setdefault("tolerance", DEFAULT_TOLERANCE)
    raw["context_files"] = raw.get("context_files", [])
    return Case(**raw)


def find_anchor_lines(file: str, anchor: str) -> list[int]:
    """1-based line numbers where `anchor` starts. Empty when the file is missing."""
    path = REPO_ROOT / file
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return [text.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(anchor), text)]


def resolve(case: Case) -> Case:
    if case.is_open and case.anchor:
        lines = find_anchor_lines(case.file, case.anchor)
        if len(lines) == 1:
            case.line = lines[0]
    return case


def load_cases() -> list[Case]:
    return [resolve(_case_from_dict(r)) for r in _read_yaml("positives.yaml")]


def load_tasks() -> list[Task]:
    """Positive tasks (one per file, open and fixed cases) plus the clean and bait tasks."""
    by_file: dict[str, Task] = {}
    for case in load_cases():
        task = by_file.setdefault(case.file, Task(
            id="T-" + re.sub(r"[^A-Za-z0-9]+", "-", case.file).strip("-"),
            kind="positive", files=[case.file], description=f"Defects known in {case.file}"))
        task.cases.append(case)
    tasks = list(by_file.values())
    for raw in _read_yaml("clean.yaml"):
        tasks.append(Task(id=raw["id"], kind=raw["kind"], files=raw["files"],
                          description=raw.get("description", "")))
    return tasks


def catalog_ids() -> set[str]:
    return set(re.findall(r"\bBT-\d{2}\b", REVIEW_MD.read_text(encoding="utf-8")))


def validate() -> list[str]:
    """Returns a list of problems; empty means the case set is consistent with the repo."""
    problems: list[str] = []
    catalog = catalog_ids()
    seen: set[str] = set()
    for case in load_cases():
        where = f"{case.id}"
        if case.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(case.id)
        if case.severity not in SEVERITIES:
            problems.append(f"{where}: bad severity {case.severity!r}")
        if case.category not in catalog:
            problems.append(f"{where}: category {case.category!r} is not in the REVIEW.md catalog")
        if not case.keywords:
            problems.append(f"{where}: needs keywords")
        if case.status not in ("open", "fixed"):
            problems.append(f"{where}: bad status {case.status!r}")
        for f in [case.file, *case.context_files]:
            if not (REPO_ROOT / f).is_file():
                problems.append(f"{where}: file not found: {f}")
        lines = find_anchor_lines(case.file, case.anchor) if case.anchor else []
        if case.is_open:
            if len(lines) != 1:
                problems.append(f"{where}: anchor must occur exactly once in {case.file}, found {len(lines)}"
                                " (if the defect was fixed, set status: fixed and give its old line)")
        else:
            if lines:
                problems.append(f"{where}: status is fixed but the anchor is still in {case.file}")
            if case.line is None:
                problems.append(f"{where}: status fixed needs the old `line`")
    for raw in _read_yaml("clean.yaml"):
        if raw.get("kind") not in TASK_KINDS[1:]:
            problems.append(f"{raw.get('id')}: bad kind {raw.get('kind')!r}")
        for f in raw.get("files", []):
            if not (REPO_ROOT / f).is_file():
                problems.append(f"{raw.get('id')}: fixture not found: {f}")
    return problems
