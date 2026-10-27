# Loan processing Agent

Process documents in Application.


# Code Layout

loan-agent/
    + docs
    + deployment            (contains deployment related scripts)
    + eval                  (contains evals for the loan_agent)
    + loan_agent            (contains main agent code that orchestrates the workflow)
        + core              (core)
        + lib               (libraries)
            + acting        (acting agent)
            + investigation (investigating agent)
        + mocks             (mock pages for app)
            + api           (mock api for loan)
                + data      (data files for mock api)
        + screens           (screen handling code including scraping, read write operations)
        + loan_schema       (contains schema for loan document) 
        + rules             (contains rules for processing a document into a loan)
        + workflow          (contains workflow with detailed steps represented in pseudo code)
        + tools             (tools for the LLM)
    + tests                 (contains tests )
README.md                   (this file)


# Review and CI

- `REVIEW.md` defines what a good change is: blast-radius paths that need a human, invariants, the bug-type catalog, and what counts as a nitpick.
- `review/` is the code review agent: `python -m review diff --base main` (`review/README.md`).
- `eval/` replays code reviewers against known defects (`eval/README.md`).
- `.github/workflows/ci.yml` runs `pytest` and the review-eval self-check. Python 3.14+ is required (`pyproject.toml`).
- `tests/conftest.py` lists known failing tests as strict `xfail` with the finding that explains each.


# TODO

1. Design a structure to perform actions on screen
2. Get vLLM + Gemma endpoint on JarvisLabs?
    - invoke model with tool calling
    - call tools
    -     
3. PDF Data extraction by Document TYpe
    - determine document type
    - quantize information needed based on the document type
    - extract precise information into fields
    - build adaptive questions as prompt 
    - ensure no hallucination
4. Finalize the Processsing steps/stages
5. Build 'GetOut' script (basically do nothing and give it to a human)
6. Design Tracking schema (no agent run shoud be missed)
7. Design list of tools that can be called from the model.
8. Acting Agent -> Investigation Agent (what will the investigation agent investigate)
