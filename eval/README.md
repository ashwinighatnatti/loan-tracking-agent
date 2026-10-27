# eval/: replay harness for code reviewers

Measures how well a code reviewer (a prompt, a model, a Claude Code subagent, a hosted tool) finds the defects that matter in this repo, how much noise it adds, and how stable and costly it is. Every change to a reviewer prompt, model or pipeline is replayed here before it is trusted. The rubric the reviewer is held to is `../REVIEW.md`.

This directory is about reviewing the agent's **code**. Evals of the loan agent's own behavior (extraction accuracy, injection, refusal to guess) are a separate job and do not exist yet.

## Boundary with review/

`eval/` measures the reviewer and must be able to fail it, so the two share no code. `eval/` never imports `review`: it runs the reviewer as a command (`--reviewer "python -m review --protocol"`) and scores the JSON it prints. The reviewer never imports `eval/` and never sees the cases. `../REVIEW.md` is the one shared contract (the reviewer reads the rubric, this directory reads the catalog ids). `tests/test_boundary.py` enforces this. Anything that only serves the reviewer (previewing its context, summarizing its output) lives in `review/`, as `python -m review context` and `python -m review summarize`.

## Run it

```
pip install -e ".[test]"                      # from the repo root
python eval/run_review.py --validate-cases    # cases still match the code
python eval/run_review.py --reviewer oracle   # harness self-check: must score 1.0
python eval/run_review.py --reviewer "python path/to/my_reviewer.py" --runs 3
python eval/run_review.py --reviewer "..." --write-baseline eval/baselines/mine.json
python eval/run_review.py --reviewer "..." --check eval/baselines/mine.json   # exit 1 if worse
pytest eval/tests                             # tests of the harness itself
```

## What is in here

| Path | What |
|---|---|
| `cases/positives.yaml` | 36 real defects: 28 from `docs/code-review-findings.md` and 8 the reviewer found that were then verified by hand (`docs/review-triage-2026-10-27.md`), each pinned to code by an exact `anchor` string |
| `cases/clean.yaml` | 6 negative tasks: 4 fixed versions of known defects, 2 correct-but-ugly "nitpick bait" files |
| `fixtures/clean`, `fixtures/bait` | The negative code. `tests/test_fixtures.py` proves it is correct |
| `harness/` | Case loading and validation, matching and metrics, reviewers |
| `run_review.py` | CLI |
| `baselines/` | Stored metrics. `oracle.json` and `null.json` are the harness bounds; add one per reviewer version |
| `results/` | Full run reports (git-ignored) |

Low-severity findings (F-30 to F-33), the repo-hygiene finding (F-29, fixed by the CI/pyproject work) and the PII-in-fixtures finding (F-25, no single line) are deliberately not cases.

## Task model

A **task** is a scope (one file) the reviewer is asked to review. Positive tasks are generated per file from `positives.yaml`; negative tasks come from `clean.yaml`. A reviewer sees only the file list, the repo path and `REVIEW.md`, never the cases (`test_reviewer_payload_does_not_leak_the_answer_key`).

A finding **matches** a case when it is in the same file, within `tolerance` lines (default 8) of the case's anchor line, and either has the case's catalog `category` or mentions one of its `keywords`. One finding satisfies at most one case. Findings in files outside the task scope are ignored.

## Reviewer protocol

`--reviewer` takes `oracle`, `null`, `noisy`, or any shell command. The command receives JSON on stdin:

```json
{"task_id": "T-loan_agent-rules-line_rules-py", "files": ["loan_agent/rules/line_rules.py"],
 "repo_root": "C:/.../loan-tracking-agent", "rubric": "C:/.../REVIEW.md", "instructions": "..."}
```

and prints JSON on stdout:

```json
{"findings": [{"file": "loan_agent/rules/line_rules.py", "line": 180, "severity": "critical",
               "category": "BT-02", "title": "...", "evidence": "...", "failure_scenario": "...", "fix": "..."}],
 "usage": {"cost_usd": 0.12, "input_tokens": 9000, "output_tokens": 800}}
```

`file` is relative to `repo_root`. A non-zero exit, timeout or invalid JSON counts as a reviewer error, not as zero findings. Wall time is measured by the harness; `cost_usd` is whatever the reviewer reports.

## Metrics

| Metric | Meaning | Direction |
|---|---|---|
| `recall`, `recall_critical_high` | share of open cases found, overall and for Critical+High | up |
| `recall_by_category` | the same per catalog id (BT-01 to BT-15) | up |
| `labelled_precision` | matched / (matched + unlabelled findings in positive tasks). **A lower bound**: the golden set is not exhaustive, so a real bug not in the set counts against it | up |
| `false_positives_on_clean` | non-nitpick findings on code known to be correct | down, target 0 |
| `nitpicks` / `nitpick_rate` | findings that `REVIEW.md` section 4 says not to report (low severity, style categories, naming/docstring/etc. titles) | down |
| `regressions` | a case marked `fixed` reported again | down, target 0 |
| `findings_without_scenario` | findings with no failure scenario (breaks `REVIEW.md` section 5) | down, target 0 |
| `stability` | with `--runs N`, mean overlap of later runs' findings with the first run | up |
| `cost_usd`, `seconds` | per run | down |

`--check` fails when recall drops more than 0.02, Critical+High recall drops at all, labelled precision drops more than 0.05, or any of false positives, nitpicks, regressions, scenario-less findings or reviewer errors rises.

## Keeping the set alive

- **Fix a defect:** change its case to `status: fixed`, add `line: <old line>`, and delete its `KNOWN_FAILURES` entry in `tests/conftest.py` if it has one, in the same change as the fix. `--validate-cases` fails if an open case's anchor vanished or a fixed case's anchor is still there.
- **A reviewer comment was wrong and a human rejected it:** add a clean or bait fixture that reproduces it, and a sentence to `REVIEW.md` section 4.
- **A bug escaped to production or was found late:** add a positive case (the buggy code as it was) and a catalog entry if it is a new type. Cases that cannot be anchored in the current tree need a pinned snapshot under `fixtures/`; this does not exist yet.
- **Edit an anchor** only to follow a refactor, never to make a reviewer pass.

## Limits you should know

- The first 28 positives come from **one audit by one reviewer** (the `code-reviewer` subagent). A reviewer is scored on finding what that audit found, so a genuinely better reviewer can look worse on precision. Treat `recall` as meaningful and `labelled_precision` as a floor.
- The set is small and tied to the current snapshot of a prototype. With 36 cases one miss moves recall by 2.8 points; two runs of the same reviewer differed by 7 points; do not read small differences as signal, and use `--runs 3` or more.
- Reviewers that read the repo can read `docs/code-review-findings.md`, which contains the answers. Run measured reviews on a checkout without that file, or exclude it in the reviewer's file access.
- `oracle` and `null` only prove the harness works. They say nothing about review quality.
- Cases are anchored to the code as it stands, not to a diff. The harness measures "can the reviewer find this defect in this file", which is an audit task. Replaying real historical PRs needs git history, which this repo does not have yet; start collecting it now.
