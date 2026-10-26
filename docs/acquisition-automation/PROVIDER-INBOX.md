# Acquisition provider inbox

Implementation: `20261026153314_acquisition_provider_inbox.sql`. This is an inert database foundation, not a live Facebook integration.

The existing `webhook_jobs` table is reused. Catalog inspection found its UUID primary key, JSONB payload, text status/source, attempts and timestamps, enabled RLS and no browser policies. Source migration 013 has the pending/created index. Existing Retell receipt and monitoring consumers remain separate. The isolated fixture recreates inspected columns/constraints, includes a legacy sentinel, and deliberately gives browser roles an overly permissive legacy policy to test the restrictive acquisition boundary.

## Routing and acceptance

A private integration maps a provider/account uniquely to a workspace. It defaults disabled; enabling requires an approval reference. Browser and service roles cannot edit configuration. Identity cannot be reassigned; disable rather than delete. Configuration changes append audit records. This is privileged release configuration pending its operator workflow, not a per-request caller-supplied workspace.

The service-only `accept_acquisition_event` RPC requires enabled global activation, enabled integration and active workspace, holding locks through commit. The caller must authenticate the provider over the raw request before calling it. This RPC does not verify signatures itself, and is not yet connected to an HTTP handler.

A receipt stores one canonical event payload, original raw request bytes, hashes, event type, external identity, integration/workspace and retention deadline. Raw input is bounded at 1 MiB. Use a minimal per-event payload for deduplication, excluding delivery-envelope timestamps that legitimately change on retries. The raw body retains the first accepted envelope. A retry with identical canonical payload returns the original receipt; conflicting payload for the same identity fails. The unique key and transaction advisory lock protect concurrent retries. No CRM lead or contact permission is inferred.

Acquisition records have source `acquisition_inbox` and status `acquisition_received`, never legacy `pending`. The existing generic drain therefore cannot claim them, even before worker code changes. A future dedicated lease/processor migration must preserve this boundary. These states intentionally do not claim processing or successful CRM ingestion.

## Access, retention and compensation

Raw receipts are server-only. Restrictive RLS excludes them from browser roles even if a permissive legacy policy exists. Application service-role raw writes cannot change/delete receipts, strip workspace scope or reset them into the legacy queue. Public RPC wrappers use invoker rights; privileged functions live in the private schema with explicit grants and empty search paths, following [Supabase function security guidance](https://supabase.com/docs/guides/database/functions).

Integration retention is configurable from 1–90 days, default 30; this engineering default requires review before activation. `purge_acquisition_payloads` performs a bounded, concurrent-safe batch after each stored deadline, removing raw bytes and JSON answers while retaining identity/hashes and an immutable purge audit. A purged receipt becomes `acquisition_expired`; it cannot be revived by a replay. No scheduler is installed. A monitored retention runner is required before accepting live payloads. Receipt metadata retention and legal holds remain policy work.

Compensation: disable the integration and its application receiver/worker. Keep schema/receipts for audit and run approved retention; never drop or replay historical migrations. Global acquisition activation also blocks new acceptance. Purging remains possible while activation is off. No production SQL is authorized by this implementation.

## Remaining delivery work

Dedicated lease/claim/completion and credential/error reconciliation; authenticated provider HTTP ingestion with persistence before acknowledgment; atomic batch handling; account/Page subscription verification; supported Meta fields/permissions/API review; token storage; controlled lead retrieval; canonical identity resolution; seller intake and attribution; monitoring and retention scheduling; full-schema upgrade and real PostgREST acceptance. Existing Facebook inline handler and legacy queue semantics are unchanged. No production release gate is met by the isolated inbox tests alone.

## Recoverable claims and deferral

Migration `20261026153939_acquisition_inbox_leases.sql` adds private processing state keyed by the existing immutable receipt. It initializes state transactionally when a receipt is inserted and covers preexisting acquisition receipts. Legacy receipts receive no processing row. No application role can read or mutate the private table directly.

`claim_acquisition_events` is service-only and takes an exact configured integration, a bounded batch of 1–20, and a 30–300 second lease. It rechecks global activation, enabled integration and active workspace, locks eligible receipts/processing rows with `SKIP LOCKED`, and returns canonical event data plus a new random lease token. It omits the full raw envelope. Concurrent workers cannot claim the same active lease. A lost claim response or worker crash is recoverable after expiry; recovery replaces the token so the former worker cannot settle the event.

`defer_acquisition_event` accepts only allowlisted retry/review outcomes. Timeouts, rate limits, provider unavailability and persistence failures receive exponential server-side backoff. Invalid credentials, permission denial, invalid data, identity conflicts and unsupported events are parked for review. Freeform exception text is rejected to avoid persisting secrets. Five attempts is the current hard limit; both failed fifth attempts and abandoned fifth leases park with `RETRY_EXHAUSTED`. Expired/purged payloads park with `PAYLOAD_EXPIRED` without being returned to a worker. Same-token identical deferral retries return the saved outcome without another audit; changed outcomes or stale/expired tokens fail.

Claiming stops on suspension or disabled activation/integration. Deferral remains available after these switches so in-flight work can record a safe hold. No generic success RPC exists: completion must be an atomic provider-specific transaction that writes canonical intake and verifies the current lease. This prevents a queue marker from being mistaken for successful CRM ingestion. Claims and deferrals append scoped audit records without exposing lease tokens.

Remaining: atomic successful intake completion, explicit reviewed recovery from held jobs, actionable credential alerts/operator queue, actual provider worker wiring, polling schedule and monitored retention. No worker runs merely by applying this migration. Compensation is to disable the integration/worker; leases expire and evidence remains. Do not reset private processing rows manually as an application recovery procedure.

## Default-off Facebook HTTP receiver

`GET/POST /webhooks/facebook/acquisition` is separate from the existing inline `/webhooks/facebook/lead` route. It requires both `ACQUISITION_ENABLED=true` and `FACEBOOK_ACQUISITION_INGESTION_ENABLED=true`, dedicated `ACQUISITION_FACEBOOK_APP_SECRET` and `ACQUISITION_FACEBOOK_VERIFY_TOKEN`, plus `ACQUISITION_INGESTION_SERVICE_KEY` and an HTTPS origin in `SUPABASE_URL`. These are configuration requirements, not authorization to enable them. No fallback to generic service credentials or legacy Facebook ingestion exists.

The GET challenge compares the configured verification token. POST reads at most 1 MiB, verifies the signature over exact bytes, validates the Page envelope and at most 100 native events, and requires Page/lead/form identities. It normalizes IDs and preserves provider attribution fields without guessing ad-set semantics. Non-lead notifications acknowledge without a database operation. Invalid signatures, oversized bodies and malformed envelopes never persist.

Migration `20261026163900_acquisition_facebook_batch_acceptance.sql` accepts the normalized batch in one service-only database transaction, with deterministic event lock order. It reuses existing per-event identity/gates/audits and original raw bytes. An unmapped/disabled account or conflicting event rolls back the entire batch. HTTP acknowledges only after a correctly shaped committed receipt response. Errors/timeouts return a sanitized retryable 503; lost responses reconcile on the next provider retry. No lead retrieval, qualification, outreach or legacy drain happens in the request.

Tests cover actual FastAPI routing and the inbox client using mocked PostgREST responses, plus independent real PostgreSQL batch rollback/concurrency/replay tests. These are not a claim of actual PostgREST/Meta end-to-end acceptance. The full raw envelope is retained per event; storage/cost sizing and retention monitoring must be reviewed before volume increases. No subscription or credentials were created or activated.

Official Meta webhook/retrieval documentation fetches returned HTTP 429 during this implementation. Current API fields, permissions, Page subscriptions and consent response handling still require official verification before provider retrieval or live release. The receiver uses the existing raw-body HMAC-SHA256 protocol and does not select a new Graph API version.

## Separate retrieval worker

`tools/acquisition_facebook_worker.py` processes one leased inquiry per invocation. `POST /webhooks/facebook/acquisition/worker` requires its own `ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET` bearer secret. No cron/schedule is installed. Global `ACQUISITION_ENABLED` and `ACQUISITION_FACEBOOK_WORKER_ENABLED` must both be true; ingestion and worker switches remain independent so acceptance can be paused separately.

Explicit worker configuration: `ACQUISITION_FACEBOOK_WORKER_SERVICE_KEY`, `ACQUISITION_FACEBOOK_PAGE_TOKEN`, `ACQUISITION_FACEBOOK_APP_SECRET`, `ACQUISITION_FACEBOOK_PAGE_ID`, `ACQUISITION_FACEBOOK_INTEGRATION_ID`, `ACQUISITION_FACEBOOK_GRAPH_VERSION`, plus `SUPABASE_URL`. The worker is pinned to one configured integration/Page and rejects mismatched claims before contacting Meta. No generic key/token fallback exists. The Graph version is required, not guessed; the selected version, Page permissions and subscription must be reviewed before activation.

The worker uses a separate HTTP client for the fixed graph.facebook.com origin, bearer Page authentication, app-secret proof and no redirects. Database credentials never enter that client. It requests lead/form/time/field/disclaimer/attribution metadata, bounds the response, validates returned lead/form identity, prepares intake, and calls atomic completion with the current lease. A lost completion response gets one exact snapshot/token retry, without re-fetching changed provider answers or writing a failure over a possible success.

Credential/permission/data failures park for review; timeouts/rate limits/server failures use the existing bounded retry ledger. Only allowlisted reason codes persist. The trigger returns status/reason only, without seller data or provider exception text. Actual actionable operator alerts and held-job recovery remain open work; a parked audit is not a delivered alert.

Returned disclaimer evidence is deep-copied with missing/empty/false distinctions and a deterministic JSON hash into the immutable intake snapshot. No checkbox is interpreted as a permission grant. Selected response fields are preserved (including complete field/disclaimer arrays); unknown unrequested response keys are excluded. Raw Graph response bytes and a reviewed business-evidence retention policy remain separate release considerations.

Field verification source: [Meta's maintained Python Business SDK Lead model](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/lead.py) includes the requested lead, form, field data, disclaimer responses and attribution fields (reviewed October 26, 2026). This supports field selection; it does not prove the account has permissions or that any particular API version is enabled. The main developer-documentation pages previously returned rate limits.

Validation uses fake HTTP provider/PostgREST transports and separate real SQL intake tests, not real Meta credentials. No campaign, subscription, outbound message, production migration or deployment was activated.

## Combined local acceptance follow-up

The integrated workflow harness now runs the real signed receiver and worker against real SQL through the strict PostgREST adapter, with Meta responses simulated. Five Facebook journeys pass, including lost responses after actual commits and integration disable during retrieval. See WORKFLOW-ACCEPTANCE.md for evidence and exclusions. This closes the previously noted combined local worker/database test gap, not the live provider/PostgREST release gates.

## Workspace inquiry health and in-app guidance

Migration `20261026165322_acquisition_inquiry_health.sql` adds a bounded, authenticated workspace projection and supporting index. `GET /api/acquisition/workspaces/{workspace}/inquiries/health` forwards the user's token/public key, never the service credential. Active owner/admin/operator membership and session/profile checks are required. Caller/agency and unrelated workspace access are denied. The projection remains readable during global/integration disablement so an authorized operator can see the hold.

The projection provides counts, noncompleted receipt references, state/attempts/times, safe reason codes, gate blockers and specific guidance for credential, permission, identity, retry-budget and expired-payload issues. It excludes seller payloads, Page/external lead IDs, lease tokens and secrets. Counts cover the whole workspace independently of UUID cursor pagination. Completed records leave the unfinished list while remaining in summary counts. Worker runtime health is explicitly unknown; a database queue state is not proof that a worker is deployed/running.

The default-off acquisition workspace now displays this health panel ahead of underwriting. Credential-review cases show a visible alert and remediation guidance when the panel loads or is refreshed. Workspace/user changes reset query state; pending/error responses hide stale guidance. No recovery, retry, credential-edit or enable control is exposed. This is an in-app review alert, not a background notification/email or proof of delivery to an absent owner.

The existing app_notifications policies use global recipient roles. No acquisition payload was inserted into that feed. A workspace-aware notification extension and reviewed recovery action remain separate work. Compensation is to keep the acquisition route disabled; this additive read projection changes no job/lead/provider state. Local component tests, feature-enabled build and real database/API acceptance passed; visual browser QA of this new panel and real PostgREST acceptance remain outstanding.

## Reviewed recovery backend

Migration `20261026170113_acquisition_inquiry_recovery.sql` adds immutable recovery records and a user-authorized recovery RPC. `POST /api/acquisition/workspaces/{workspace}/inquiries/{receipt}/recoveries` requires a stable request UUID, exact health `updated_at` timestamp and reason, a 20–2000 character review note and an evidence reference. It accepts no actor/role override. The server requires current owner/admin membership, an approved profile/live session and MFA (`aal2`), holding authority and integration/activation locks through commit.

Only held review states with an allowlisted reason can recover. Disabled integration/global activation, changed review state, expired/purged payload, an already completed intake, or exhausted recovery budget blocks the action. The review must document the actual fix; the API does not itself rotate or validate provider credentials. Fresh provider retrieval/completion checks still apply afterwards.

Approval appends an immutable record and scoped audit, preserves previous attempt count/reason, resets the job to ready and clears the old lease token atomically. Each receipt permits at most three approved recovery cycles, each with the existing five-attempt worker budget (at most twenty attempts including the initial cycle). It does not enable the integration, invoke the worker, contact a seller or authorize outreach. Same-request exact retries return the original approval without another reset. Changed request content or concurrent approval against stale state fails.

`GET .../recoveries` reads at most three history records through user-token RLS for owner/admin/operator. Other workspaces/callers/agencies cannot read them; service roles cannot directly mutate/delete approval history. Evidence references and notes are business review records, not places for credential values.

The dashboard form is not yet wired to these endpoints. Its health projection's `recovery_authorized=false` remains correct: a read is not a reusable execution authorization. The final mutation performs all checks again. Disable integration/worker to compensate; preserve the additive schema and evidence rather than resetting rows manually.
