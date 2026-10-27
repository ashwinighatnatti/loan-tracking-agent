"""Model inversion: review code with a different model family than the one that wrote it.

A model reviewing its own family's output fails in the same ways it wrote them, so catches fewer bugs
(vendor-reported in the research notes; measure it on eval/ before relying on it). Authors are detected from
fingerprints the coding agents leave. Detection is partial (the research reports about 80%); when it fails
the review runs on the default reviewer and the report says inversion was not applied."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .rubric import REPO_ROOT

CONFIG_PATH = REPO_ROOT / "review.toml"

# (family, regex over commit messages / PR text, case-insensitive)
TRAILER_PATTERNS = [
    ("claude", r"co-authored-by:[^\n]*\b(claude|anthropic)\b|generated with \[?claude code"),
    ("gpt", r"co-authored-by:[^\n]*\b(codex|openai|chatgpt)\b|generated (with|by) (codex|chatgpt)"),
    ("gemini", r"co-authored-by:[^\n]*\bgemini\b|generated (with|by) gemini"),
]
BRANCH_PATTERNS = [("gpt", r"^(codex|openai)/"), ("claude", r"^claude/"), ("gemini", r"^gemini/")]
HUMAN = {"human"}


@dataclass
class Detection:
    families: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)


def detect_author(text: str = "", branch: str = "") -> Detection:
    d = Detection()
    for family, pat in TRAILER_PATTERNS:
        m = re.search(pat, text or "", re.I)
        if m:
            d.families.add(family)
            d.evidence.append(f"{family}: commit text '{m.group(0)[:60]}'")
    for family, pat in BRANCH_PATTERNS:
        if re.search(pat, branch or "", re.I):
            d.families.add(family)
            d.evidence.append(f"{family}: branch '{branch}'")
    return d


@dataclass
class Choice:
    family: str
    backend_spec: str
    inverted: bool
    note: str


class InversionError(ValueError):
    pass


def load_families(path: Path = CONFIG_PATH) -> dict[str, str]:
    """{family: backend spec} from review.toml [families], in file order (first is the default)."""
    if not path.is_file():
        return {"claude": "claude-cli"}
    fams = tomllib.loads(path.read_text(encoding="utf-8")).get("families", {})
    if not fams:
        raise InversionError(f"{path.name} has no [families] entries")
    return {str(k): str(v) for k, v in fams.items()}


def parse_author(spec: str, detected: Detection) -> tuple[set[str], str]:
    """`--author`: auto | human | unknown | comma-separated families. Returns (families, how we know)."""
    if spec == "auto":
        return set(detected.families), ("; ".join(detected.evidence) if detected.evidence
                                        else "no fingerprint found")
    if spec in ("human", "unknown"):
        return set(), f"declared {spec}"
    return {s.strip().lower() for s in spec.split(",") if s.strip()}, "declared"


def choose(authors: set[str], families: dict[str, str], evidence: str = "") -> Choice:
    default_family = next(iter(families))
    if not authors:
        return Choice(default_family, families[default_family], False,
                      f"Model inversion not applied: author model unknown ({evidence}).")
    others = [f for f in families if f not in authors]
    if others:
        return Choice(others[0], families[others[0]], True,
                      f"Inverted: author {'/'.join(sorted(authors))} ({evidence}) reviewed by {others[0]}.")
    return Choice(default_family, families[default_family], False,
                  f"Model inversion NOT applied: author {'/'.join(sorted(authors))} ({evidence}) but no other "
                  f"reviewer family is configured in review.toml. Same-family review catches fewer bugs.")


def dump(choice: Choice) -> str:
    return json.dumps(choice.__dict__)
