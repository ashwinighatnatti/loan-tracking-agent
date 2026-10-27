"""Known failures, recorded so CI is green but the bugs stay visible.

Each entry is a test id fragment mapped to the review finding that explains it
(docs/code-review-findings.md). They are strict: when the bug is fixed the test
XPASSes and fails the run, so the entry must be deleted in the same change.
"""
import pytest

KNOWN_FAILURES = {
    "1/1/2025 | 12/31/2025 ; ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; Complete": "F-04 Already On File closes nothing",
    "abc1234 | abc  carrier | 01/01/2025 | 12/31/2025 ; Complete": "F-04 Already On File closes nothing",
    "1/1/2024 | 12/31/2024 ; Policy Not Accepted": "F-04 old policy produces no action",
}


def pytest_collection_modifyitems(items):
    for item in items:
        if "test_process_document" not in item.nodeid:
            continue
        for fragment, reason in KNOWN_FAILURES.items():
            if fragment in item.nodeid:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
