"""review/ (the product) and eval/ (the instrument that measures it) must not depend on each other's code.

If the measurer shares code with the measured, a bug in the shared part passes both. See review/README.md and
eval/README.md, section Boundary. The only sanctioned coupling is path *strings* (the answer-key guard list)."""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVIEW_FILES = sorted((ROOT / "review").rglob("*.py"))
EVAL_FILES = sorted((ROOT / "eval").rglob("*.py"))

# eval/ is on sys.path during tests (pytest.ini), so its modules can be imported by bare name.
EVAL_MODULES = {"eval", "harness", "run_review", "compare_runs"}
REVIEW_MODULES = {"review"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_both_sides_are_actually_found():
    assert len(REVIEW_FILES) >= 10 and len(EVAL_FILES) >= 8  # a path typo must not make the tests vacuous


@pytest.mark.parametrize("path", REVIEW_FILES, ids=rel)
def test_review_does_not_import_eval(path):
    assert not imported_modules(path) & EVAL_MODULES, f"{rel(path)} imports eval code"


@pytest.mark.parametrize("path", EVAL_FILES, ids=rel)
def test_eval_does_not_import_review(path):
    assert not imported_modules(path) & REVIEW_MODULES, f"{rel(path)} imports reviewer code"


def test_review_holds_no_case_ids_or_case_files():
    for path in REVIEW_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\bC-[FT]\d", text), f"{rel(path)} mentions an eval case id"
        assert "positives.yaml" not in text and "clean.yaml" not in text, f"{rel(path)} reads eval cases"


def test_eval_holds_no_reviewer_prompt_or_pipeline():
    forbidden = ("system_prompt", "OUTPUT_SPEC", "SHORT_SYSTEM", "build_pack", "ClaudeCli")
    for path in EVAL_FILES:
        if path.name == "test_harness.py":
            continue  # asserts on the protocol payload, mentions none of these as code
        text = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{rel(path)} contains reviewer internals ({word})"


def test_the_only_eval_reference_in_review_is_the_answer_key_guard():
    """review/ may name eval paths as strings, but only in the two sanctioned guard lists."""
    allowed = {"review/context.py", "review/retrieval.py", "review/README.md"}
    offenders = []
    for path in REVIEW_FILES:
        if rel(path) in allowed:
            continue
        if re.search(r"""["']eval[/"']""", path.read_text(encoding="utf-8")):
            offenders.append(rel(path))
    assert offenders == []


def test_the_shared_contract_exists_at_the_root():
    assert (ROOT / "REVIEW.md").is_file()
