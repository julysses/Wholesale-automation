# Guided contract date review — implementation handoff

## Verified client boundary (candidate89)

`frontend/src/lib/acquisition/deadline-review.ts` validates exact term/source/date interpretations, scoped current state and read-only action choices. Named-zone round trips require an explicit matching offset, accept both explicitly identified repeated DST occurrences, reject nonexistent local times and nonzero fractional seconds, and never select midnight or replace a signed date.

Recovery is scoped to the current user/workspace and retains the original property/offer/contract/version context and exact request through expiry. Approval and withdrawal retain distinct original review identities and the shared ledger cursor. Only a matching historical receipt, or a definite rejection on the first attempt, can clear a saved request. Corrupt/conflicting storage remains held. Candidate parsing preserves the original withdrawal when the selected evidence changes and rejects mixed scope, source, cursor, term, timestamps and current authority.

`ApiError.rejectedDeadline` is recognized only for the exact POST deadline-reviews route and reviewed401/403/409 marker. GET responses, candidate URLs, other writes, query variants and uncertain503/429 responses cannot clear recovery. Existing execution findings optionally retain exact references covering every calendar-only term with unique IDs; legacy findings omit the field entirely. These are transport/recovery checks, not server authorization.

Validation: full frontend822 tests/91 files passed14.43s; final build/typecheck passed3.28s; no new lint findings against147 existing. Focused initial client/API91 tests passed599ms. Logs:`/tmp/deadline-client-full-tests.log`, `/tmp/deadline-client-final-build.log`, `/tmp/deadline-client-lint.log`. All frontend validation processes are terminal0.

## Required next app work

1. Add a collapsed date-interpretation form within the existing step5 contract review card. Preserve navy/orange styling, shared document/property context, keyboard labels and one primary next action. This client module alone does not add a visible control.
2. Load choices for the selected effective/inspection/closing term and selected document. Display the immutable original calendar date and clause separately from the selected interpretation source. Keep evidence IDs out of the main form.
3. Require explicit local time, named zone and offset, source clause, basis, rationale, personal review acknowledgement and bounded review expiry. Never initialize a guessed time. Build the request with the exact discovered source/policy/cursor, then let the server revalidate all authority.
4. Make original-review withdrawal independent of the selected source and unavailable approval controls. Preserve exact pending review across reload/version changes and hold navigation/sibling mutations until recovery. Extend parent recovery detection to the new deadline key, including corrupt storage and conflicts with other pending operations.
5. Load current exact term reviews for execution findings. Preserve original calendar precision, bind explicit review IDs, cap requested expiry by all interpretation expiries and keep missing/revoked/changed interpretations held. Update `executionTermsHold` with verified source-bound state without making client checks a substitute for SQL enforcement.
6. Verify desktop/mobile guided journeys: unknown/missing source holds; explicit review; changed source; original withdrawal; lost approval and withdrawal responses; reload; exact retry; original-version recovery; cross-operation conflict; current expiry/revocation; bound execution handoff. Inspect screenshots, overflow, keyboard access and errors before usability acceptance.

No live schema, policy, signing, outreach or provider activation is authorized by these local checks. Full PRD scope and sequential channel release gates remain active.

## Guided form checkpoint — candidate90

Visible `DeadlineReviewForm.tsx` and parent `ContractDraft.tsx` recovery/adjacent-action integration now implement steps1–4 above. The form records explicit interpretation or original withdrawal using the exact discovered authority. Parent recovery supports missing selection, newer canonical versions, conflicting operations and unreadable saved requests. All831frontend tests, build and lint passed; desktop/mobile browser approval/withdrawal lost-response recovery passed with exactly two decisions and unchanged original date. Evidence:`evidence/deadline-review-ui-2026-11-01/`. The source-backed execution binding in step5 and complete combined journey remain next; existing date-only client execution hold is intentionally still present until that connection is verified.

## Combined execution handoff — candidate91

ExecutionReviewForm now reads fresh exact term states, displays accompanying interpretations, preserves original calendar fields and attaches their exact review IDs. `resolveExecutionDates` makes temporary comparison copies only and caps review expiry. Missing, revoked, stale, mixed-scope and changed-date authority stays held; pending retries preserve the original IDs/bytes. Refresh clears personal acknowledgement. No server authority is inferred from these client checks.

The combined date interpretation → execution review → executed status browser journey passed on desktop/mobile with lost responses/reload/recovery at all three writes, original date/ID preservation, expiry bounds and later original execution withdrawal. Full834frontend tests, build and lint passed. Evidence:`evidence/execution-date-handoff-ui-2026-11-01/`. The local client steps above are now connected; hosted/provider/legal and remaining full lifecycle/PRD acceptance remain separate and incomplete.
