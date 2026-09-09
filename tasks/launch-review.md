# Launch review — September 8, 2026

Base: `4ae6ee3` on `claude/ai-wholesaling-agency-KkDF1`.
Working branch: `codex/launch-readiness-audit`.

## Progress

- [x] Locate repository, clone current default, pull before edits.
- [x] Independently review frontend, backend, security and deployment configuration.
- [x] Open deployed login in Chrome; approved-account acceptance pending.
- [x] Correct buyer/task/pipeline CRUD, dates and drag/drop with regression tests.
- [x] Correct lead pagination, error reporting, imports and scoring completion states.
- [x] Correct backend messaging contracts, import deduplication and form processing.
- [x] Correct provider signatures, configuration precedence and Retell completion handling.
- [x] Correct deployment migration failure handling and calendar capability reporting.
- [x] Correct buyer deal context, stale matches and development draft persistence.
- [x] Draft anonymous-intake policy repair and redact public startup tracebacks.
- [x] Run regressions: backend 230 passed; frontend 63 passed; production build passed.
- [x] Lint gate passed (157 existing findings); frontend dependency audit returned zero findings.
- [x] Perform public-form desktop/mobile browser checks and production read-only checks.
- [x] Push reviewed code fixes through `f90002f` and document precise release gates.
- [x] Publish [draft PR #7](https://github.com/julysses/Wholesale-automation/pull/7).
      Backend/frontend CI and Vercel preview passed for `7acd6fd` (all code fixes).
- [x] Check branch preview: health 200, protected API 401, login/public form load,
      no observed form browser errors. No form submission or signed-in acceptance.

## Next release steps — still open

- [ ] Resolve browser session sharing, then run signed-in CRUD, role and
      development-workspace acceptance on preview/staging. User reports being signed
      in; the connected Chrome preview still displays login. Browser identification
      has been requested. Do not ask for credentials or claim an authenticated pass.
- [ ] Validate/apply `20260909023229_protect_public_intake.sql` through release process.
      Live anonymous insert policies remain unchanged until rollout.
- [ ] Confirm intended launch providers and authorize controlled test-recipient
      delivery/callback tests; no real SMS/email/calls/ads have been sent here.
- [ ] Verify real webhook duration and deliberate recovery for parked partial attempts.
- [ ] Review/merge/deploy and repeat production smoke checks after acceptance gates.

Current release decision: **not cleared for production launch**. See the report
for evidence and operational limits. External calendar synchronization is unavailable.

## Scope and evidence

No real SMS, email, calls or ads are sent by this review. Tests mock external actions.
Production database changes and merging/deployment are separate from the review branch.
Existing readiness notes are context, not evidence that current workflows pass.
Confirmed findings and validation are recorded in `docs/launch-review.md`.

## Acceptance safeguards verified on resumption

- Live lead triggers currently contain only `leads_updated_at`; the repository's
  enrichment-on-insert trigger is not active in the inspected database. Relevant
  enrichment settings are absent. Recheck after any migration rollout.
- 16,952 leads were unscored at inspection. `useResumeAutoScore` starts scoring on
  authenticated layout mount when backlog exists. Do not interpret DNC/paused flags
  as scoring suppression or use repeated reloads as a harmless acceptance action.
- Buyer/task writes have no provider-send triggers in the supplied source. Leave
  disposable buyer contact fields blank; collect UUIDs for exact cleanup. Task/deal
  pages lack delete controls, so arrange exact-ID cleanup before creating fixtures.
- Export the existing development workspace before editing, then restore both its
  cloud data and local draft. Do not overwrite an operator's existing work.
- No acceptance fixtures or provider requests were created by the resumed checks.
