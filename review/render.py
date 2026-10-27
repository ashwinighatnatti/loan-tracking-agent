"""Markdown report for a PR comment or a terminal."""
from __future__ import annotations

from .pipeline import Result
from .rubric import touches_blast_radius


def markdown(res: Result, model: str | None, backend: str) -> str:
    f = res.outcome.findings
    lines = ["# Automated review", "",
             f"Scope: {len(res.files)} file(s). Backend: {backend}" + (f", model: {model}" if model else "")
             + f". Findings: {len(f)} ({len(res.outcome.dropped)} candidates dropped by filters).", ""]
    if res.passes:
        lines += ["Passes: " + "; ".join(
            f"{p.name} {p.kept} kept" + (" (ERROR)" if p.error else "") for p in res.passes), ""]
    ctx = res.context
    if ctx.items or ctx.notes or ctx.omitted:
        kinds = {}
        for i in ctx.items:
            kinds[i.kind] = kinds.get(i.kind, 0) + 1
        lines += ["Context: " + (", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "none")
                  + f" ({ctx.chars} chars" + (f", {ctx.omitted} omitted for budget" if ctx.omitted else "") + ")"
                  + ("; " + "; ".join(ctx.notes) if ctx.notes else ""), ""]
    if res.inversion_note:
        lines += [f"Model inversion: {res.inversion_note}", ""]
    if any(x.blast_radius for x in f) or any(touches_blast_radius(p) for p in res.files):
        lines += ["> **Human review required.** This change touches paths listed in REVIEW.md section 1. "
                  "This automated review advises; it does not approve.", ""]
    if not f:
        lines += ["No findings against REVIEW.md sections 2 and 3 in the scope reviewed. "
                  "This is not evidence that the code has no defects.", ""]
    for i, x in enumerate(f, 1):
        agree = f" · found by {len(x.found_by)}: {', '.join(x.found_by)}" if len(x.found_by) > 1 else \
                (f" · {x.found_by[0]}" if x.found_by else "")
        lines += [f"## {i}. [{x.severity.upper()}] {x.title}",
                  f"`{x.file}:{x.line}` · {x.category} · confidence {x.confidence:.2f}{agree}"
                  + (" · blast radius" if x.blast_radius else ""), "",
                  "```", x.quote.strip(), "```", "",
                  f"**Failure scenario.** {x.failure_scenario}", "", f"**Fix.** {x.fix}", ""]
    if res.outcome.not_reviewed:
        lines += ["## Not reviewed", *[f"- {n}" for n in res.outcome.not_reviewed], ""]
    if res.skipped:
        lines += ["## Skipped", *[f"- {s}" for s in res.skipped], ""]
    if res.errors:
        lines += ["## Errors (these passes/files were NOT reviewed)", *[f"- {e}" for e in res.errors], ""]
    u = res.usage
    lines += ["---", f"{u.calls} call(s), {u.input_tokens + u.output_tokens} tokens, "
                    f"${u.cost_usd:.3f}, {u.seconds:.0f}s"]
    return "\n".join(lines)
