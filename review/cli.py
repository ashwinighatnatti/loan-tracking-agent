"""Command line.

    python -m review files loan_agent/rules/line_rules.py [more files]
    python -m review diff --base main            # files changed vs a base branch (also --staged)
    python -m review --protocol                  # eval/run_review.py reviewer protocol on stdin/stdout
    python -m review context <files> [--full]    # preview the context pack (no model call)
    python -m review summarize <review.json>     # summarize a saved --json run

Passes: --passes all (default: correctness, safety, robustness in parallel) | general | comma list.
Model inversion: the author's model family is read from commit trailers and the branch name (--author auto),
or declared (--author claude|gpt|gemini|human). The reviewer is then the first family in review.toml that
differs. --backend fixes the reviewer and turns inversion off.
Environment defaults: REVIEW_BACKEND, REVIEW_MODEL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import backends, context, inversion, passes, render, tools
from .pipeline import Options, review

# Exit codes for CI: 0 clean, 1 findings, 2 usage/backend failure (nothing was reviewed).
EXIT_CLEAN, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2


def run_protocol(backend, opts: Options, review_passes=None, note: str = "") -> int:
    """Reads one eval task as JSON on stdin and prints {"findings": [...], "usage": {...}}."""
    task = json.load(sys.stdin)
    opts.allow_answer_key = False  # measurement runs must never see the answers
    res = review(task["files"], backend, opts, passes=review_passes)
    if res.errors and not res.outcome.findings:
        print("; ".join(res.errors), file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps({"findings": [f.to_protocol() for f in res.outcome.findings],
                      "usage": {"cost_usd": res.usage.cost_usd, "input_tokens": res.usage.input_tokens,
                                "output_tokens": res.usage.output_tokens}}))
    return EXIT_CLEAN


def pick_backend(args, commit_text: str, branch: str):
    """Returns (backend, note). An explicit --backend wins and disables inversion."""
    explicit = args.backend or os.environ.get("REVIEW_BACKEND")
    if explicit:
        return backends.get(explicit), f"Reviewer fixed by --backend {explicit}; inversion not applied."
    families = inversion.load_families()
    authors, how = inversion.parse_author(args.author, inversion.detect_author(commit_text, branch))
    choice = inversion.choose(authors, families, how)
    return backends.get(choice.backend_spec), choice.note


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m review", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=["files", "diff", "context", "summarize"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--protocol", action="store_true")
    ap.add_argument("--full", action="store_true", help="context mode: print the gathered code, not just the list")
    ap.add_argument("--backend", help="claude-cli | anthropic | command:<cmd>; fixes the reviewer")
    ap.add_argument("--model", default=os.environ.get("REVIEW_MODEL"))
    ap.add_argument("--passes", default="all")
    ap.add_argument("--author", default="auto", help="auto | human | unknown | claude | gpt | gemini | a,b")
    ap.add_argument("--base", help="diff mode: base branch or commit")
    ap.add_argument("--staged", action="store_true", help="diff mode: staged changes")
    ap.add_argument("--min-severity", default="medium", choices=["low", "medium", "high", "critical"])
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--context-chars", type=int, default=40_000,
                    help="budget for the context pack of declarations, callees, callers and tests; 0 = off")
    ap.add_argument("--allow-answer-key", action="store_true",
                    help="allow reviewing docs/code-review-findings.md and eval/cases (never for measured runs)")
    ap.add_argument("--out", help="write the Markdown report here")
    ap.add_argument("--json", dest="json_out", help="write findings (and dropped candidates) as JSON here")
    args = ap.parse_args(argv)

    if args.mode in ("context", "summarize"):  # inspection only: no backend, no model call
        if not args.paths:
            ap.error(f"`{args.mode}` needs at least one path")
        return tools.show_context(args.paths, args.full) if args.mode == "context" else tools.summarize(args.paths[0])

    try:
        review_passes = passes.select(args.passes)
        commit_text = context.git_commit_text(args.base) if not args.protocol else ""
        branch = context.git_branch() if not args.protocol else ""
        backend, note = pick_backend(args, commit_text, branch)
    except (ValueError, backends.BackendError) as exc:  # InversionError is a ValueError
        print(exc, file=sys.stderr)
        return EXIT_ERROR
    opts = Options(args.model, args.min_severity, args.min_confidence, args.allow_answer_key,
                   context_chars=args.context_chars)

    if args.protocol:
        return run_protocol(backend, opts, review_passes, note)
    if args.mode is None:
        ap.error("choose `files`, `diff`, or --protocol")

    diff = ""
    if args.mode == "files":
        paths = args.paths
        if not paths:
            ap.error("`files` needs at least one path")
    else:
        paths = context.git_changed_files(args.base, args.staged)
        if not paths:
            print("no changed files")
            return EXIT_CLEAN
        diff = context.git_diff(args.base, args.staged, paths)

    res = review(paths, backend, opts, diff, review_passes)
    res.inversion_note = note
    report = render.markdown(res, args.model, backend.name)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"findings": [f.__dict__ for f in res.outcome.findings],
                       "dropped": [{"reason": d.reason, "finding": d.finding} for d in res.outcome.dropped],
                       "passes": [{"name": p.name, "kept": p.kept, "dropped": p.dropped, "error": p.error,
                                   "cost_usd": p.usage.cost_usd} for p in res.passes],
                       "context": [{"kind": i.kind, "path": i.path, "lines": [i.start, i.end], "why": i.why}
                                   for i in res.context.items],
                       "context_omitted": res.context.omitted, "context_notes": res.context.notes,
                       "inversion": note, "errors": res.errors, "skipped": res.skipped,
                       "usage": res.usage.__dict__}, fh, indent=2)
    if res.errors or not res.files:
        return EXIT_ERROR
    return EXIT_FINDINGS if res.outcome.findings else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
