"""Builds the code the model is shown. The model has no tools: what is here is all it can see."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .rubric import REPO_ROOT, RULES_DOC

MAX_CHUNK_LINES = 700
CHUNK_OVERLAP = 40
BATCH_CHARS = 90_000
MAX_RULES_CHARS = 30_000
# Files that contain the answers to the review-eval. Never shown in protocol (measurement) mode.
ANSWER_KEY = ("docs/code-review-findings.md", "eval/cases/")


def rel(path: str | Path) -> str:
    p = Path(path)
    if p.is_absolute():
        p = p.resolve().relative_to(REPO_ROOT)
    return p.as_posix().lstrip("./")


def is_answer_key(path: str) -> bool:
    return any(path == k or path.startswith(k) for k in ANSWER_KEY)


@dataclass
class Chunk:
    file: str
    start: int  # 1-based, inclusive
    end: int
    text: str   # numbered lines

    def render(self) -> str:
        span = "" if self.start == 1 and self.end == self.text.count("\n") + 1 else f' lines="{self.start}-{self.end}"'
        return f'<file path="{self.file}"{span}>\n{self.text}\n</file>'


def read_source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")


def chunks_for(path: str, source: str | None = None) -> list[Chunk]:
    lines = (source if source is not None else read_source(path)).splitlines()
    out, start = [], 0
    while True:
        end = min(start + MAX_CHUNK_LINES, len(lines))
        body = "\n".join(f"{i + 1:5d}| {lines[i]}" for i in range(start, end))
        out.append(Chunk(path, start + 1, end, body))
        if end >= len(lines):
            return out
        start = end - CHUNK_OVERLAP


def batches(chunks: list[Chunk]) -> list[list[Chunk]]:
    """Greedy grouping so several small files share one model call."""
    out: list[list[Chunk]] = []
    size = 0
    for c in chunks:
        if not out or size + len(c.text) > BATCH_CHARS:
            out.append([])
            size = 0
        out[-1].append(c)
        size += len(c.text)
    return out


def intended_behavior(files: list[str]) -> str:
    """processing-rules.md when any reviewed file is loan logic, so the model can check code against it."""
    if not any(f.startswith("loan_agent/") and "/mocks/" not in f for f in files) or not RULES_DOC.is_file():
        return ""
    text = RULES_DOC.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_RULES_CHARS:
        text = text[:MAX_RULES_CHARS] + "\n[truncated]"
    return text


def git_changed_files(base: str | None, staged: bool) -> list[str]:
    args = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    args += ["--cached"] if staged else ([f"{base}...HEAD"] if base else ["HEAD"])
    out = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def git_commit_text(base: str | None) -> str:
    """Commit messages being reviewed, where coding agents leave author trailers. Empty if unavailable."""
    if not base:
        return ""
    proc = subprocess.run(["git", "log", f"{base}..HEAD", "--format=%B"], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


def git_branch() -> str:
    proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_diff(base: str | None, staged: bool, files: list[str]) -> str:
    args = ["git", "diff", "--unified=3"]
    args += ["--cached"] if staged else ([f"{base}...HEAD"] if base else ["HEAD"])
    return subprocess.run(args + ["--", *files], cwd=REPO_ROOT, capture_output=True, text=True,
                          check=True).stdout
