"""Print the unlabelled findings of a run report so a person can decide: real bug (add a case) or noise (tighten a filter).

    python eval/triage.py eval/results/claude-cli-run3.json
"""
import json
import sys


def main(path: str) -> int:
    report = json.load(open(path, encoding="utf-8"))
    errors = report["metrics"]["reviewer_errors"]
    if errors:
        print(f"WARNING: {errors} reviewer error(s) in this run; it is incomplete.\n")
    n = 0
    for task in report["tasks"]:
        for f in task["unlabelled_detail"]:
            n += 1
            print(f"#{n} [{task['kind']}] {f['file']}:{f['line']} {f['severity']} {f['category']}")
            print("   title:   ", f["title"])
            print("   quote:   ", f["evidence"].strip().replace("\n", " | ")[:200])
            print("   scenario:", f["failure_scenario"][:350])
            print()
    print(f"{n} unlabelled findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
