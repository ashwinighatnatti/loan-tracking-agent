# REVIEW.md: what a good change looks like in this repo

This file is the single source of truth for reviewers, human and automated. Reviewer prompts are built from sections 1 to 5. Do not duplicate them elsewhere. When a reviewer comment is rejected or a bug escapes, update this file and add an eval case (`eval/README.md`).

The agent changes loan records and can cause payments. A wrong write or a missed payment is costly; a stylistic imperfection is not. Review effort follows that.

## 1. Blast radius: a human must approve changes to these

| Path | Why |
|---|---|
| `loan_agent/rules/` | Decides what is written to the loan, which deficiencies are raised, and whether a payment is prepared |
| `loan_agent/tools/tools.py`, `tools/utils.py` | Name, address, term and date logic that links a document to a loan and drives the 60-120 day rule |
| `loan_agent/loan_schema/` | Defaults here decide whether "missing" looks like zero |
| `loan_agent/screens/**` (anything that calls `set_field`, `mark`, save, click) | Writes to the loan system |
| `loan_agent/agent.py`, `prompt.py`, `lib/` | What the LLM may see, decide and call |
| `workflow/processing-rules.md`, `process-as-code.md` | The intended behavior. Code is reviewed against these |
| `mocks/api/data/`, `loan_schema/*.json` | Fixtures. Must stay synthetic |

An AI reviewer advises on these paths and never approves them. Everything else may merge on green CI plus a clean machine review.

## 2. Invariants (a violation is at least High)

1. **Unknown is not zero, not "No", not today.** A missing or unparseable amount, date, escrow flag, name or address is carried as unknown (`None`) and routed to a human. It is never defaulted to `0.0`, `""`, `False` or the current date in a way that changes a decision.
2. **Every run ends in a recorded outcome.** Any input, however malformed, produces either a result or an explicit get-out (Edit / Inquiry / Cannot ID / Manager Review) with a reason. Decision code (`rules/`, `tools/`, `loan_schema/`) does not raise for bad data and does not `print`. Screen and I/O helpers may raise on infrastructure failure (page did not load, timeout, element missing); the defect then is the absence of one run-level handler that records the outcome (report it once, against the run entry point, not once per helper).
3. **No literal values in decision logic.** No hard-coded dates, line ids, loan numbers, names or magic markers (`#06#`, `#08#`) in `rules/` or `tools/`.
4. **A document is linked to a loan only on borrower name AND property address,** per `processing-rules.md`. Ambiguity (several candidates, partial match) goes to a human with the candidates listed.
5. **The LLM proposes, code and humans dispose.** Document text is untrusted data, never instructions. The LLM has no write tool. Payments and low-confidence or unclassified cases need a human gate. Every extracted value keeps its evidence (page and quote).
6. **Code matches `processing-rules.md`.** When code and the rules disagree, that is a finding, whichever is wrong.
7. **Reads and writes are symmetric.** Every field the code can write has a scrape path and a round-trip test.
8. **No real borrower data** in fixtures, logs, test names, commits or run output.
9. **Time is injected.** Anything depending on "today" takes a `processing_date` argument.

## 3. Bug-type catalog

Reviewers look for these first. Each entry has an id, what to look for, and the finding it came from. Add entries from incidents and rejected-then-reversed review comments.

| Id | Bug type | Look for | Seed |
|---|---|---|---|
| BT-01 | Money / escrow comparison | Escrow, premium, coverage, deductible compared as strings or defaulted; payment decided on a value that can be blank | F-02, F-08 |
| BT-02 | Constant in place of data | Literal dates, ids, names, `tmp fix` comments in decision paths | F-01, F-24 |
| BT-03 | Date and term arithmetic | `abs()` on signed differences, sentinels (`-1`), `date.today()`, half-open vs closed terms, leap days, asymmetric comparisons | F-03, F-18, F-19 |
| BT-04 | Unhandled branch / stub | `pass` bodies, uncovered enum or scenario combinations, empty `actions` treated as success, wrong call arity | F-03, F-04, F-05, F-17 |
| BT-05 | Raise instead of get-out | `ValueError` or parse errors on bad input, missing validation at the entry point | F-06, F-22 |
| BT-06 | Wrong-entity link | Fuzzy name or substring address matching, `or` where `and` is required, first-match wins | F-09, F-10, F-16 |
| BT-07 | Vocabulary mapping | Document wording not mapped to the closed set of policy types, string suffix tests that match real policy numbers | F-07, F-17 |
| BT-08 | Silent data loss | Unknown keys only logged, field renames between schema and JSON, numeric defaults on optional data | F-08, F-22 |
| BT-09 | LLM safety | Untrusted text interpolated into prompts, LLM-built arguments for large objects, no confidence or evidence, write tools exposed | F-11, F-12 |
| BT-10 | Selector / screen fragility | Interpolated selectors, suffix matches, fallback sample data read as real, no post-load identity check, no timeouts or retries | F-21, F-23 |
| BT-11 | Network exposure | Debug servers on `0.0.0.0`, wildcard CORS, unauthenticated PII endpoints | F-14, F-25 |
| BT-12 | Run tracking | Execution id created late, outputs written flat or outside a safe root, path components not validated | F-20 |
| BT-13 | Broken or dead module | Does not parse, undefined names, leftovers from other projects | F-13, F-28 |
| BT-14 | Environment / reproducibility | Version-specific APIs undeclared, missing dependency file | F-15 |
| BT-15 | Test blind spot | Tests that lock in a stub as expected behavior, logic only in `__main__` self-tests, tests coupled to fixture values | F-27 |

## 4. What is a nitpick (do not report)

A comment is a nitpick, and must be dropped, if all of these hold: it does not change behavior for any input the system can receive, it is not in the invariants above, and it is about taste. Concretely, do not report:

- naming, typos in comments or identifiers, docstring or comment wording, import order, line length, formatting
- missing type hints or docstrings on private helpers
- "add another layer of defense" or extra validation on a value that is already validated upstream in the same call path
- suggesting a different but equivalent construct (loop vs comprehension, early return vs else)
- speculative performance remarks without a measured hot path
- generic error-handling advice ("wrap in try/except") without a concrete failing input
- TODO comments, unless they hide a missing branch of `processing-rules.md`
- `raise` in a screen or I/O helper for a page, network or timeout failure (see invariant 2)
- quirks of mock servers and fixtures that cannot reach production, except exposure of data (invariant 8, BT-11)
- a value "could be None/unset" when the declaring schema is not in front of you; check the field's type and default first, and if you cannot, put it under not reviewed

A coding agent applies review comments without discrimination. Every nitpick posted becomes defensive code in the repo.

## 5. What a finding must contain

Drop the finding if you cannot fill all of these:

1. `path:line` of the code (not of a symptom)
2. a short quote or description of that code
3. a **concrete failure scenario**: a specific input or state, and the wrong result it produces (for loan code, name the real-world consequence: wrong loan, wrong date written, payment not prepared, document lost)
4. severity and a catalog id (or "new" with a one-line description)
5. a recommended fix, and the test that would have caught it

Severity: **Critical** wrong data written to a loan, security exposure or data loss in a realistic scenario. **High** likely wrong behavior or crash on a plausible input, or an invariant violation. **Medium** a clear future failure or coverage gap. **Low** everything else; do not report Low findings in PR comments.

Say what was not reviewed or not run. A reviewer can show a bug exists but not that none do; never write "no bugs found", write "no findings against sections 2 and 3 in the scope reviewed".

## 6. Review procedure

1. Classify the PR against section 1. Note the author (human or which model).
2. Gather context: the diff, the matching section of `processing-rules.md` / `process-as-code.md`, callers and callees of changed functions, the tests that cover them.
3. Check each invariant in section 2, then the catalog in section 3, against the changed lines and their callers.
4. Run the tests. A failing test that the PR does not explain is a finding.
5. Filter against section 4. Emit findings in the format of section 5, ordered by severity.
6. A PR that touches section 1 gets a human review regardless of the machine verdict.

## 7. Measures

Not lines changed or PRs opened. Track: catch rate on `eval/` cases per reviewer version, share of review comments that were acted on, share judged nitpicks, stability of findings across reruns, cost per review, and the gap between "tests pass" and "a maintainer would merge".
