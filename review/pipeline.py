"""One review: build context, run each pass against the backend, ground and filter, merge across passes."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import context, findings, passes as passes_mod, prompt, retrieval
from .backends import Backend, BackendError


@dataclass
class Options:
    model: str | None = None
    min_severity: str = "medium"
    min_confidence: float = 0.5
    allow_answer_key: bool = False
    parallel: bool = True
    context_chars: int = 40_000  # 0 turns the context pack off


@dataclass
class Usage:
    calls: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.cost_usd += other.cost_usd
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens  # seconds is wall time, set by review()


@dataclass
class PassResult:
    name: str
    kept: int = 0
    dropped: int = 0
    usage: Usage = field(default_factory=Usage)
    error: str = ""


@dataclass
class Result:
    outcome: findings.Outcome = field(default_factory=findings.Outcome)
    usage: Usage = field(default_factory=Usage)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    passes: list[PassResult] = field(default_factory=list)
    inversion_note: str = ""
    context: retrieval.Pack = field(default_factory=retrieval.Pack)


def _call(backend: Backend, system: str, user: str, opts: Options, usage: Usage):
    """One model call with a single repair retry when the reply is not parseable."""
    last_err = ""
    for attempt in range(2):
        ask = user if attempt == 0 else (
            user + "\n\nYour previous reply was not valid JSON for the required format "
                   f"({last_err}). Reply again with only the JSON object.")
        start = time.monotonic()
        comp = backend.complete(system, ask, opts.model)
        usage.calls += 1
        usage.seconds += time.monotonic() - start
        usage.cost_usd += comp.cost_usd
        usage.input_tokens += comp.input_tokens
        usage.output_tokens += comp.output_tokens
        try:
            return findings.parse_reply(comp.text)
        except findings.ParseError as exc:
            last_err = str(exc)
    raise findings.ParseError(last_err)


def _run_pass(p: passes_mod.Pass, chunk_batches, sources, intended, diff, backend, opts, related=""):
    pr = PassResult(p.name)
    system = prompt.system_prompt(p)
    raw: list[dict] = []
    not_reviewed: list[str] = []
    for batch in chunk_batches:
        try:
            found, nr = _call(backend, system, prompt.user_prompt(batch, intended, diff, related), opts, pr.usage)
        except (BackendError, findings.ParseError) as exc:
            pr.error = f"[{p.name}] {', '.join(sorted({c.file for c in batch}))}: {exc}"
            continue
        raw += found
        if nr:
            not_reviewed.append(nr)
    out = findings.process(raw, sources, opts.min_severity, opts.min_confidence, p.name)
    pr.kept, pr.dropped = len(out.findings), len(out.dropped)
    return pr, out, not_reviewed


def review(paths: list[str], backend: Backend, opts: Options | None = None, diff: str = "",
           passes: list[passes_mod.Pass] | None = None) -> Result:
    opts = opts or Options()
    passes = passes or [passes_mod.GENERAL]
    res = Result()
    sources: dict[str, str] = {}
    for p in paths:
        p = context.rel(p)
        if context.is_answer_key(p) and not opts.allow_answer_key:
            res.skipped.append(f"{p}: contains the eval answer key")
        elif not (context.REPO_ROOT / p).is_file():
            res.skipped.append(f"{p}: not a file")
        else:
            sources[p] = context.read_source(p)
    res.files = list(sources)
    if not sources:
        return res

    chunks = [c for p, src in sources.items() for c in context.chunks_for(p, src)]
    batches = context.batches(chunks)
    intended = context.intended_behavior(list(sources))
    related = ""
    if opts.context_chars > 0:
        try:  # context is an aid; a failure here must not stop the review
            res.context = retrieval.build_pack(list(sources), budget=opts.context_chars,
                                               changed=retrieval.changed_lines(diff) if diff else None)
            related = res.context.render()
        except Exception as exc:  # noqa: BLE001 - ast/IO problems on odd files
            res.context.notes.append(f"context pack failed: {type(exc).__name__}: {exc}")

    def run(p):
        return _run_pass(p, batches, sources, intended, diff, backend, opts, related)

    started = time.monotonic()
    if opts.parallel and len(passes) > 1:
        with ThreadPoolExecutor(max_workers=len(passes)) as pool:
            done = list(pool.map(run, passes))
    else:
        done = [run(p) for p in passes]
    res.usage.seconds = time.monotonic() - started

    merged: list[findings.Finding] = []
    for pr, out, nr in done:
        res.passes.append(pr)
        res.usage.add(pr.usage)
        if pr.error:
            res.errors.append(pr.error)
        merged += out.findings
        res.outcome.dropped += out.dropped
        res.outcome.not_reviewed += [f"[{pr.name}] {x}" for x in nr]
    # Findings from different passes that describe the same defect collapse; agreement raises confidence.
    res.outcome.findings = findings.rank(findings.dedupe(merged, res.outcome.dropped))
    return res
