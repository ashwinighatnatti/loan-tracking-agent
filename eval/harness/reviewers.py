"""Reviewers the harness can drive.

Built in: `oracle` (returns the answer key, so recall must be 1.0), `null` (finds nothing),
`noisy` (oracle plus nitpicks and a bogus finding, so the noise metrics must move).
Anything else is a shell command: the task payload goes to its stdin as JSON and it prints
{"findings": [...], "usage": {...}} to stdout. See eval/README.md.
"""
from __future__ import annotations

import json
import subprocess
import time

from .cases import Task

Result = dict  # {"findings": [...], "usage": {...}, "error": str | None}


def _oracle_findings(task: Task) -> list[dict]:
    return [{"file": c.file, "line": c.line, "severity": c.severity, "category": c.category,
             "title": c.summary, "evidence": c.anchor, "failure_scenario": c.scenario,
             "fix": "see docs/code-review-findings.md " + c.finding}
            for c in task.cases if c.is_open and c.line]


def oracle(task: Task) -> Result:
    return {"findings": _oracle_findings(task), "usage": {}}


def null(task: Task) -> Result:
    return {"findings": [], "usage": {}}


def noisy(task: Task) -> Result:
    out = _oracle_findings(task)
    for f in task.files:
        out.append({"file": f, "line": 1, "severity": "low", "category": "naming",
                    "title": "Rename variable for clarity", "failure_scenario": ""})
        out.append({"file": f, "line": 2, "severity": "medium", "category": "BT-03",
                    "title": "Possible off-by-one in the loop bound",
                    "failure_scenario": "An empty list raises IndexError."})
    return {"findings": out, "usage": {}}


BUILTIN = {"oracle": oracle, "null": null, "noisy": noisy}


def command_reviewer(command: str, timeout: int = 900):
    def run(task: Task) -> Result:
        start = time.monotonic()
        try:
            proc = subprocess.run(command, input=json.dumps(task.reviewer_payload()), shell=True,
                                  capture_output=True, text=True, timeout=timeout)
            if proc.returncode != 0:
                return {"findings": [], "usage": {}, "error": f"exit {proc.returncode}: {proc.stderr[-300:]}"}
            data = json.loads(proc.stdout)
            findings = data.get("findings", []) if isinstance(data, dict) else data
            usage = dict(data.get("usage", {})) if isinstance(data, dict) else {}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            return {"findings": [], "usage": {}, "error": f"{type(exc).__name__}: {exc}"}
        usage["seconds"] = time.monotonic() - start
        return {"findings": findings, "usage": usage, "error": None}
    return run


def get(spec: str):
    return BUILTIN[spec] if spec in BUILTIN else command_reviewer(spec)
