## What and why
<!-- One paragraph. Link the spec, ticket, or processing-rules section this implements. -->
Spec / rule: 

## Author
- [ ] Human
- [ ] Coding agent (name and model): 
<!-- The reviewer should come from a different model family than the author. -->

## Blast radius (see REVIEW.md section 1)
- [ ] Touches money, escrow, payment preparation or term/date logic
- [ ] Touches document-to-loan matching (names, addresses)
- [ ] Touches anything that writes to the loan screen
- [ ] Touches prompts, tools or agent wiring
- [ ] Touches the schema or the mock/fixture data
- [ ] None of the above

If any box above is ticked, a human must review and approve this PR.

## Verification
- [ ] Added or updated a test that fails without this change
- [ ] `pytest` passes
- [ ] No new hard-coded dates, magic ids, or silent defaults for missing data
- [ ] No real borrower data in fixtures, logs or output
