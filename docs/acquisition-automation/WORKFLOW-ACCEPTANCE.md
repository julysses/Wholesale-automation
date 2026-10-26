# Local acquisition workflow acceptance

Run using an environment with the backend requirements installed:

```sh
python scripts/run_offline_tests.py --acquisition-workflow
```

Set `PG_BIN` when local PostgreSQL binaries are not at the harness default. CI uses PostgreSQL 16; the local run used PostgreSQL 17. The offline runner forwards only that binary-directory setting, clears inherited secrets/dotenv, and retains the Python network-denial hook. The harness creates its own disposable Unix-socket-only cluster, applies the focused schema/migration fixtures and stops/removes that cluster in `finally`. No TCP listener, cron, pg_net, provider or production database is used.

## Evidence provided

`test_acquisition_workflow.py` runs the real acquisition API router, real request schemas, user-scoped store, dedicated worker, Decimal engine, migration RPCs, constraints, RLS and audit triggers. A strict `httpx.MockTransport` adapter replaces PostgREST transport and supplies synthetic Meta lead/error responses for the Facebook journeys. It maps synthetic tokens to isolated database roles/session claims, validates route/argument allowlists, and executes the actual SQL with those identities. Calculator outputs are not mocked.

Three underwriting/offer journeys pass:

1. Sourced inputs calculate a $188,900 MAO and $78,900 modeled profit, persist the immutable result, reject a proposal above the ceiling, create an authorized internal amount approval and expose current review state while denying transmission. Repeated saves/proposals retain one record and one calculation audit event; existing lead MAO stays untouched. Another workspace cannot read the review.
2. Missing downside ARV stays missing, creates an incomplete saved result and prevents proposal creation even though the base case is complete.
3. A worker completion commits successfully but its response is lost. The API's fresh user-authorized read confirms the final status, so its calculation response reports `RECONCILED_FROM_SAVED_SCENARIO`. Retrying keeps one revision and does not run completion again.

The lost-response journey exposed a response-consistency bug: the API previously returned a pending worker summary alongside a confirmed calculated record. It now reports the committed status after the authorized read. An actually unconfirmed outcome still remains pending and retains the same-reference retry requirement.

## Signed Facebook ingestion through real persistence

Five additional journeys run the actual new webhook router, HMAC verification, durable inbox client, retrieval worker, intake preparer, SQL claims/completion, constraints, audit and RLS. The transport adapter allowlists each RPC and argument type; each is executed in the real disposable database with explicit service/user roles. It also supplies bounded synthetic Graph responses and rejects unexpected hosts/operations. No receipt, completed job, canonical lead or intake database result is fabricated.

1. A signed two-event delivery creates durable receipts without CRM leads. Two worker invocations create two incomplete intakes, despite sharing the same phone with each other and an existing lead. Evidence preserves a declined checkbox; sending flags remain disabled. Another workspace cannot read the intakes. Replayed delivery creates no new intake/audit and the worker remains idle. Legacy pending-job sentinel stays unchanged.
2. Receipt acceptance commits but the HTTP response is lost; delivery returns 503 and its retry reconciles the existing receipt. Completion then commits with another lost response; the worker's exact snapshot/token retry returns the same intake, with one provider fetch and one creation audit.
3. An expired-credential response parks the real job with CREDENTIALS_INVALID and an audit, without writing a CRM lead/intake. The next worker call is idle. The authenticated workspace health endpoint then exposes the safe reason and credential-remediation guidance to the owner, while denying another workspace. The owner then submits a documented recovery review through the real API; replaying that approval does not reset twice. After the synthetic credential fix, the worker creates one intake and retains one recovery/audit. This proves the API recovery path; the UI recovery form and background notification delivery remain separate work.
4. Signature tampering creates no receipt. A subsequent valid delivery whose fetched form differs from the receipt parks with IDENTITY_CONFLICT and creates no lead.
5. The integration is disabled during synthetic provider retrieval. Atomic completion fails without creating a lead/intake; a subsequent worker invocation cannot claim or contact the provider. The prior lease remains recoverable subject to a reviewed integration recovery.

The existing dedicated CI job invokes the same eight-journey runner. No CI configuration change is necessary for additional methods defined on WorkflowTests.

## Boundaries and remaining acceptance

This is not a live PostgREST/JWT-signature test. It does not exercise the whole application authentication middleware, actual HTTP provider transport, browser-to-database flow, full production schema, frontend input serialization or all four strategies end to end. Those layers have separate focused tests and still require integrated acceptance. The engine's broader arithmetic suite covers additional strategies, but that must not be confused with full persisted-path coverage for each strategy.

CI retains ordinary repository pytest coverage, including county Python tests, while excluding only the two standalone acquisition database runner files from ordinary collection. Those run in dedicated cluster-owning jobs. Root collection had attempted to collect their inherited tests without the setup runner; explicit separation fixes orchestration without dropping ordinary tests. The standalone workflow job installs backend requirements and invokes the same offline command. Local success is not a claim that remote CI has completed or that production activation is approved.
