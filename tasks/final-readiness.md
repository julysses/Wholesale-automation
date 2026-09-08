# Final readiness review — 2026-09-08

Branch: `codex/final-readiness`. Base: `ff676ba`.

## Baseline
- Latest default branch pulled before work.
- Backend: 134 tests pass (Python 3.12); frontend production build passes.
- Lint: 185 errors, 5 warnings; CI currently ignores lint failures.
- Production health responds, but Supabase project `dvzhzlipbwzzcliujzyz` is INACTIVE and its hostname fails DNS.
- Resume explicitly approved by user and completed; auth hostname and SQL now respond.
- Reproduced live `42P17` profile policy recursion using a read-only authenticated-role query.
- Core tables permit pending accounts, and reporting views bypass row policies.

## Work
- [x] Protect operational API routes with verified sign-in and approved profile checks; preserve public forms and signed webhooks.
- [x] Send session tokens on frontend API requests.
- [x] Make public form routes independent of dashboard authentication/bootstrap.
- [x] Validate submissions and acknowledge only durable saves (10 regression tests pass).
- [x] Verify approval routing, auth bootstrap cleanup, and session data isolation.
- [x] Review frontend workflow errors and improve release checks.
- [x] Run backend (162 passing), frontend DOM regression tests (16 passing), production build, lint-regression gate, and dependency audit (zero vulnerabilities).
- [ ] Complete browser visual QA; local browser preview blocked by client.
- [ ] Update release documentation, commit, push, and create a reviewable PR.

## Release gates
- [x] Resume existing Supabase project with user approval.
- [x] Correct and verify database access policies after restoration.
- No live SMS, email, calls, or ad publishing during verification.
- Report remaining limitations explicitly; do not describe an inactive deployment as production-ready.

## Applied changes and verification
- Both frontend coordination and live database repair explicitly approved in chat.
- Migration tested with rollback, applied through Supabase migration API, and verified with authenticated-role claims. Approved profile/lead access succeeds.
- Eight security-definer view errors removed; residual advisor warnings are recorded in `docs/final-readiness-review.md`.
- Frontend dependency audit reports zero vulnerabilities after locked dependency updates and maintained SheetJS installation.
- Lint gate blocks new findings; 181 old errors and 5 warnings remain explicitly tracked.
- Browser client blocked the local visual preview; frontend DOM regression coverage is passing. Visual and real-provider acceptance remain release gates.
