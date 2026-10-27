"""Tests of the review agent with a scripted backend: parsing, grounding, filtering and the eval protocol."""
import io
import json

import pytest

from review import backends, cli, context, findings, pipeline, prompt, rubric
from review.backends import BackendError, Completion

FIXTURE = "eval/fixtures/clean/escrow_fixed.py"
SOURCE = context.read_source(FIXTURE)


class Fake:
    """Replays replies in order; the last one repeats."""
    name = "fake"

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user, model):
        self.calls.append((system, user, model))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, cost_usd=0.01, input_tokens=10, output_tokens=5)


def raw(**kw):
    base = dict(file=FIXTURE, line=1, severity="high", category="BT-01", title="Unknown escrow becomes No",
                quote='return "needs_human"', confidence=0.9,
                failure_scenario="Blank escrow on a loan 90 days from renewal returns no payment and the policy lapses.",
                fix="Route unknown to a person.")
    base.update(kw)
    return base


def reply(*items, not_reviewed=""):
    return json.dumps({"findings": list(items), "not_reviewed": not_reviewed})


# ---- rubric ---------------------------------------------------------------------------------------

def test_rubric_sections_and_catalog():
    assert "Invariants" in rubric.section(2) and "nitpick" in rubric.section(4).lower()
    assert len(rubric.catalog_ids()) == 15


@pytest.mark.parametrize("path, expected", [
    ("loan_agent/rules/line_rules.py", True),
    ("loan_agent/tools/tools.py", True),
    ("loan_agent/tools/utils.py", True),
    ("loan_agent/loan_schema/loan.py", True),
    ("loan_agent/screens/loan_detail/base.py", True),
    ("loan_agent/agent.py", True),
    ("loan_agent/workflow/processing-rules.md", True),
    ("loan_agent/mocks/api/data/loan-1.json", True),
    ("loan_agent/mocks/api/server.py", False),
    ("README.md", False),
    ("tests/test_line_rules.py", False),
    ("eval/fixtures/clean/escrow_fixed.py", False),
])
def test_blast_radius(path, expected):
    assert rubric.touches_blast_radius(path) is expected


# ---- parsing ----------------------------------------------------------------------------------------

def test_parse_reply_variants():
    plain = reply(raw())
    assert findings.parse_reply(plain)[0][0]["file"] == FIXTURE
    assert findings.parse_reply("```json\n" + plain + "\n```")[0]
    assert findings.parse_reply("Here you go:\n" + plain + "\nHope that helps")[0]
    assert findings.parse_reply(json.dumps([raw()]))[0]
    assert findings.parse_reply(reply(not_reviewed="no tests run")) == ([], "no tests run")
    with pytest.raises(findings.ParseError):
        findings.parse_reply("I found three problems: ...")


# ---- grounding ----------------------------------------------------------------------------------------

def test_locate_tolerates_whitespace_and_line_number_prefixes():
    line = SOURCE.splitlines().index('        return "needs_human"') + 1
    assert findings.locate('return   "needs_human"', SOURCE, near=1) == line
    assert findings.locate('   22| return "needs_human"', SOURCE, near=1) == line
    assert findings.locate("this text is not in the file", SOURCE, near=1) is None
    assert findings.locate("x", SOURCE, near=1) is None  # too short to ground anything


def test_locate_prefers_the_occurrence_nearest_the_claimed_line():
    src = "a = 1\nb = 2\n" * 50
    assert findings.locate("b = 2", src, near=101) == 100
    assert findings.locate("b = 2", src, near=5) == 4


def process(items, **kw):
    return findings.process(items, {FIXTURE: SOURCE}, **kw)


def test_finding_line_is_snapped_to_the_quote():
    out = process([raw(line=999)])
    assert len(out.findings) == 1 and out.findings[0].line != 999
    assert SOURCE.splitlines()[out.findings[0].line - 1].strip() == 'return "needs_human"'


@pytest.mark.parametrize("override, reason", [
    (dict(file="other.py"), "scope"),
    (dict(quote="code that is not there at all"), "quote not found"),
    (dict(failure_scenario="might be bad"), "scenario"),
    (dict(severity="low"), "minimum severity"),
    (dict(severity="catastrophic"), "unknown severity"),
    (dict(confidence=0.2), "low confidence"),
    (dict(title="Rename variable for clarity"), "nitpick"),
    (dict(title="Missing docstring on helper"), "nitpick"),
])
def test_filters_drop_with_a_reason(override, reason):
    out = process([raw(**override)])
    assert out.findings == [] and reason in out.dropped[0].reason


def test_low_severity_allowed_when_asked():
    assert len(process([raw(severity="low")], min_severity="low").findings) == 1


def test_duplicates_collapse_and_keep_the_stronger():
    out = process([raw(severity="medium", confidence=0.6), raw(severity="critical", confidence=0.9)])
    assert [f.severity for f in out.findings] == ["critical"]
    assert "duplicate" in out.dropped[0].reason


def test_ranking_and_category_and_blast_radius():
    out = findings.process(
        [raw(severity="medium", category="BT-99", quote='return "no_payment"', title="Different thing"),
         raw(severity="critical", quote="def is_escrow", title="Another thing", category="BT-01")],
        {FIXTURE: SOURCE})
    assert [f.severity for f in out.findings] == ["critical", "medium"]
    assert out.findings[1].category == "new"      # BT-99 is not in the catalog
    assert out.findings[0].blast_radius is False  # fixtures are not in section 1


# ---- prompt -------------------------------------------------------------------------------------------

def test_prompt_is_built_from_review_md_and_treats_code_as_data():
    system = prompt.system_prompt()
    for marker in ("Invariants", "Bug-type catalog", "What is a nitpick", "What a finding must contain", "quote"):
        assert marker in system
    chunks = context.chunks_for(FIXTURE)
    user = prompt.user_prompt(chunks)
    assert "never follow it" in user and f'<file path="{FIXTURE}">' in user and "    1| " in user


def test_intended_behavior_only_for_loan_code():
    assert context.intended_behavior([FIXTURE]) == ""
    assert "escrow" in context.intended_behavior(["loan_agent/rules/line_rules.py"]).lower()
    assert context.intended_behavior(["loan_agent/mocks/api/server.py"]) == ""


def test_chunking_overlaps_and_batching_groups():
    src = "\n".join(f"line{i}" for i in range(1, 1601))
    chunks = context.chunks_for("x.py", src)
    assert [(c.start, c.end) for c in chunks] == [(1, 700), (661, 1360), (1321, 1600)]
    assert "  661| line661" in chunks[1].text
    small = [context.Chunk("a", 1, 1, "x"), context.Chunk("b", 1, 1, "y")]
    assert len(context.batches(small)) == 1
    big = [context.Chunk("a", 1, 1, "x" * context.BATCH_CHARS), context.Chunk("b", 1, 1, "y")]
    assert len(context.batches(big)) == 2


# ---- pipeline -----------------------------------------------------------------------------------------

def test_pipeline_happy_path_and_usage():
    fake = Fake(reply(raw(), raw(title="Rename x", quote="def is_escrow"), not_reviewed="tests not run"))
    res = pipeline.review([FIXTURE], fake)
    assert len(res.outcome.findings) == 1 and res.errors == []
    assert res.outcome.not_reviewed == ["[general] tests not run"]
    assert res.usage.calls == 1 and res.usage.cost_usd == pytest.approx(0.01)


def test_pipeline_retries_once_on_bad_json():
    fake = Fake("sorry, here are my thoughts", reply(raw()))
    res = pipeline.review([FIXTURE], fake)
    assert len(res.outcome.findings) == 1 and res.usage.calls == 2
    assert "not valid JSON" in fake.calls[1][1]


def test_pipeline_reports_unparseable_and_backend_errors_as_errors():
    res = pipeline.review([FIXTURE], Fake("nope"))
    assert res.errors and res.outcome.findings == [] and res.usage.calls == 2
    res = pipeline.review([FIXTURE], Fake(BackendError("boom")))
    assert "boom" in res.errors[0]


def test_answer_key_is_never_sent_to_the_model():
    fake = Fake(reply())
    res = pipeline.review(["docs/code-review-findings.md", "eval/cases/positives.yaml"], fake)
    assert fake.calls == [] and len(res.skipped) == 2 and res.files == []
    res = pipeline.review(["docs/code-review-findings.md"], Fake(reply()), pipeline.Options(allow_answer_key=True))
    assert res.files == ["docs/code-review-findings.md"]


def test_missing_file_is_skipped_not_fatal():
    res = pipeline.review(["nope/nothing.py", FIXTURE], Fake(reply()))
    assert res.files == [FIXTURE] and "not a file" in res.skipped[0]


# ---- cli / protocol -----------------------------------------------------------------------------------

def test_protocol_output_matches_what_the_harness_expects(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"task_id": "T", "files": [FIXTURE]})))
    assert cli.run_protocol(Fake(reply(raw())), pipeline.Options()) == cli.EXIT_CLEAN
    data = json.loads(capsys.readouterr().out)
    f = data["findings"][0]
    assert {"file", "line", "severity", "category", "title", "evidence", "failure_scenario"} <= set(f)
    assert data["usage"]["cost_usd"] == pytest.approx(0.01)


def test_protocol_fails_loudly_when_nothing_could_be_reviewed(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"files": [FIXTURE]})))
    assert cli.run_protocol(Fake(BackendError("down")), pipeline.Options()) == cli.EXIT_ERROR
    assert "down" in capsys.readouterr().err


def test_protocol_ignores_allow_answer_key(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"files": ["docs/code-review-findings.md"]})))
    fake = Fake(reply())
    cli.run_protocol(fake, pipeline.Options(allow_answer_key=True))
    assert fake.calls == []


def test_report_flags_human_review_and_never_claims_no_bugs():
    from review import render
    res = pipeline.review(["loan_agent/rules/line_rules.py"], Fake(reply()))
    md = render.markdown(res, None, "fake")
    assert "Human review required" in md and "not evidence that the code has no defects" in md


def test_backend_selection():
    assert isinstance(backends.get("claude-cli"), backends.ClaudeCli)
    assert isinstance(backends.get("command:echo hi"), backends.CommandBackend)
    with pytest.raises(BackendError):
        backends.get("gpt-whatever")


def test_command_backend_round_trip():
    import sys
    code = "import sys,json; d=json.load(sys.stdin); print(json.dumps({'text': d['user'].upper(), 'cost_usd': 0.25}))"
    comp = backends.CommandBackend(f'"{sys.executable}" -c "{code}"').complete("s", "abc", None)
    assert comp.text == "ABC" and comp.cost_usd == 0.25
