"""Phase 4: focused passes, cross-pass merging, and model inversion."""
import argparse
import io
import json

import pytest

from review import backends, cli, findings, inversion, passes, pipeline, prompt
from review.adapters import openai_chat
from review.backends import Completion

FIXTURE = "eval/fixtures/clean/escrow_fixed.py"


def raw(**kw):
    base = dict(file=FIXTURE, line=1, severity="high", category="BT-01", title="Unknown escrow becomes No",
                quote='return "needs_human"', confidence=0.6,
                failure_scenario="Blank escrow on a loan 90 days from renewal returns no payment and the policy lapses.",
                fix="Route unknown to a person.")
    base.update(kw)
    return base


class ByPass:
    """Replies depend on which pass's focus text is in the system prompt, so thread order is irrelevant."""
    name = "bypass"

    def __init__(self, replies: dict[str, list[dict] | Exception]):
        self.replies, self.systems = replies, []

    def complete(self, system, user, model):
        self.systems.append(system)
        for name, items in self.replies.items():
            if f"# Your focus: {name}" in system:
                if isinstance(items, Exception):
                    raise items
                return Completion(json.dumps({"findings": items}), cost_usd=0.01, input_tokens=5, output_tokens=2)
        return Completion(json.dumps({"findings": []}))


# ---- passes -----------------------------------------------------------------------------------------

def test_default_passes_and_selection():
    assert [p.name for p in passes.select("all")] == ["correctness", "safety", "robustness"]
    assert [p.name for p in passes.select("general")] == ["general"]
    assert [p.name for p in passes.select("safety, general")] == ["safety", "general"]
    with pytest.raises(ValueError):
        passes.select("correctness,bogus")


def test_focused_prompt_adds_focus_and_adversarial_text_but_general_does_not():
    focused = prompt.system_prompt(passes.CORRECTNESS)
    assert "# Your focus: correctness" in focused and "Assume the code under review is wrong" in focused
    assert "BT-01" in passes.CORRECTNESS.focus
    assert "# Your focus" not in prompt.system_prompt(passes.GENERAL)
    assert "# Your focus" not in prompt.system_prompt()


def test_every_catalog_entry_is_owned_by_some_focused_pass():
    from review import rubric
    text = " ".join(p.focus for p in passes.ALL.values())
    assert {i for i in rubric.catalog_ids() if i in text} == rubric.catalog_ids()


# ---- merging ----------------------------------------------------------------------------------------

def test_same_defect_from_two_passes_collapses_and_gains_confidence():
    fake = ByPass({"correctness": [raw()], "safety": [raw(title="Escrow unknown treated as No")], "robustness": []})
    res = pipeline.review([FIXTURE], fake, passes=passes.select("all"), opts=pipeline.Options(parallel=False))
    assert len(res.outcome.findings) == 1
    f = res.outcome.findings[0]
    assert f.found_by == ["correctness", "safety"]
    assert f.confidence == pytest.approx(0.7)
    assert any("duplicate" in d.reason for d in res.outcome.dropped)
    assert res.usage.calls == 3 and res.usage.cost_usd == pytest.approx(0.02 + 0.01)


def test_different_defects_from_different_passes_are_both_kept_and_ranked():
    fake = ByPass({"correctness": [raw(severity="medium", quote="def is_escrow", title="A", category="BT-03")],
                   "safety": [raw(severity="critical", title="B", category="BT-09")]})
    res = pipeline.review([FIXTURE], fake, passes=passes.select("all"))
    assert [f.severity for f in res.outcome.findings] == ["critical", "medium"]
    assert [p.name for p in res.passes] == ["correctness", "safety", "robustness"]


def test_one_failing_pass_does_not_hide_the_others_but_is_reported():
    fake = ByPass({"correctness": [raw()], "safety": backends.BackendError("quota"), "robustness": []})
    res = pipeline.review([FIXTURE], fake, passes=passes.select("all"))
    assert len(res.outcome.findings) == 1
    assert len(res.errors) == 1 and "[safety]" in res.errors[0]
    assert [p.error != "" for p in res.passes] == [False, True, False]


def test_report_shows_agreement_passes_and_inversion_note():
    from review import render
    fake = ByPass({"correctness": [raw()], "safety": [raw()]})
    res = pipeline.review([FIXTURE], fake, passes=passes.select("all"))
    res.inversion_note = "Inverted: author claude reviewed by gpt."
    md = render.markdown(res, None, "fake")
    assert "found by 2: correctness, safety" in md and "Passes: correctness 1 kept" in md
    assert "Model inversion: Inverted: author claude" in md


# ---- author detection ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text, branch, expected", [
    ("fix\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", "", {"claude"}),
    ("Generated with [Claude Code](https://claude.com/claude-code)", "", {"claude"}),
    ("fix\n\nCo-authored-by: Codex <codex@openai.com>", "", {"gpt"}),
    ("", "codex/fix-escrow", {"gpt"}),
    ("", "claude/loan-link", {"claude"}),
    ("Co-Authored-By: Claude <x>\nCo-authored-by: Codex <y>", "", {"claude", "gpt"}),
    ("plain human commit", "feature/escrow", set()),
    ("", "", set()),
])
def test_detect_author(text, branch, expected):
    assert inversion.detect_author(text, branch).families == expected


def test_parse_author_modes():
    d = inversion.detect_author("Co-Authored-By: Claude <x>")
    assert inversion.parse_author("auto", d)[0] == {"claude"}
    assert inversion.parse_author("human", d)[0] == set()
    assert inversion.parse_author("GPT, Claude", d)[0] == {"gpt", "claude"}
    assert inversion.parse_author("auto", inversion.Detection())[1] == "no fingerprint found"


# ---- choosing a reviewer --------------------------------------------------------------------------------

FAMS = {"claude": "claude-cli", "gpt": "command:x"}


def test_inversion_picks_a_different_family():
    c = inversion.choose({"claude"}, FAMS, "trailer")
    assert (c.family, c.backend_spec, c.inverted) == ("gpt", "command:x", True)
    c = inversion.choose({"gpt"}, FAMS)
    assert (c.family, c.inverted) == ("claude", True)


def test_inversion_avoids_every_author_family():
    c = inversion.choose({"claude", "gpt"}, {**FAMS, "gemini": "command:g"})
    assert c.family == "gemini" and c.inverted


def test_unknown_author_uses_default_and_says_inversion_was_not_applied():
    c = inversion.choose(set(), FAMS, "no fingerprint found")
    assert c.family == "claude" and not c.inverted and "not applied" in c.note


def test_single_configured_family_cannot_invert_and_says_so_loudly():
    c = inversion.choose({"claude"}, {"claude": "claude-cli"}, "trailer")
    assert not c.inverted and "NOT applied" in c.note and "Same-family" in c.note


def test_load_families_reads_review_toml_in_order(tmp_path):
    p = tmp_path / "review.toml"
    p.write_text('[families]\nclaude = "claude-cli"\ngpt = "command:x"\n', encoding="utf-8")
    assert list(inversion.load_families(p).items()) == [("claude", "claude-cli"), ("gpt", "command:x")]
    p.write_text("[other]\na = 1\n", encoding="utf-8")
    with pytest.raises(inversion.InversionError):
        inversion.load_families(p)
    assert inversion.load_families(tmp_path / "missing.toml") == {"claude": "claude-cli"}


def test_repo_review_toml_loads_and_defaults_to_claude():
    assert next(iter(inversion.load_families())) == "claude"


def args(**kw):
    base = dict(backend=None, author="auto")
    base.update(kw)
    return argparse.Namespace(**base)


def test_pick_backend_explicit_backend_disables_inversion():
    backend, note = cli.pick_backend(args(backend="command:echo hi", author="claude"), "", "")
    assert isinstance(backend, backends.CommandBackend) and "inversion not applied" in note


def test_pick_backend_inverts_to_command_family_when_configured(monkeypatch):
    monkeypatch.setattr(inversion, "load_families", lambda: {"claude": "claude-cli", "gpt": "command:echo hi"})
    backend, note = cli.pick_backend(args(author="claude"), "", "")
    assert isinstance(backend, backends.CommandBackend) and note.startswith("Inverted")
    backend, note = cli.pick_backend(args(), "Co-Authored-By: Codex <c@openai.com>", "")
    assert isinstance(backend, backends.ClaudeCli) and "reviewed by claude" in note


def test_pick_backend_detects_from_commit_text(monkeypatch):
    monkeypatch.setattr(inversion, "load_families", lambda: {"claude": "claude-cli", "gpt": "command:echo hi"})
    _, note = cli.pick_backend(args(), "Generated with [Claude Code](x)", "")
    assert note.startswith("Inverted") and "commit text" in note


# ---- protocol with passes -------------------------------------------------------------------------------

def test_protocol_runs_the_requested_passes(monkeypatch, capsys):
    fake = ByPass({"correctness": [raw()], "safety": [raw()]})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"files": [FIXTURE]})))
    assert cli.run_protocol(fake, pipeline.Options(), passes.select("all")) == cli.EXIT_CLEAN
    out = json.loads(capsys.readouterr().out)
    assert len(out["findings"]) == 1 and out["findings"][0]["found_by"] == ["correctness", "safety"]
    assert out["usage"]["cost_usd"] == pytest.approx(0.02)  # robustness has no scripted reply, so costs 0


# ---- OpenAI adapter ---------------------------------------------------------------------------------------

def test_adapter_requires_key_and_model(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"system": "s", "user": "u"})))
    assert openai_chat.main() == 2 and "OPENAI_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_REVIEW_MODEL", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"system": "s", "user": "u"})))
    assert openai_chat.main() == 2 and "no model" in capsys.readouterr().err


def test_adapter_round_trip_with_a_stubbed_http_call(monkeypatch, capsys):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["auth"], seen["body"] = req.full_url, req.get_header("Authorization"), json.loads(req.data)

        class R(io.BytesIO):
            __enter__ = lambda self: self
            __exit__ = lambda self, *a: None
        return R(json.dumps({"choices": [{"message": {"content": "{\"findings\": []}"}}],
                             "usage": {"prompt_tokens": 11, "completion_tokens": 3}}).encode())

    monkeypatch.setattr(openai_chat.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "some-model")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"system": "SYS", "user": "USR", "model": None})))
    assert openai_chat.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["text"] == '{"findings": []}' and out["input_tokens"] == 11
    assert seen["url"].endswith("/chat/completions") and seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "some-model" and seen["body"]["messages"][0]["content"] == "SYS"
    # and the command backend can consume it
    comp = backends.Completion(out["text"])
    assert findings.parse_reply(comp.text) == ([], "")
