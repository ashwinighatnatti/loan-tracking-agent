"""Per-run and per-subset view of a multi-run report, so configurations can be compared like for like.

    python eval/compare_runs.py eval/results/measure-A.json [more.json ...]

Case subsets: `original` = the 28 cases from the first audit (C-F*), `triaged` = the 8 added from triage (C-T*).
"""
import json
import sys


def recall(missed: set, ids: list) -> float:
    return round(1 - len(missed & set(ids)) / len(ids), 3)


def main(paths: list[str]) -> int:
    for path in paths:
        r = json.load(open(path, encoding="utf-8"))
        runs = r["per_run"]
        all_ids = sorted(set().union(*[set(x["missed"]) for x in runs]))
        print(f"== {path}  ({r['reviewer'].split('-m ')[-1]})")
        # Case ids are not stored for found cases, so rebuild the universe from the case file.
        from pathlib import Path
        import yaml
        cases = yaml.safe_load((Path(__file__).parent / "cases" / "positives.yaml").read_text(encoding="utf-8"))
        ids = [c["id"] for c in cases if c.get("status", "open") == "open"]
        orig = [i for i in ids if i.startswith("C-F")]
        new = [i for i in ids if i.startswith("C-T")]
        print(f"{'run':>3} {'recall':>7} {'orig28':>7} {'triaged8':>8} {'C+H':>6} {'prec':>6} {'unlab':>6} "
              f"{'FP':>3} {'nit':>4} {'find':>5} {'cost$':>6} {'sec':>6} {'err':>3}")
        for n, x in enumerate(runs, 1):
            m = set(x["missed"])
            print(f"{n:>3} {x['recall']:>7} {recall(m, orig):>7} {recall(m, new):>8} {x['recall_critical_high']:>6} "
                  f"{x['labelled_precision']!s:>6} {x['unlabelled_findings']:>6} {x['false_positives_on_clean']:>3} "
                  f"{x['nitpicks']:>4} {x['total_findings']:>5} {x['cost_usd']:>6} {x['seconds']:>6} {x['reviewer_errors']:>3}")
        m = r["metrics"]
        print(f"mean recall {m['recall']} (orig28 {round(sum(recall(set(x['missed']), orig) for x in runs) / len(runs), 3)}, "
              f"triaged8 {round(sum(recall(set(x['missed']), new) for x in runs) / len(runs), 3)}); "
              f"stability {m['stability']}; cost/run {m['cost_usd']}")
        print("always missed:  ", ", ".join(m["always_missed"]) or "-")
        print("sometimes missed:", ", ".join(m["sometimes_missed"]) or "-")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
