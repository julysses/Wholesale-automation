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
- [ ] Protect operational API routes with verified sign-in and approved profile checks; preserve public forms and signed webhooks.
- [ ] Send session tokens on frontend API requests.
- [ ] Make public form routes independent of dashboard authentication/bootstrap.
- [x] Validate submissions and acknowledge only durable saves (10 regression tests pass).
- [ ] Verify approval routing, auth bootstrap cleanup, and session data isolation.
- [ ] Review frontend workflow errors and improve release checks.
- [ ] Run backend, frontend and browser regression checks.
- [ ] Update release documentation, commit, push, and create a reviewable PR.

## Release gates
- [x] Resume existing Supabase project with user approval.
- [ ] Correct and verify database access policies after restoration.
- No live SMS, email, calls, or ad publishing during verification.
- Report remaining limitations explicitly; do not describe an inactive deployment as production-ready.
