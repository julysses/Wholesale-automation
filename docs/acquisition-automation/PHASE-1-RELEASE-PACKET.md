# Phase 1 release packet — Facebook seller inquiries

Prepared October 30, 2026 from the current acquisition branch. Status: **not ready for live activation**. This packet distinguishes what is implemented from the hosted/provider work needed to launch. It does not authorize migrations, secret changes, a scheduler, advertising, seller contact or a test lead.

## Exact candidate and evidence

- Branch: `codex/acquisition-foundation`.
- Published UI candidate: `69239df98a2754c1b6f1674858fb9d3e52ac252b`; CI `41138136317`. All six jobs completed successfully, with the last job finishing at 22:36:42 UTC. Verify the successor run after publishing retained work.
- Retained gateway acceptance commit: `922de78`. All 50 proposed migrations, 60 full-catalog workflows, 26 access probes and 23 real local PostgREST checks passed. Evidence: `evidence/2026-10-30-content-http-result.json`.
- Migration scope is the exact ordered `migrations` list in `evidence/acquisition-upgrade-manifest.json`, not every repository migration and not a wildcard deployment. Manifest SHA-256: `60dee1837cc5efa95f4bba769cdbcf85ec242d70931148c24d1e543464ea2732`. Its `production_apply_approved` remains false. If the list or hash changes, review the replacement candidate and repeat affected acceptance.
- Captured production application baseline ends at `20261023221455`; latest metadata recheck was 2026-10-30 22:25:17 UTC. This is not a claim about current deployment. Refresh the catalog, grants and ledger immediately before any approval proposal/application.
- Local history preservation covers 24 representative synthetic rows across 22 populated tables and 103 definitions. Managed Auth/Storage are fixtures; local transport uses signed synthetic JWTs. These results do not prove hosted platform behavior or every historical record state.

## Implemented Phase 1 path

`web/api/acquisition_webhooks.py` receives `/webhooks/facebook/acquisition`, verifies the raw-body signature, bounds and parses native Page events, and calls `accept_facebook_acquisition_batch` before acknowledging durability. Integration routing supplies the workspace; the event cannot choose it. Conflicting/replayed provider events are reconciled in SQL.

`tools/acquisition_facebook_worker.py` processes one leased inquiry per invocation. It uses a separate Graph client, token header and app-secret proof; it checks form/ad identities, bounds provider data, preserves consent fields and submits the exact prepared intake. Ambiguous completion is retried with the same snapshot and lease. Credential/permission errors become held review states with safe reason codes. This function is not a deployed or monitored worker schedule.

`InquiryHealth.tsx` and `InquiryRecovery.tsx` provide in-app processing guidance and documented owner/admin recovery with MFA. The user works through the existing acquisition page: prepare campaign, review inquiry, evaluate property, review proposed amount. Amount approval is internal review; no message or binding offer is transmitted. Generic form submission does not grant unrestricted outreach consent.

## Controls that must be verified by environment

Record only **present/missing**, **enabled/disabled**, approved identity references and observation time. Never put secret values or tokens in this packet, logs, screenshots or chat.

| Control | Inspected code contract | Required hosted evidence |
| --- | --- | --- |
| UI visibility | `VITE_ACQUISITION_ENABLED` controls `/acquisition-review` | Deployed build identity, actual user/workspace access and screen walkthrough |
| Intake | Both `ACQUISITION_ENABLED` and `FACEBOOK_ACQUISITION_INGESTION_ENABLED` required | Initially disabled; authorized activation window and receiver URL verified |
| Inbox credential | `ACQUISITION_INGESTION_SERVICE_KEY`, HTTPS `SUPABASE_URL` | Correct project, server-only custody and approved rotation/revocation procedure |
| Webhook authenticity | `ACQUISITION_FACEBOOK_APP_SECRET`, `ACQUISITION_FACEBOOK_VERIFY_TOKEN` | Approved app/Page subscription, challenge and valid/invalid signature outcomes |
| Worker | `ACQUISITION_FACEBOOK_WORKER_ENABLED`; exact integration/Page/version configuration | Initially disabled; monitored trigger cadence, ownership, alerts, lease expiry and restart acceptance |
| Worker trigger | Bearer `ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET` at `/webhooks/facebook/acquisition/worker` | Secret custody, restricted invocation and rejected unauthorized requests |
| Retrieval | Worker service key, Page token, app secret, Page ID, integration ID, Graph version | Current official Meta permissions/version/field review and actual authorized retrieval; no guessed version or unverified token |
| Database | Private activation and provider integration gates, workspace status | Approved disabled configuration, MFA/session/role tests through hosted Auth and Data API |
| Payload retention | Bounded `purge_acquisition_payloads` RPC; configured receipt expiry | Reviewed duration and metadata/legal-hold policy, monitored runner and failed-run alert. No retention scheduler currently established by this branch |
| Existing operations | Acquisition receipt states are separate from legacy pending jobs | Before/after SMS scheduler flags and held jobs, county ingestion and CRM smoke checks on the deployed environment |

No new retention endpoint or scheduler should be activated merely because the purge RPC exists. The current source does not establish a legal-hold administration workflow or monitored retention service. Resolve policy and implementation before accepting live sensitive payloads.

## Acceptance record required to close FB-001–006

Use fresh, explicitly approved test leads only. Do not reuse old held sessions, fabricate provider events as live evidence, or replay customer submissions. Synthetic replay tests remain valid only as labelled local tests.

| Case | Existing evidence | Missing release evidence |
| --- | --- | --- |
| Capture and qualify | Signed synthetic webhook → durable receipt → Graph fixture → canonical intake; consent and ad/form provenance retained | One approved Meta test lead with actual IDs/timestamps, authorized retrieval and correct workspace CRM record |
| Retry | Local durable acceptance/completion loss and exact retry tests | Controlled approved provider delivery retry reconciles the same receipt/lead; no seller contact |
| Missing address | Synthetic incomplete-intake classification | Fresh incomplete test lead appears with a clear next action in the actual app |
| Invalid signature | Local rejection without durable writes | Hosted rejection and safe log record; no sensitive payload logged |
| Expired credentials | Held job, safe reason and recovery API/UI tests | Controlled approved credential failure, visible owner alert, documented fix, same-record recovery |
| Permission/opt-out | Form evidence preserved; generic submission does not authorize outbound AI/SMS; suppression tests | Actual form wording/version reviewed; opted-out test identity remains prohibited in follow-up |
| Isolation | Local RLS/session/MFA and actual local gateway checks | Two hosted workspaces, real issued sessions, denied unrelated access and revocation acceptance |
| Attribution | Campaign/ad/form lineage and reviewed costs/underwriting paths | Actual test lead joins the intended campaign and reports correctly; closed-transaction attribution remains dependent on contract/disposition work |
| Operational independence | Legacy queue and historical row preservation in disposable tests | Production SMS remains paused; county/CRM controls and held records unchanged |

Record commit/build, project, workspace, test IDs, observations, expected/actual outcomes and reviewer for every hosted case. Store sensitive evidence in the approved access-controlled location and link its reference; do not put seller data in Git.

## Separate approval stages

1. **Hosted isolated rehearsal:** identify and verify the disposable target, ownership, external-network/provider controls and synthetic identities. Establish real Auth/MFA/Storage/Data API acceptance against the exact candidate. This packet does not identify or authorize a target yet.
2. **Disabled production deployment/migrations:** after hosted acceptance, present the exact commit, deployment targets, refreshed baseline, immutable migration list/hash, backup/restore evidence, compatibility checks and compensating controls for approval. Keep global/provider/UI execution gates disabled. Do not replay existing historical migrations.
3. **Controlled Facebook acceptance:** after disabled deployment verification and provider/retention readiness, obtain approval for the exact Page/form, fresh test lead, receiver/worker window and evidence destination. No paid campaign publication, seller follow-up or SMS activation is included.
4. **Phase 1 activation:** requires all acceptance cases and an explicit reviewed channel/budget scope. Later inbound/mail/portal/caller/agency activation gates remain separate. A green build does not pass this gate.

## Containment and remaining implementation

Before any live window, record the authorized operators and exact commands/configuration for disabling intake and worker triggers, disabling the private integration/global activation, hiding the UI when necessary and preserving receipts/audits. Do not delete evidence, reset immutable history or re-enable SMS as a recovery shortcut. Unknown provider outcomes remain held until reconciled.

Next work: define the isolated hosted target and its approved test scope; implement the monitored worker/retention operational contract and remaining retention policy controls; verify current Meta integration requirements. The full PRD still requires canonical postal eligibility and batch reservations, the selected mail adapter/proofs, online offer portal, manual human caller, agency controls, and contract/disposition workflows. Phase 1 packet completion is not completion of those requirements.
