"""Replay a reviewer over the golden cases and report catch rate, noise, stability and cost.

    python eval/run_review.py --validate-cases
    python eval/run_review.py --reviewer oracle
    python eval/run_review.py --reviewer "python my_reviewer.py" --runs 3 --check eval/baselines/mine.json
    python eval/run_review.py --reviewer "..." --write-baseline eval/baselines/mine.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import cases as cases_mod  # noqa: E402
from harness import reviewers, scoring  # noqa: E402


def run(reviewer_spec: str, runs: int, only: str | None) -> dict:
    review = reviewers.get(reviewer_spec)
    tasks = [t for t in cases_mod.load_tasks() if not only or only in t.id]
    all_cases = [c for t in tasks for c in t.cases]
    per_run_scores, per_run_findings, per_run_usage, per_run_errors = [], [], [], []
    for n in range(runs):
        scores, found = [], []
        usage = {"cost_usd": 0.0, "seconds": 0.0}
        errors = 0
        for task in tasks:
            result = review(task)
            if result.get("error"):
                errors += 1
                print(f"  reviewer error on {task.id} (run {n + 1}): {result['error']}", file=sys.stderr)
            findings = [scoring.Finding.from_dict(d) for d in result["findings"]]
            scores.append(scoring.score_task(task, findings))
            found.extend(findings)
            for k in ("cost_usd", "seconds"):
                usage[k] += float(result["usage"].get(k, 0) or 0)
        per_run_scores.append(scores)
        per_run_findings.append(found)
        per_run_usage.append(usage)
        per_run_errors.append(errors)
    stability = scoring.stability_of(per_run_scores, per_run_findings)
    per_run = [scoring.aggregate(sc, all_cases, us, stability, er)
               for sc, us, er in zip(per_run_scores, per_run_usage, per_run_errors)]
    metrics = scoring.mean_metrics(per_run)
    return {"reviewer": reviewer_spec, "runs": runs, "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "metrics": metrics, "per_run": per_run,
            "tasks": [vars(s) for s in per_run_scores[0]]}


def print_report(report: dict) -> None:
    m = report["metrics"]
    print(f"reviewer: {report['reviewer']}   runs: {report['runs']}")
    for key in ("cases_open", "recall", "recall_critical_high", "labelled_precision", "unlabelled_findings",
                "false_positives_on_clean", "nitpicks", "nitpick_rate", "regressions",
                "findings_without_scenario", "total_findings", "stability", "cost_usd", "seconds",
                "reviewer_errors"):
        print(f"  {key:28} {m[key]}")
    print("  recall by category:", ", ".join(f"{k}={v}" for k, v in m["recall_by_category"].items()))
    for key in ("recall_range", "recall_critical_high_range", "labelled_precision_range"):
        if m.get(key):
            print(f"  {key:28} {m[key][0]} .. {m[key][1]}")
    if m.get("always_missed") is not None and report["runs"] > 1:
        print("  always missed:   ", ", ".join(m["always_missed"]) or "-")
        print("  sometimes missed:", ", ".join(m["sometimes_missed"]) or "-")
    elif m["missed"]:
        print("  missed:", ", ".join(m["missed"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate-cases", action="store_true", help="check the cases against the repo and exit")
    ap.add_argument("--reviewer", default="oracle", help="oracle | null | noisy | shell command")
    ap.add_argument("--runs", type=int, default=1, help="repeat to measure stability")
    ap.add_argument("--only", help="run only tasks whose id contains this text")
    ap.add_argument("--check", metavar="BASELINE", help="fail if worse than this baseline json")
    ap.add_argument("--write-baseline", metavar="PATH")
    ap.add_argument("--out", metavar="PATH", help="write the full report json here")
    args = ap.parse_args()

    problems = cases_mod.validate()
    if problems:
        print("case problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    if args.validate_cases:
        n = len(cases_mod.load_cases())
        print(f"ok: {n} cases, {len(cases_mod.load_tasks())} tasks")
        return 0

    report = run(args.reviewer, args.runs, args.only)
    print_report(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(report["metrics"], indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {args.write_baseline}")
    if args.check:
        baseline = json.loads(Path(args.check).read_text(encoding="utf-8"))
        bad = scoring.compare_to_baseline(report["metrics"], baseline)
        if bad:
            print("REGRESSION vs " + args.check + ":\n  " + "\n  ".join(bad), file=sys.stderr)
            return 1
        print("no regression vs " + args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
