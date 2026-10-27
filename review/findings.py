"""Turns raw model output into trustworthy findings: parse, ground in the real file, filter noise, dedupe, rank."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from . import rubric

SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
MIN_SCENARIO_CHARS = 25
# Mirrors REVIEW.md section 4. Kept independent of eval/harness so the filter is measured, not shared.
NITPICK_TITLE = re.compile(
    r"\b(naming|rename|typo|docstring|type hints?|type annotations?|import order|line length|formatting|"
    r"whitespace|comment wording|list comprehension|early return|magic number|pep ?8)\b", re.I)


@dataclass
class Finding:
    file: str
    line: int
    severity: str = "medium"
    category: str = "new"
    title: str = ""
    quote: str = ""
    failure_scenario: str = ""
    fix: str = ""
    confidence: float = 0.5
    blast_radius: bool = False
    found_by: list[str] = field(default_factory=list)  # review passes that reported it

    def to_protocol(self) -> dict:
        """Shape the eval harness expects."""
        d = asdict(self)
        d["evidence"] = d.pop("quote")
        return d


@dataclass
class Dropped:
    finding: dict
    reason: str


@dataclass
class Outcome:
    findings: list[Finding] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    not_reviewed: list[str] = field(default_factory=list)


class ParseError(ValueError):
    pass


def parse_reply(text: str) -> tuple[list[dict], str]:
    """Extracts (findings, not_reviewed) from a model reply, tolerating code fences and surrounding prose."""
    body = text.strip()
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body)
    candidates = [body]
    if "{" in body and "}" in body:
        candidates.append(body[body.index("{"): body.rindex("}") + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)], ""
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return [d for d in data["findings"] if isinstance(d, dict)], str(data.get("not_reviewed") or "")
    raise ParseError("reply is not a JSON object with a findings list")


def _norm_with_lines(source: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed text plus, for each character, the 1-based line it came from."""
    chars, lines, line, prev_space = [], [], 1, True
    for ch in source:
        if ch.isspace():
            if not prev_space:
                chars.append(" ")
                lines.append(line)
            prev_space = True
            if ch == "\n":
                line += 1
        else:
            chars.append(ch)
            lines.append(line)
            prev_space = False
    return "".join(chars), lines


_NUMBER_PREFIX = re.compile(r"^\s*\d+\|\s?", re.M)


def locate(quote: str, source: str, near: int) -> int | None:
    """Line where `quote` occurs in `source` (nearest to `near` when it occurs several times)."""
    q = " ".join(_NUMBER_PREFIX.sub("", quote).split())
    if len(q) < 4:
        return None
    norm, lines = _norm_with_lines(source)
    hits, start = [], 0
    while (i := norm.find(q, start)) != -1:
        hits.append(lines[i])
        start = i + 1
    return min(hits, key=lambda ln: abs(ln - near)) if hits else None


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default=0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def process(raw: list[dict], sources: dict[str, str], min_severity: str = "medium",
            min_confidence: float = 0.5, pass_name: str = "") -> Outcome:
    """`sources` maps each in-scope repo-relative path to its full text."""
    out = Outcome()
    floor = SEVERITY_RANK[min_severity]
    kept: list[Finding] = []
    for d in raw:
        file = str(d.get("file", "")).replace("\\", "/").lstrip("./")
        f = Finding(file=file, line=_int(d.get("line")),
                    severity=str(d.get("severity", "medium")).lower(),
                    category=str(d.get("category") or "new"), title=str(d.get("title", "")).strip(),
                    quote=str(d.get("quote") or d.get("evidence") or ""),
                    failure_scenario=str(d.get("failure_scenario", "")).strip(),
                    fix=str(d.get("fix", "")).strip(), confidence=_float(d.get("confidence")),
                    found_by=[pass_name] if pass_name else [])

        def drop(reason: str) -> None:
            out.dropped.append(Dropped(d, reason))

        if f.file not in sources:
            drop("file not in review scope")
        elif f.severity not in SEVERITY_RANK:
            drop(f"unknown severity {f.severity!r}")
        elif SEVERITY_RANK[f.severity] < floor:
            drop(f"below minimum severity ({f.severity})")
        elif len(f.failure_scenario) < MIN_SCENARIO_CHARS:
            drop("no concrete failure scenario")
        elif NITPICK_TITLE.search(f.title):
            drop("nitpick (REVIEW.md section 4)")
        elif f.confidence < min_confidence:
            drop(f"low confidence ({f.confidence})")
        else:
            line = locate(f.quote, sources[f.file], f.line)
            if line is None:
                drop("quote not found in file (possible hallucination)")
                continue
            f.line = line
            if f.category != "new" and f.category not in rubric.catalog_ids():
                f.category = "new"
            f.blast_radius = rubric.touches_blast_radius(f.file)
            kept.append(f)
    out.findings = rank(dedupe(kept, out.dropped))
    return out


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", s.lower()))


def dedupe(findings: list[Finding], dropped: list[Dropped]) -> list[Finding]:
    """Same file, nearby line, and the same category or a similar title count as one finding.
    When different passes report it, the kept finding records all of them and gains confidence:
    independent agreement is the strongest evidence of a real defect that we have."""
    kept: list[Finding] = []
    for f in sorted(findings, key=lambda x: (-SEVERITY_RANK[x.severity], -x.confidence)):
        for k in kept:
            if k.file == f.file and abs(k.line - f.line) <= 3:
                a, b = _words(k.title), _words(f.title)
                if k.category == f.category or (a and b and len(a & b) / len(a | b) > 0.4):
                    before = len(k.found_by)
                    k.found_by = sorted(set(k.found_by) | set(f.found_by))
                    k.confidence = min(1.0, k.confidence + 0.1 * (len(k.found_by) - before))
                    dropped.append(Dropped(asdict(f), f"duplicate of {k.file}:{k.line}"))
                    break
        else:
            kept.append(f)
    return kept


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (-SEVERITY_RANK[f.severity], -f.confidence, f.file, f.line))
