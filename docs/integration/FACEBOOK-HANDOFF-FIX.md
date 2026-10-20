# Facebook Instant Form repair — local acceptance

October 20, 2026. **The native handoff is repaired on the integration branch and the connected local API/database journeys pass. Production is unchanged and remains paused.** This supersedes the `no_form_receipt` blocker in the initial `FACEBOOK-LAUNCH-READINESS.md` investigation.

## Implementation

| File | Change |
|---|---|
| `tools/facebook_inquiry.py` | Save a stable native submission ID, Meta lead/form identity, original submission time, submitted phone, normalized answers and independent consent evidence. Exact retries reuse the receipt; changed evidence raises a review error. Only ingestion `recorded_at` is excluded from replay comparison. |
| `web/api/webhooks.py` | Persist the native receipt on new and recovered intake paths before owner/task notification handoff. Receipt or owner failure returns a retryable failure, rather than claiming successful intake. |
| `tools/retell_form_sms.py` | Keep the website path and job identity; when no website receipt exists, use exactly one native receipt with a separate job namespace and foreign key. Preserve original due/expiry calculation and use source-specific provider metadata. Invalid/future timestamps fail closed. |
| `tools/sms_client.py` | Native submissions use immutable consent evidence instead of editable alert metadata. A later website refusal still wins. Legacy notification evidence remains available only for historical direct-Twilio consent; it cannot manufacture a native queue receipt. |
| `20261020184154_facebook_inquiry_sms_receipts.sql` | New private-to-browser, RLS-enabled receipt table; server INSERT/SELECT only; immutable update/delete trigger. Jobs require exactly one website or native source. Native FK binds receipt, lead and phone together. Existing transport immutability includes the new source key. |

The migration was generated with the Supabase CLI. It has only been executed in disposable local databases. It neither backfills records nor changes any scheduler, sending flag, existing job status, deadline, receipt or historical migration.

The existing intake claim prevents a previously held/attempted notification from acquiring a new SMS job merely because the webhook is retried after this repair. Regression coverage proves this. The production held conversation is untouched.

## Connected acceptance

`tests/test_local_lead_journeys.py` uses the actual FastAPI submission/webhook handlers and actual PostgreSQL RPC bodies, transactions, claims and constraints. A small PostgREST-shaped test adapter translates client table/RPC operations to SQL. Meta fetching, SendGrid transport, Twilio SDK calls and Retell HTTP calls are mocked; application consent, claim, receipt, routing and dispatch guards are not mocked.

All **10 cases passed**:

- Hilltop seller form, Jays seller form and native Facebook: submit twice → one CRM lead → approved owner and due task → persisted notification/owner email → queue one acknowledgment → refuse dispatch while paused → mocked acknowledgment → signed delivery callback processed while paused → signed seller reply → owned task and email → refuse generation while paused → one Retell generation → one Twilio reply → signed delivery receipt → STOP → START does not clear DNC → later messages/retries cannot send again.
- All three routes without SMS consent: preserve lead, owner task and alert; create no SMS job or provider dispatch.
- All three routes without an approved owner: return a retryable failure and preserve the original receipt; once the fixture owner is restored, retry finishes once without duplicate lead/task/job/email.
- Native database commit with lost response: the retry reuses the committed receipt and creates one queue job without duplicate sending.

An additional **eight-worker real PostgreSQL race passed**: one native receipt, one queue job, one acknowledgment claim and one ledger event. Zero external provider calls occurred.

The fixture uses UTF-8 PostgreSQL and synthetic submission clocks two minutes in the past to exercise the due queue without sleeping or changing real deadlines. Workers are called explicitly against mocks; local scheduler flags stay false, cron/net are table-only stubs, and the stub HTTP-request table stays empty throughout the connected journeys. The temporary cluster is stopped and removed in `finally`.

## Regression evidence

| Suite | Result |
|---|---|
| Full backend | 1,261 passed; six local-only cases skipped in that run because no disposable DB URL was supplied. The subsequently expanded local suite ran all ten separately. |
| Full pipeline/PGlite | 231 passed |
| New native schema permissions/immutability test | Passed; existing website jobs unchanged; mismatched lead/phone and dual-source jobs rejected; browser access denied; service INSERT/SELECT allowed; receipt update/delete blocked |
| Full frontend, bounded to two workers | 240 passed across 51 files |
| Connected API/PostgreSQL journeys | 10 passed |
| Native PostgreSQL contention | Eight workers, one winner at each claim boundary |
| Whitespace checks | Passed |

The initial unrestricted frontend run alongside the large SQL suite had three timing failures. The complete rerun with two workers passed without changing application code, assertions or timeouts. No frontend source changed in this repair; the previously successful TypeScript/Vite build remains applicable. Backend warnings are existing datetime deprecations.

Evidence logs remain locally under ignored `logs/`: `facebook-fix-backend.log`, `facebook-fix-pipeline.log`, `facebook-fix-frontend.log`, `facebook-fix-frontend-bounded.log`, `facebook-fix-sql.log`, `local-lead-journeys.log`. The validation JSON records their hashes. This evidence exercises a selected real intake/transport schema fixture, not a complete production schema export.

Reproduce:

```sh
.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests -q
.venv/bin/python scripts/run_offline_tests.py npm --prefix pipeline test
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test -- --maxWorkers=2
.venv/bin/python scripts/run_offline_tests.py --lead-journeys
```

The runner removes inherited credentials, disables dotenv and uses temporary HOME. Python and Node network guards block providers. The special journey runner permits Node TCP only to its generated localhost test database; the Python SQL adapter likewise refuses any other database host/name. PostgreSQL uses local shared memory, which requires the approved local sandbox exception.

## Review and eventual release

`facebook-handoff-release-manifest.json` lists the one new ad-intake migration separately from the eleven county/offer/lot migrations. It depends on the existing production app-owned transport and intake schema. It does not require activating or releasing county collection.

The repair delta starts at `327179b`. A future ad-only release candidate must isolate that delta against production and repeat its acceptance checks. Do not copy the entire shared `web/api/webhooks.py` or deploy PR #21 wholesale: the integration branch also contains separately prepared collection behavior.

1. Review this patch, migration and evidence. Keep PR #21 draft and production paused.
2. Before any release, verify the exact deployed schema and runtime against the reviewed prerequisites. Rehearse the additive migration on a sanitized production-shaped snapshot; the selected fixture is not a substitute.
3. With separate release authorization, apply only the reviewed native-receipt migration, then the matching runtime in paused mode. Never push the migration directory wholesale or include the historical held-session repair implicitly.
4. With separate bounded live-test authorization, verify the actual Meta form/webhook and website destinations, real owner email/task visibility, carrier delivery and handset receipt, a fresh seller reply, and STOP suppression. Local mock acceptance is not carrier delivery or live go-live certification.
5. Decide paid-ad launch from that evidence. Collection schedules remain a separate decision.

Do not backfill/replay historical held notifications, extend old job windows or clear suppression. A rollback must keep sending paused and retain the new receipt table and evidence; use a forward-compatible runtime repair rather than deleting native history.

The full eleven-migration county integration upgrade/concurrency acceptance remains outstanding. This repair does not certify that broader release. The connected acceptance starts at API requests, with separate React component tests; it is not a real-browser or Meta/carrier production test.

Schema access follows the [Supabase RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security): explicit grants plus RLS, no browser receipt grants, and tested server-only access.
