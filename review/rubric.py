"""Reads REVIEW.md, the single source of truth for what the reviewer looks for and what it must not report."""
from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_MD = REPO_ROOT / "REVIEW.md"
RULES_DOC = REPO_ROOT / "loan_agent" / "workflow" / "processing-rules.md"


@lru_cache(maxsize=1)
def _text() -> str:
    return REVIEW_MD.read_text(encoding="utf-8")


def section(number: int) -> str:
    """The body of '## <number>. ...' in REVIEW.md, heading included."""
    m = re.search(rf"^## {number}\. .*?(?=^## \d+\. |\Z)", _text(), re.S | re.M)
    if not m:
        raise ValueError(f"REVIEW.md has no section {number}")
    return m.group(0).strip()


def catalog_ids() -> set[str]:
    return set(re.findall(r"\bBT-\d{2}\b", section(3)))


@lru_cache(maxsize=1)
def blast_radius_patterns() -> tuple[str, ...]:
    """Backticked paths in the first column of the section 1 table."""
    patterns: list[str] = []
    for line in section(1).splitlines():
        if line.startswith("| `"):
            first_cell = line.split("|")[1]
            patterns += re.findall(r"`([^`]+)`", first_cell)
    return tuple(patterns)


def touches_blast_radius(path: str) -> bool:
    """True when `path` (repo-relative) is covered by a section 1 pattern. Patterns may be written
    relative to loan_agent/."""
    path = path.replace("\\", "/").lstrip("./")
    for pattern in blast_radius_patterns():
        for candidate in (pattern, "loan_agent/" + pattern):
            if candidate.endswith(("/", "**")):
                if path.startswith(candidate.rstrip("*")):
                    return True
            elif fnmatch.fnmatch(path, candidate):
                return True
    return False
