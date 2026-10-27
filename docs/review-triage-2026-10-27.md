# Triage of the reviewer's unlabelled findings (run 3, 2026-10-27)

Reviewer: `python -m review --protocol` on `claude-cli`, Sonnet 5.5, one run, 55 findings, $1.08. Of those, 35 matched no golden case. Each was read and, where its claim was checkable, verified against the code. Findings are numbered in the order `eval/triage.py` prints them (`eval/results/` is git-ignored; rerun to regenerate).

Two runs of the same reviewer on the same 28 cases already differ: recall 0.786 (run 1) vs 0.714 (run 3), and the Critical escrow bug (C-F02) was found in run 1 and missed in run 3. **Single-run differences of a few points are noise.** Use `--runs 3` before judging any change.

## Result

| Verdict | Count | Findings |
|---|---|---|
| Real defect, not in the golden set: added as a case | 8 | #6 #7 #18 #19 #20 #28 #32 #33 |
| Real defect, same root cause as an existing case, but missed by the matcher (distance or wording) or split into several findings | 12 | #3 #5 #9 #10 #12 #13 #16 #17 #22 #23 #24 #25 |
| Real but known and now mitigated | 1 | #11 (needs Python < 3.14; `pyproject.toml` now requires 3.14) |
| Plausible, needs the business rules to decide | 2 | #2 (`additional_amount_due = 0` on a new line), #21 (print and keyword fallback) |
| Over-applied, speculative, minor, or a restatement of a known finding: noise | 9 | #8 #14 #15 #26 #27 #29 #30 #31 #34 (see below) |
| **Wrong, because the claim itself was false** | 2 | #1, #4 |
| **True positive against our own "clean" fixture** | 1 | #35 |

#35 is the only false positive on the clean set, and it was right: `intake_policy("---")` returned `""` instead of `None`, so the bait fixture was not clean. The fixture and its test are fixed.

## Noise, and what it taught us

| # | Claim | Why it is noise | Change made |
|---|---|---|---|
| 1 | `len(doc.payee_name)` raises on None | `payee_name: str = ""` and `from_dict` skips None, so it cannot be None | prompt: find the declaration before claiming None |
| 4 | `wind_excluded` None treated as not excluded | `wind_excluded: bool = False`; the real issue is the default itself (F-08, already a case) | same |
| 14, 27 | `raise RuntimeError` on a page error | infrastructure failure in a screen helper; the gap is a missing run-level handler (F-20) | REVIEW.md invariant 2 narrowed; section 4 nitpick entry |
| 15 | `.get("loan_number", "")` in a grid scrape | speculative; no input shown that triggers it | covered by the same "no unsupported None/missing" rule |
| 26 | OCR loader in the mock server | mock-only quirk | REVIEW.md section 4 |
| 29, 30, 31 | escrow code lookup, `#None` selector, blank page values | true but minor or already covered by F-02 / F-22 / F-23 | none (low value, kept out of the set) |
| 34 | test requires `ValueError` | per the original audit (F-27) the "error" rows exercise the string parser, not `process_document`; not re-verified | none |
| 8 | defaults of 0.0 / "" on optional fields | correct, but a restatement of F-08 (already a case) | none |

## What changed as a result

- `eval/cases/positives.yaml`: 28 -> 36 cases (C-T01 to C-T08). Widened tolerance or keywords for C-F03, C-F09, C-F28 where valid findings missed only on distance or wording.
- `eval/fixtures/bait/validated_upstream.py` and its test: fixed.
- `REVIEW.md` invariant 2 and section 4, and `review/prompt.py`: the three noise patterns above.
- Baselines: `claude-cli-v1.json` (28-case set) removed as no longer comparable; `oracle.json` and `null.json` regenerated.

## Not yet measured

The prompt and rubric changes have **not** been re-run against the model. The next measurement should use `--runs 3` on the 36-case set and be saved as the new baseline.

## Scorer limitations seen here

- Matching is one finding per case. The reviewer reported the F-14 mock-server exposure as three findings (host, CORS, debug); one is credited and two count as unlabelled (#24, #25). That understates precision.
- Findings that are the same root cause in a different file (#13, #17) are real but have no case until someone writes one.
