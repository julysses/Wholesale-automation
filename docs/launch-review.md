# Wholesale Automation launch review

Review date: September 8, 2026 (America/Chicago). Base: `4ae6ee3` on
`claude/ai-wholesaling-agency-KkDF1`. Fix branch: `codex/launch-readiness-audit`.

Review package: [draft pull request #7](https://github.com/julysses/Wholesale-automation/pull/7).
Preview: [audit branch](https://wholesale-automation-git-codex-launch-13c233-julysses-projects.vercel.app).

**Release decision: ready for staging acceptance, not cleared for production launch.**
The review found and repaired material workflow failures. Passing automated tests
does not establish that live credentials, external delivery, approved-user database
access or production migrations work. The remaining release gates below require
evidence before the launch decision can change.

## Findings and repairs

| Area | Confirmed problem | Repair in this branch |
| --- | --- | --- |
| Buyer CRUD | Form-only ZIP field reached database payloads; modal state could show another buyer's values. | Persist only schema fields, initialize the selected record, preserve failed-save drafts, surface query errors. |
| Tasks | Stale edit state, duplicated/misclassified due dates, inability to clear a due date. | Mount fresh edit forms, use local calendar boundaries, persist explicit null clearing and completion dates. |
| Pipeline | New deals lacked a required lead ID; drag/drop did not handle card targets or failed writes reliably. | Search/select the source lead, resolve drop targets, restore failed moves, update close dates consistently. |
| Lead lists and totals | Client filters applied after pagination; motivation filtering did nothing; several totals stopped at the API row limit. | Filter before pagination, reset page, use exact count queries and paginated narrow projections with stable order. |
| Qualification decisions | An old HOT/WARM result could supersede a newer COLD result; related call transcripts could mismatch. | Choose latest qualification first, then classify; batch related lookups and match transcript by call ID. |
| Imports | Master imports missed existing records beyond the response cap and conflated same-address properties in different cities. | Page existing records, use location-aware keys, batch new inserts, skip unchanged writes, propagate failures. |
| Scoring and CSV UI | Cancelled/failed scoring appeared completed; partial imports could be presented as success. | Distinguish completed/stopped/paused states and report imported, skipped and failed records accurately. |
| Outreach | Buyer SMS called its adapter with an invalid signature; selected WARM leads came from the wrong data source; email edits were ignored. | Use correct adapter contracts and Supabase leads, honor custom text/subject, enforce consent/suppression checks and bounded sends. |
| Outreach results | Queued/accepted requests appeared fully sent, and failures could discard already confirmed results. | Report sent, failed, skipped, dry-run, unresolved and logging failures; stop after uncertain requests without automatic resend. |
| Buyer deal matching | The selected deal never reached the message composer; late match responses could restore stale recipients. | Carry actual property/price context, reset drafts on selection changes, cancel and ignore stale responses. |
| Intake qualification | Public/Facebook forms invoked nonexistent agent methods and silently failed processing. | Use deterministic answer scoring; propagate Facebook fetch/save failures and deduplicate repeated Facebook deliveries. |
| Webhook authentication | Retell signature format did not match its documented provider format; configuration fallback/alias behavior was inconsistent. | Verify timestamp plus body using designated key and a bounded age; fix Facebook aliases and fail-closed missing secrets. |
| Retell completion | Ended/analyzed callbacks and retries could repeat qualification and follow-up actions. | Archive provider events and claim one durable completion attempt per call, await nested actions and park partial failures. |
| HOT/WARM follow-up | Invalid contact constructor arguments prevented enrollment; false provider results were ignored. | Correct the contact contract, surface configured action failures and preserve partial successes for recovery. |
| Call outcomes | Completion needed to preserve later analyzed details and support legitimate calls without speech. | Persist final recording/disposition fields, preserve explicit appointments and record non-conversation attempts once. |
| Settings | Saved true/number values could not override nonempty defaults consistently. | Parse allowed settings by type, distinguish explicit environment values from defaults. |
| Migration startup | HTTP Supabase URLs were treated as database URLs and migration errors allowed startup to continue. | Require PostgreSQL connection URL, load repository environment and stop startup on failure. |
| Calendar | Stub adapters reported external synchronization as successful. | Keep saved appointment and report external synchronization as unavailable. |
| Development workspace | Invalid edits were clamped/saved; browser storage failures could block cloud saves. | Keep invalid edits visible with errors, retain last valid persisted copy, isolate local storage failures. |
| Dependencies | Installed Vitest version was affected by a reported path traversal vulnerability. | Upgrade to 4.1.11; npm dependency audit reports zero known findings for the resulting lockfile. |
| Startup diagnostics | Serverless import errors exposed full exception tracebacks to unauthenticated visitors. | Keep diagnostics in server logs and return a generic 503 response; regression checks confirm sensitive text is absent. |
| Public database access | Live anonymous INSERT policies bypass the public form API. | Draft migration removes those two policies and anonymous INSERT grants; **not applied to production**. |

The Retell implementation follows the provider's [webhook security documentation](https://docs.retellai.com/features/secure-webhook).
The dependency upgrade addresses [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9).

## Validation evidence

- Backend: **230 tests passed**. The local Python 3.12 run reports 289 existing
  deprecation warnings (UTC datetime and Starlette/AnyIO APIs); no test failures.
- Frontend: **63 tests across 16 files passed** with `TZ=America/Chicago`.
- TypeScript and Vite production build passed. Bundle warning remains: approximately
  581 KB main JavaScript and 500 KB on-demand spreadsheet parser, before compression.
- `npm run lint:check` passed with no new findings; 157 existing findings remain.
  This is an explicit baseline gate, not a clean full-lint result.
- Frontend dependency audit returned zero known vulnerabilities. Python dependencies
  remain lower-bound requirements without a lockfile; no complete Python advisory
  scan or reproducible dependency snapshot was established by this review.
- GitHub backend/frontend checks (push and PR runs) and the Vercel preview deployment
  **passed for `7acd6fd`**, which contains all reviewed code changes. The PR is
  mergeable and remains a draft. Subsequent report-only commits do not change code.
- Regression coverage includes actual UI form edits, nullable date updates, failed
  mutations, paging below a server cap, incomplete outreach batches, provider signature
  rejection, duplicate completion callbacks, failed claims and startup failures.
  External providers are mocked; no actual outreach was sent during testing.

## Live read-only and browser evidence

- Supabase project `dvzhzlipbwzzcliujzyz` reported `ACTIVE_HEALTHY`.
- Database counts at review: 17,332 leads, zero buyers, zero deals, zero tasks.
  This makes correct paging necessary, and means production buyer/deal/task workflows
  have not been demonstrated by existing rows.
- Public `/api/health` returned 200; unauthenticated scoring status returned 401.
- The production login page rendered. An approved operator login was requested in
  the Chrome **Wholesale QA** tab and has not been supplied for acceptance testing.
- The branch preview initially required Vercel authentication. Authorized temporary
  access through the connected account allowed its login and public form to load.
  Preview health returned 200, protected scoring status returned 401 without an app
  session, and the loaded preview form reported no browser error logs. The preview
  login was left ready for approved-operator acceptance. No form was submitted.
- Public `/form/hilltop-home-co` loaded. Empty required fields displayed validation;
  all four steps were exercised with dummy entries, including a 390-by-844 mobile
  viewport. Final consent/submission was not sent. Observed browser error logs were
  empty. This validates the existing production page, not the unmerged branch.
- Live policies `public_insert_submissions` and `anon_insert_fb_leads` allow anonymous
  insertion. The repair migration is `20260909023229_protect_public_intake.sql`.
- `development_workspaces` exists. No app-settings rows were present at inspection;
  this does not establish whether deployment environment credentials are configured.

## Remaining release gates

1. **Schema rollout:** validate the public-intake migration in staging; reconcile
   deployed schema and migration histories, then apply through the normal release
   process. Confirm anonymous direct writes fail and API submissions still work.
2. **Signed-in acceptance:** use an approved operator account against the preview/staging
   build. Create/edit/reload a disposable lead, buyer, linked deal and task; verify
   filters, pipeline moves, reports, development save/reload and role restrictions.
   Use isolated test records and remove them after verification.
3. **Enabled integrations:** identify the providers intended for launch and verify
   credentials, provider callbacks, test-recipient SMS/email, call qualification,
   opt-out suppression and provider logs. Obtain explicit authorization before
   sending messages or calls, creating paid jobs or changing ad campaigns.
4. **Webhook operations:** measure real processing duration on the chosen host and
   verify recovery for interrupted/failed Retell receipts. Inline execution, parked
   completion claims and nested error handling in other providers remain operational
   limits; no always-running worker or scheduler was confirmed.
5. **Deployment acceptance:** review/merge the branch only after the preceding gates,
   deploy it and repeat health, authentication, form and signed-in smoke tests. The
   production application still runs its existing version during this review.

External calendar sync is unavailable. Keep it out of the launch feature promise
unless a real integration is implemented and verified. Large reporting/history
queries are now correct but still load full matching history; server aggregates or
cursor pagination should be evaluated as volume grows. Existing lint debt and bundle
size are follow-up efficiency work, with no claim of measured production speedup.

## Resume and verification

See `tasks/launch-review.md` for current progress and `docs/deployment-vercel.md`
for actual hosting topology and recovery behavior. Do not use older readiness reports
as evidence that these current gates passed.

```sh
git switch codex/launch-readiness-audit
git pull --ff-only
python -m pytest -q
cd frontend
npm ci
TZ=America/Chicago npm test
npm run build
npm run lint:check
npm audit --audit-level=high
```
