"""Inspection helpers for the reviewer: preview a context pack, summarize a saved run. No model calls."""
from __future__ import annotations

import json
from collections import Counter

from . import retrieval


def show_context(paths: list[str], full: bool = False) -> int:
    """What the reviewer would be shown around these files (python -m review context <files> [--full])."""
    for f in paths:
        pack = retrieval.build_pack([f])
        print(f"== {f}: {len(pack.items)} items, {pack.chars} chars, {pack.omitted} omitted for budget")
        for note in pack.notes:
            print("   note:", note)
        for i in pack.items:
            print(f"   {i.kind:12} {i.path}:{i.start}-{i.end}  {i.why[:80]}")
            if full:
                print(i.text)
    return 0


def summarize(path: str) -> int:
    """One-screen summary of a `python -m review ... --json out.json` file (python -m review summarize <json>)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    print("usage:", {k: round(v, 3) for k, v in d["usage"].items()})
    print("passes:", [(p["name"], p["kept"], p["error"] or "ok") for p in d["passes"]])
    print("context:", dict(Counter(i["kind"] for i in d.get("context", []))), "omitted", d.get("context_omitted"),
          d.get("context_notes") or "")
    print("errors:", d["errors"])
    print(f"findings: {len(d['findings'])}, dropped: {len(d['dropped'])} "
          f"({dict(Counter(x['reason'].split(' (')[0][:32] for x in d['dropped']))})")
    for f in d["findings"]:
        print(f"  {f['severity']:8} {f['file'].split('/')[-1]}:{f['line']} {f['category']:6} "
              f"x{len(f['found_by'])} {f['title'][:105]}")
    return 0
