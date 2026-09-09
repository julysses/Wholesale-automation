# Launch review — September 8, 2026

Base: `4ae6ee3` on `claude/ai-wholesaling-agency-KkDF1`.
Working branch: `codex/launch-readiness-audit`.

## Progress

- [x] Locate repository, clone current default, pull before edits.
- [x] Independently review frontend, backend, security and deployment configuration.
- [x] Connect the user's signed-in approved-admin Chrome session.
- [x] Correct buyer/task/pipeline CRUD, dates and drag/drop with regression tests.
- [x] Correct lead pagination, error reporting, imports and scoring completion states.
- [x] Correct backend messaging contracts, import deduplication and form processing.
- [x] Correct provider signatures, configuration precedence and Retell completion handling.
- [x] Correct deployment migration failure handling and calendar capability reporting.
- [x] Correct buyer deal context, stale matches and development draft persistence.
- [x] Draft anonymous-intake policy repair and redact public startup tracebacks.
- [x] Run regressions: backend 230 passed; frontend 88 passed; production build passed.
- [x] Lint gate passed (157 existing findings); frontend dependency audit returned zero findings.
- [x] Perform public-form desktop/mobile browser checks and production read-only checks.
- [x] Push reviewed code fixes through `f90002f` and document precise release gates.
- [x] Publish [draft PR #7](https://github.com/julysses/Wholesale-automation/pull/7).
      Backend/frontend CI and Vercel preview passed for the initial repair set.
- [x] Check branch preview: health 200, protected API 401, login/public form load,
      no observed form browser errors. No public form submission.
- [x] Fix and retest signed-in lead editing, Add Lead reset, Buyer zero values,
      admin navigation and explicit scoring intent on `7d4d5e5`.
- [x] Verify buyer/task/lead/deal workflows, pipeline pointer drag, Reports and
      Development validation/save/local reload. Remove all five fixtures exactly.
- [x] GitHub backend/frontend checks and Vercel preview passed for `7d4d5e5`.

## Next release steps — still open

- [ ] Extended staging acceptance: real lower-role session; Development cloud-only
      cold load and import/export restoration; native task date clearing. The core
      signed-in workflows and new lead/admin/scoring fixes have passed in Chrome.
- [ ] Validate/apply `20260909023229_protect_public_intake.sql` through release process.
      Live anonymous insert policies remain unchanged until rollout.
- [ ] Confirm intended launch providers and authorize controlled test-recipient
      delivery/callback tests; no real SMS/email/calls/ads have been sent here.
- [ ] Verify real webhook duration and deliberate recovery for parked partial attempts.
- [ ] Review/merge/deploy and repeat production smoke checks after acceptance gates.

Current release decision: **not cleared for production launch**. See the report
for evidence and operational limits. External calendar synchronization is unavailable.

## Scope and evidence

No SMS, email, calls or ads were intentionally sent by this review. Tests mock external
actions. The existing app automatically started Claude scoring on authenticated mount
and again on admin-route navigation; it was cancelled when observed. The new fix
requires an explicit scoring action on open/reload. Disposable live CRUD records are
tracked below. Production schema changes and merge/deploy remain separate release steps.
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
- Browser metadata initially showed a stale authorization page title; inspecting the
  claimed Chrome tab revealed the signed-in app. Do not infer login state from titles.

## Signed-in acceptance follow-up

Confirmed new fixes: Lead drawer excludes generated `total_score` and unchanged
automation fields; Add Lead resets on reopen; Buyer zero values survive editing;
page mount only reads scoring progress; admin profile loading waits for auth.
The first Buyer clear attempt used a browser-input method that did not trigger React;
keyboard clearing persisted NULL in the live database. It was not a database defect.

Fixture marker: `CODEX-QA-PR7-20260909`. All contact fields blank. Lead guarded with
DNC, AI calling paused, both sequences false and five non-null score fields.

| Entity | Exact UUID | State |
| --- | --- | --- |
| Buyer | `79f7c18c-730b-495e-b938-65be0e318bf5` | Deleted; create/edit/clear/zero checks passed |
| Task | `13057387-b141-4b17-860d-dc7fda915f6b` | Deleted; create/edit/complete/filter passed |
| Lead | `5073377f-a6a7-4473-a04b-36b87a4814d7` | Deleted; corrected edit saved/reopened with guards intact |
| Deal | `d03056e4-419f-481b-baa0-69f36268c53b` | Deleted; stage edit and pointer drag persisted |
| Development cloud row | `553cab1d-0c43-4c62-bf37-99d48106137b` | Deleted with ID, owner and JSON-hash guard |

Development baseline had zero cloud rows. Finished SF 0 was rejected; restored 2800,
saved the otherwise unchanged default draft, verified cloud persistence and SPA local
reload, then removed only the created cloud row. Original displayed values remain.
This does not prove cloud-only cold loading or import/export round-trip fidelity.
Task due time 2026-09-10 14:30 CDT persisted as 19:30 UTC; completion timestamp verified.
Native date-segment clearing was not conclusively exercised in Chrome; NULL clearing
has automated regression coverage. Related lead/deal/buyer tables had no fixture rows
at the pre-cleanup inspection. All deletions returned the intended UUIDs; final counts
are 17,332 leads and zero buyers/deals/tasks/cloud workspaces, with no QA lead marker.
Old-build automatic scoring reached 516 including the QA fixture; it remained stable
through fixed-build retests. After removing the manually scored fixture, 515 production
leads are scored. Fixed-build reload and admin navigation did not start scoring.
Browser errors observed after the corrected reload: none. Mobile Buyer modal footer
was reachable at 390-by-844; viewport restored. Preview remains available in Chrome.
