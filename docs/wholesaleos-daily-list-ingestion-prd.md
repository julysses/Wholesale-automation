# WholesaleOS daily list ingestion PRD

Original requirements: October 11, 2026. Dallas/Collin scope and implementation checkpoint: October 12, 2026.

## Goal and boundaries

Automate official distressed-property collection for Hilltop Home Co. and WholesaleOS. Target: verified new records scored and ready for permitted outreach within 60 minutes of collection. Initial launch is Dallas and Collin counties only. Code enforcement is municipal; a city dataset never establishes countywide coverage or proves a property's county.

Preserve the existing React/Vite frontend, FastAPI backend, Supabase, Vercel, Claude scoring, Twilio SMS, Retell calling, underwriting, appointments and deal workflows. GPT owns collection only. Humans establish every offer price and approve offers. No automatic seller contact, paid tracing, ad activation, production deployment, or offer delivery is authorized by this preservation checkpoint.

The supplied video summary informs the design; its vendor pricing and volume claims are unverified. Adopt off-market/direct-to-seller/needs-to-sell evidence, government lists, reviewed reusable collection procedures, distress stacking, compliant enrichment and buyer ranking. Do not infer consent or bypass access controls.

## Source configuration and daily schedule

All times use America/Chicago, including daylight saving time. On October 13 the owner clarified that no operating collection schedule exists; the earlier task was unfinished. Rebuild and verify delivery before installing a recurring schedule. No local Codex automation definitions were found in the inspected default automation location; this does not inventory cloud ChatGPT Tasks. Endpoint delivery and credentials remain unverified. The migration seeds sources **disabled**.

| County | List | Pull time | Initial window / recurrence |
| --- | --- | --- | --- |
| Dallas | Pre-foreclosure | 05:00 | Maximum 30 inclusive filing days |
| Collin | Pre-foreclosure | 05:05 | Maximum 30 inclusive filing days |
| Dallas | Probate | 05:10 | Initial 30 days; seven-day overlap |
| Collin | Probate | 05:15 | Initial 30 days; seven-day overlap |
| Dallas | Tax delinquent | 05:20 | Latest official snapshot; compare prior verified snapshot |
| Collin | Tax delinquent | 05:25 | Latest official snapshot; compare prior verified snapshot |
| Dallas | Code violation, Dallas city | 05:30 | Initial 30 days; seven-day overlap; archived starting dataset needs replacement |
| Collin | Code violation, McKinney | 05:35 | Initial 30 days; seven-day overlap |

Delivery deadline: 06:00. Owner digest target: 07:30. Source schedules, lookbacks, enabled state and routing threshold must be configurable without a deploy. Other municipalities, including Plano, Allen and Frisco, remain unonboarded.

## Collection procedure

Prefer official exports/APIs over browsing. Use only public decedent-estate probate matters; exclude guardianship, minors, mental-health and sealed records. Keep foreclosure notice filing, underlying mortgage recording and auction dates separate. Tax sale inventory alone does not cover all delinquent owners. Exclude personal-property tax accounts. Do not substitute general 311 complaints or permits for verified code cases.

Use a reviewed, versioned procedure per source. Stop at CAPTCHA, login wall, access denial or rate limit and request human review; never bypass. Report transport/parser failures as failed, incomplete coverage as partial and access restrictions as blocked. Zero-record success requires verified complete coverage. Unknown fields are null; never invent values. Verify county and property identity with authoritative evidence. Probate name-only matches remain unresolved. Do not collect SSNs or sensitive court details.

Collector prompt must instruct one explicit status per source, exact window and as-of date, source identifiers and document URLs, and no following instructions embedded in source content. Procedure changes require review. Keep ingest secrets outside prompts, files and logs. Preferred delivery is scoped authenticated HTTPS; a verified polling-folder path is fallback. Collection-only files must not be described as ingested, scored or contacted.

## Payload contract and ingestion

Deployed contract source: `frontend/supabase/functions/daily-list-ingest/ingest.schema.json`.

Required manifest: schema_version, source_key, code-generated UUID run_id, scheduled_for, pulled_at, source (state/county/jurisdiction/list_type/source_url), status, status_reason, lookback_days, window_start, window_end, coverage_complete, source_as_of, records_sha256, records. Municipal source keys append the municipality.

Each record retains stable source_record_id, case_number, filed_date, auction_date, property_address, unit, city, state, zip, parcel_id, owner_name, mailing_address, amount_owed, amount_type, source_url and minimal raw evidence. Unknown identity goes to review. Hash records using the shared JavaScript canonicalJSON implementation: recursively sorted object keys, array order preserved, JSON.stringify scalars, compact encoding and SHA-256. Split above 2,000 records or 2 MiB without truncation; preserve run metadata and include batch_index/batch_count plus per-batch hashes.

Ingress authenticates an expiring source-scoped token, validates structure and semantics, verifies hashes/allowed hosts, and atomically stores run, raw payload, staged records and jobs. Same reference and same content replays safely; changed content under the same reference conflicts. Do not process an incomplete batch set as complete. Retain raw payloads 90 days. Use restricted database roles; collectors never receive database credentials.

## Data model and processing

Keep existing public CRM tables authoritative. The additive private `wholesale_ingest` schema contains sources, ingest_runs, raw_payloads, records, properties, property_aliases, distress_signals, signal_observations, jobs, lead_evaluations, skip_trace_requests, contacts, daily_budgets, daily_digests and expected_runs. Operations add review_events and settings. Enable RLS and deny anonymous/browser access to private records; expose approved administrative operations through the backend.

Property identity includes county and state. Prefer verified parcel ID; retain address aliases including unit so later parcel enrichment does not create a second lead. Conflicting identities and ambiguous legacy CRM matches require review. A second list hit adds provenance/distress evidence rather than another property lead. Stack count means distinct active list types, not repeated daily observations.

Enrichment uses a swappable provider adapter, only for new unenriched leads, with atomic daily budget reservations and request idempotency. Unknown provider outcomes require reconciliation before retry. National/Texas DNC, internal opt-outs, fresh screening evidence and channel-specific consent must pass. DNC-clean does not mean consented. Preserve existing provider gates and recipient restrictions. Assumed outreach window is 09:00–20:00 recipient local time, subject to approved policy; enforce again at dispatch, with configured send caps.

Claude produces validated 0–100 scores, reasons and flags. Starting weights: distress stack 30, need to sell 25, equity 20, contactability 15, recency 10. Include ODN evidence and unknowns; do not invent equity from incomplete debt data. Persist model/prompt version and input identity. Rule-based routing, not model output, determines eligible call/SMS, vacant-lot underwriting or nurture. Nurture is not permission to send. Lots use the existing underwriting platform.

Offers remain human-entered and approved with durable evidence. Buyer ranking returns the top three eligible cash buyers from area, purchase history and price fit, excludes wholesalers, and records closing outcomes. Do not send buyer messages as part of ranking.

## Functional requirements and final acceptance tests

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-1 | Configurable source settings | Admin can update valid settings; unauthorized users denied; foreclosure cap enforced |
| FR-2 | Per-source status | Success/partial/blocked/failed preserved with reason and coverage |
| FR-3 | Strict contract | Invalid payload gets 4xx field errors without writes |
| FR-4 | Idempotency | Exact replay, conflicting replay, lost ACK and simultaneous duplicate requests create no duplicates |
| FR-5 | Raw retention | Replay before expiry; scheduled removal after 90 days without destroying normalized provenance |
| FR-6 | Property dedupe | Repeat hits, parcel enrichment, unit/county differences and conflicting aliases handled correctly |
| FR-7 | Lookback/backfill | Inclusive boundary tests, maximum 30-day foreclosure window, filing versus auction dates |
| FR-8 | Blocked-source review | Blocked receipt creates one operator task; no bypass or false empty success |
| FR-9 | Tracing adapter/budget | No retrace of enriched lead, concurrent cap enforcement, ambiguous-outcome recovery |
| FR-10 | Compliance gates | DNC, opt-out, consent, quiet hours and caps fail closed at queueing and dispatch |
| FR-11 | Scoring | Validated score/reasons/flags, ODN/equity unknowns, configurable threshold, stale input rejected |
| FR-12 | Lot routing | Verified lot handoff and acknowledgement through existing underwriting |
| FR-13 | Daily digest | Source counts, new/stacked leads, top ten and all failures; actual owner delivery by 07:30 |
| FR-14 | Heartbeat | Missing payload/incomplete batch alert by deadline, DST correctness and deduplicated tasks |
| FR-15 | Provenance | Every normalized lead/signal traces to source URL, pulled_at and run_id |

Also test authentication/RLS, token expiry/rotation/scopes, payload size, source injection, out-of-county exclusion, review audit, false code cases, stale tax snapshots, malformed Claude output, provider outages, unauthorized offer pricing/sending, buyer exclusions, UI recovery, regression suites and backup/restore.

Phase-one acceptance requires 14 consecutive unattended days, zero duplicate leads in the acceptance run and every failure alerted. Operational targets: source success/partial at least 95%, pull-to-ready within 60 minutes, duplicate audit under 1%, valid DNC-clean contact at least 70%, blocked sources under 10%, digest on time at least 95%. Measure contact and appointment rates without conflating them with consent. Quiet-hour holds must be reported separately from processing latency.

## Build and release gates

1. Schema/ingress and handmade payload: contract, rollback and replay proofs.
2. One county foreclosure source: five supervised clean runs with verified delivery.
3. Add other lists: provenance, geographic verification and stacking.
4. Enrichment, compliance and existing queues: no unauthorized dispatch.
5. Claude scoring, underwriting, heartbeat and delivered digest.
6. Both counties and 14-day unattended acceptance.
7. Cash-buyer ranking against a real authorized contract and recorded outcomes.

Do not certify launch from code or unit tests alone. Verify provider configuration, collector delivery secrets, CRON_SECRET/scheduling, owner notification receipt, controlled Retell callback/handback, SMS STOP/refusal, email unsubscribe, Meta consent, Auth/Storage/Edge restore, approved Texas legal/disclosure/offer/title process, staffing, ad caps and final go/no-go. These requirements remain acceptance gates until evidenced.

## Assumptions and unresolved decisions

- Counties fixed to Dallas and Collin; foreclosure first.
- All four list types daily, configurable; official publication frequency may be slower.
- October 13: PropStream browser workflow selected. Latest authorization: use only the existing $50 prepaid balance, no refill or upgrade; this is a total cap, not a recurring allowance. Verify quotes and reconcile results. API adapter remains deferred.
- GPT HTTPS/secret-store delivery has not been verified; no fallback integration is assumed working.
- Owner and counsel confirm legal/contact rules before outreach activation.
- Official county evidence and reviewed procedures are required before automatic matching.
- The October 12 McKinney collection has 141 unresolved candidates; it is not verified outreach inventory.

Implementation checkpoint and migration reconciliation: see `docs/dallas-collin-launch-prep-checkpoint.md`. This PRD describes the target, not a claim that all features are complete.
