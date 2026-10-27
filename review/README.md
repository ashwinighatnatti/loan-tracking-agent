# review/: the code review agent

Reads code, applies the rubric in `../REVIEW.md`, and reports findings that are grounded in the actual file text. Measured by `../eval/`.

## Use it

```
python -m review files loan_agent/rules/line_rules.py loan_agent/tools/utils.py
python -m review diff --base main --out review.md --json review.json     # files changed vs main
python -m review diff --staged                                            # before committing
```

Exit code: `0` no findings, `1` findings, `2` nothing was reviewed (backend down, unparseable replies, no readable files). CI must treat `2` as a failure, never as a pass.

Backends (`--backend` or `REVIEW_BACKEND` fixes the reviewer; otherwise it is chosen by model inversion below; `--model` or `REVIEW_MODEL`):

| Backend | Needs | Notes |
|---|---|---|
| `claude-cli` (default family in `review.toml`) | the `claude` CLI, logged in | runs `claude -p` with **all tools off**, from an empty directory, so no project memory or subagents leak in |
| `anthropic` | `pip install anthropic`, `ANTHROPIC_API_KEY` | token counts only, cost is not computed |
| `command:<shell command>` | any program | receives `{"system","user","model"}` JSON on stdin; prints the reply text, or `{"text", "cost_usd"}`. This is how a second model family is plugged in |

Measure a reviewer version with the harness:

```
python eval/run_review.py --reviewer "python -m review --protocol" --runs 3 --write-baseline eval/baselines/claude-cli.json
```

## How a review runs

1. **Scope.** The files are read by this tool, numbered, split into 700-line chunks (40 lines overlap) and batched up to 90k characters per call. If any file is loan logic, `processing-rules.md` is included as the intended behavior.
2. **Prompt.** The system text is lifted from REVIEW.md sections 2 to 5 (invariants, bug catalog, nitpick rules, finding format), so editing REVIEW.md changes the reviewer. Code is wrapped as data with an explicit instruction not to follow text found inside it.
3. **No tools.** The model sees only what is in the prompt. It cannot browse the repo, so it cannot read `docs/code-review-findings.md`. Files that hold the eval answers (`docs/code-review-findings.md`, `eval/cases/`) are refused unless `--allow-answer-key` is given, and never in `--protocol` mode.
4. **Parse.** Replies may be fenced or wrapped in prose. An unparseable reply is retried once, then recorded as an error. Errors are reported, never counted as "no findings".
5. **Ground.** Every finding must quote code that exists in that file (whitespace-insensitive). The reported line is snapped to where the quote really is. A finding with no matching quote is dropped as a probable hallucination.
6. **Filter.** Dropped: files outside scope, severity below `--min-severity` (default medium), no concrete failure scenario, nitpick titles (REVIEW.md section 4), confidence below `--min-confidence` (default 0.5). Near-duplicates collapse to the stronger one.
7. **Report.** Ranked by severity then confidence. If a reviewed file is in the REVIEW.md section 1 blast radius, the report says a human must review. The tool advises; it never approves. A clean result says "no findings in the scope reviewed", never "no bugs".

`--json` also writes the dropped candidates with the reason for each, which is what to read when tuning the filters.

## Several focused passes (Phase 4)

By default a review runs three passes in parallel, each a separate model call with the same rubric plus a focus and an instruction to assume the code is wrong and try to demonstrate it (`review/passes.py`):

| Pass | Looks hardest for |
|---|---|
| `correctness` | money, dates and terms, unhandled branches, wrong-loan linking, vocabulary mapping, silent defaults (BT-01 to BT-04, BT-06 to BT-08) |
| `safety` | no get-out path, LLM trust boundary, writes without a human gate, network exposure, run tracking, PII (BT-05, BT-09, BT-11, BT-12) |
| `robustness` | selectors, read/write asymmetry, broken modules, environment, tests that lock in bugs (BT-10, BT-13 to BT-15) |

`--passes general` runs the single broad pass of Phase 3 (the ablation); `--passes correctness,safety` picks some. Each pass is grounded and filtered on its own; then findings that describe the same defect (same file, lines within 3, same category or similar title) collapse into one that records which passes found it and gains 0.1 confidence per extra pass. The report shows `found by 2: correctness, safety`. A pass that fails is reported as an error naming the pass; the other passes still count. Cost is roughly three times a single pass (about $0.19 for one 112-line file).

## Model inversion (Phase 4)

A model reviewing its own family's code fails in the same ways it wrote them. `review.toml` lists reviewer families in order (the first is the default). For `files` and `diff` reviews the author family is read from commit trailers (`Co-Authored-By: Claude`, "Generated with Claude Code", Codex/OpenAI/Gemini equivalents) and branch prefixes (`codex/`, `claude/`) in `<base>..HEAD`, or declared with `--author claude|gpt|gemini|human`. The reviewer is the first configured family that is not an author family. The report always states what happened:

- `Inverted: author claude (...) reviewed by gpt.`
- `Model inversion not applied: author model unknown (no fingerprint found).` (the review uses the default family)
- `Model inversion NOT applied: author claude (...) but no other reviewer family is configured` (**the current state of this repo**: only `claude` is configured)

`--backend` fixes the reviewer and turns inversion off. To enable it for Claude-written code, add a second family to `review.toml`. `review/adapters/openai_chat.py` is a ready `command:` backend for OpenAI-compatible APIs (`OPENAI_API_KEY`, `OPENAI_REVIEW_MODEL`; it does not guess a model name, and reports tokens, not dollars). Detection is partial (the research cites about 80% for fingerprints), so unknown authors are common; it is a bias reducer, not a guarantee.

**Neither feature has been measured on `eval/` yet.** Measure before trusting either (they cost about 3x per run):

```
python eval/run_review.py --reviewer "python -m review --protocol --passes general" --runs 3 --write-baseline eval/baselines/general.json
python eval/run_review.py --reviewer "python -m review --protocol"                  --runs 3 --check eval/baselines/general.json
python eval/run_review.py --reviewer "python -m review --protocol --author claude"  --runs 3   # needs a second family configured
```

## Context pack (Phase 5)

Before the model is called, `review/retrieval.py` indexes the repo's Python with `ast` (no embeddings, no model) and gathers the code around each reviewed file, in this priority order, under a character budget (`--context-chars`, default 40,000; `0` turns it off):

| Kind | What | Why |
|---|---|---|
| `declaration` | classes the file uses, with one level of base classes | field types and defaults: a field typed `str = ""` is never None, so "could be None" claims can be checked |
| `callee` | functions the file calls that live in other files | contracts, sentinels, what they raise |
| `caller` | where other (non-test) code calls what the file defines | how inputs actually arrive |
| `test` | up to two test files using the file's symbols | what is asserted, and what locks in a bug |
| `note` | public symbols no test file imports or references | a coverage fact for BT-15 |

In `diff` mode only the functions overlapping the changed lines drive the search. The pack is shown to every pass as `<related_code>`, marked read-only: findings must be located in the reviewed files, and the model may cite the context in its failure scenario. The report prints a one-line summary of what was given (`Context: 9 declaration, 6 callee, 2 test, 1 note (26,732 chars)`), and `--json` lists every item and why it was included.

Limits, by design: resolution is by import, not by type inference, so method calls on objects (`obj.method()`) and dynamic dispatch are not followed. A file that does not parse (`lib/acting/general_acting_agent.py` today) gets a note instead of context. `eval/`, `docs/code-review-findings.md` and non-Python files are never indexed, so the pack cannot leak the eval answers. Preview a pack without calling a model: `python -m review context <file> [--full]`. Summarize a `--json` run: `python -m review summarize out.json`.

**Measured on `eval/` (2026-10-27, 3 runs each, 36 cases, 0 reviewer errors).** One broad pass with no context: recall 0.657, labelled precision 0.593, about $1.01 cold per run. Three passes plus context (the default): recall 0.787, Critical+High recall 0.841, labelled precision 0.462, about $3.48 cold per run; 0 false positives and 0 nitpicks in both. The two changes were measured together, so the gain is not attributed to passes or to context separately, and the extra unlabelled findings have not been triaged.

## Boundary with eval/

`review/` is the product: code in, findings out. `eval/` is the instrument that measures it. Rules, enforced by `tests/test_boundary.py`:

- `review/` never imports anything from `eval/`, and holds no case ids or case files.
- `eval/` never imports `review`; it only runs the reviewer as a command (`python -m review --protocol`) and reads its JSON.
- `REVIEW.md` at the repo root is the one shared contract: this package reads it for the rubric, `eval/` for the catalog ids.
- The single sanctioned coupling is a list of paths the reviewer refuses to read or index (`ANSWER_KEY` in `context.py`, `SKIP_DIRS` in `retrieval.py`), so it cannot see the eval answers.

## Not built yet

- Posting comments to a pull request, and acceptance tracking (Phase 6). There is no remote yet.
- Running the model reviewer in CI. It needs credentials; only the harness self-checks run there.
