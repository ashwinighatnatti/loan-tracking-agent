"""Phase 5: the context pack (declarations, callees, callers, tests) found by static analysis."""
import json
from pathlib import Path

import pytest

from review import backends, passes, pipeline, prompt, retrieval
from review.backends import Completion

FILES = {
    "app/__init__.py": "",
    "app/models.py": 'class Base:\n    note: str = ""\n\n\nclass Doc(Base):\n    payee: str = ""\n    wind: bool = False\n',
    "app/util.py": "def same(a, b):\n    return a == b\n\n\ndef unused():\n    return 1\n",
    "app/rules.py": ("from . import util\nfrom .models import Doc\n\n\ndef run(doc: Doc):\n"
                     "    return util.same(doc.payee, 'x')\n\n\ndef other(doc: Doc):\n    return util.unused()\n"),
    "app/other.py": "from app.rules import run\n\n\ndef go(d):\n    return run(d)\n",
    "app/broken.py": "def oops(:\n    pass\n",
    "tests/test_rules.py": "from app.rules import run\n\n\ndef test_run():\n    run(None)\n",
    "eval/cases/answers.py": "SECRET = 1\n",
    "docs/note.md": "not python\n",
}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def kinds(pack):
    return [(i.kind, i.path) for i in pack.items]


def test_index_skips_eval_and_non_python_and_survives_a_file_that_does_not_parse(repo):
    idx = retrieval.Index(repo)
    assert "eval/cases/answers.py" not in idx.files and "docs/note.md" not in idx.files
    assert idx.files["app/broken.py"].tree is None and "does not parse" in idx.files["app/broken.py"].error
    assert idx.module_file("app.rules", "app/other.py", 0) == "app/rules.py"
    assert idx.module_file("models", "app/rules.py", 1) == "app/models.py"


def test_pack_has_declarations_with_defaults_and_base_classes(repo):
    pack = retrieval.build_pack(["app/rules.py"], root=repo)
    decls = [i for i in pack.items if i.kind == "declaration"]
    assert [d.path for d in decls] == ["app/models.py", "app/models.py"]
    text = "\n".join(d.text for d in decls)
    assert 'payee: str = ""' in text and "wind: bool = False" in text and 'note: str = ""' in text  # Doc and Base
    assert "class Doc(Base)" in text and "    5| class Doc(Base):" in text  # real line numbers


def test_pack_has_callees_callers_tests_and_untested_note(repo):
    pack = retrieval.build_pack(["app/rules.py"], root=repo)
    by_kind = {k: [i for i in pack.items if i.kind == k] for k in ("callee", "caller", "test", "note")}
    assert {c.text.split("|")[1].strip().split("(")[0] for c in by_kind["callee"]} == {"def same", "def unused"}
    assert [c.path for c in by_kind["caller"]] == ["app/other.py"] and "run(d)" in by_kind["caller"][0].text
    assert [t.path for t in by_kind["test"]] == ["tests/test_rules.py"]
    assert "that no test file imports or references: other" in by_kind["note"][0].text  # run is tested, other is not


def test_priorities_declarations_first_and_budget_drops_the_rest_not_the_note(repo):
    pack = retrieval.build_pack(["app/rules.py"], root=repo, budget=330)
    assert pack.items[0].kind == "declaration" and pack.omitted > 0
    assert any(i.kind == "note" for i in pack.items)
    assert pack.chars - sum(len(i.text) for i in pack.items if i.kind == "note") <= 330


def test_reviewing_a_file_never_includes_itself_as_context(repo):
    pack = retrieval.build_pack(["app/rules.py", "app/models.py"], root=repo)
    assert all(not (i.kind == "declaration" and i.path == "app/models.py") for i in pack.items)


def test_unparseable_file_is_reported_not_fatal(repo):
    pack = retrieval.build_pack(["app/broken.py", "app/util.py"], root=repo)
    assert any("app/broken.py" in n and "does not parse" in n for n in pack.notes)
    assert any(i.kind == "caller" for i in pack.items)  # the other file still got its context


def test_reviewing_a_test_file_gets_the_code_under_test_but_no_test_listing(repo):
    pack = retrieval.build_pack(["tests/test_rules.py"], root=repo)
    assert ("callee", "app/rules.py") in kinds(pack)
    assert not any(i.kind in ("test", "note") for i in pack.items)


def test_diff_restricts_context_to_the_changed_functions(repo):
    diff = ("--- a/app/rules.py\n+++ b/app/rules.py\n@@ -5,2 +5,3 @@\n def run(doc: Doc):\n"
            "+    x = 1\n     return util.same(doc.payee, 'x')\n")
    changed = retrieval.changed_lines(diff)
    assert changed == {"app/rules.py": {5, 6, 7}}
    pack = retrieval.build_pack(["app/rules.py"], root=repo, changed=changed)
    callee_text = " ".join(i.text for i in pack.items if i.kind == "callee")
    assert "def same" in callee_text and "def unused" not in callee_text   # `other` did not change


def test_changed_lines_handles_multiple_files_and_single_line_hunks():
    diff = "+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n+++ b/b.py\n@@ -10,0 +11,2 @@\n+p\n+q\n"
    assert retrieval.changed_lines(diff) == {"a.py": {1}, "b.py": {11, 12}}


# ---- on the real repo -------------------------------------------------------------------------------------

def test_real_repo_pack_shows_the_schema_defaults_the_reviewer_got_wrong():
    pack = retrieval.build_pack(["loan_agent/rules/line_rules.py"])
    text = pack.render()
    assert 'payee_name: str = ""' in text and "wind_excluded: bool = False" in text
    assert "def safe_compare" in text and "tests/test_line_rules.py" in text
    assert pack.chars < retrieval.DEFAULT_BUDGET + 2000


def test_real_repo_pack_never_contains_the_answer_key():
    for f in ("loan_agent/rules/line_rules.py", "loan_agent/tools/utils.py", "tests/test_line_rules.py"):
        for item in retrieval.build_pack([f]).items:
            assert not item.path.startswith(("eval/", "docs/"))


def test_real_repo_caller_snippets_do_not_overlap():
    items = [i for i in retrieval.build_pack(["loan_agent/tools/utils.py"]).items if i.kind == "caller"]
    for n, a in enumerate(items):
        for b in items[n + 1:]:
            assert a.path != b.path or a.end < b.start or b.end < a.start


# ---- wiring ---------------------------------------------------------------------------------------------

class Capture:
    name = "capture"

    def __init__(self):
        self.users = []

    def complete(self, system, user, model):
        self.users.append(user)
        return Completion(json.dumps({"findings": []}))


def test_prompt_wraps_context_as_read_only_background():
    user = prompt.user_prompt([], context="<context kind=\"declaration\">x</context>")
    assert "<related_code>" in user and "read-only background" in user and "Do not report" in user
    assert "<related_code>" not in prompt.user_prompt([])


def test_pipeline_sends_context_to_every_pass_and_can_turn_it_off():
    cap = Capture()
    res = pipeline.review(["loan_agent/rules/line_rules.py"], cap, passes=passes.select("all"),
                          opts=pipeline.Options(parallel=False))
    assert len(cap.users) == 3 and all("<related_code>" in u and 'payee_name: str = ""' in u for u in cap.users)
    assert res.context.items
    cap = Capture()
    res = pipeline.review(["loan_agent/rules/line_rules.py"], cap, opts=pipeline.Options(context_chars=0))
    assert "<related_code>" not in cap.users[0] and not res.context.items


def test_context_failure_does_not_stop_the_review(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("index exploded")
    monkeypatch.setattr(retrieval, "build_pack", boom)
    cap = Capture()
    res = pipeline.review(["loan_agent/tools/utils.py"], cap)
    assert len(cap.users) == 1 and "<related_code>" not in cap.users[0]
    assert any("context pack failed" in n for n in res.context.notes)


def test_report_mentions_the_context_that_was_given():
    from review import render
    res = pipeline.review(["loan_agent/rules/line_rules.py"], Capture())
    md = render.markdown(res, None, "fake")
    assert "Context: " in md and "declaration" in md and "callee" in md


def test_eval_payload_files_get_context_but_never_from_the_answer_key():
    res = pipeline.review(["loan_agent/rules/line_rules.py"], Capture(),
                          opts=pipeline.Options(allow_answer_key=False))
    assert all(not i.path.startswith(("eval/", "docs/")) for i in res.context.items)
