# Dallas/Collin launch preparation recovery — October 12, 2026

## Current blocker

User supplied the continuation brief from ChatGPT task **Review AI Wholesale Automation**, conversation `6acc2a81-02a4-83ea-9698-1b490c63f558`. Its associated durable execution task is `01a12d86-eab0-768f-9170-ded60cf100ca`, cwd `/workspace/scratch/08cdfe13643f`. Both histories were read and the exact handoff matched.

The previous checkout `/workspace/scratch/08cdfe13643f/wholesale-automation` is not mounted on this computer. Successful authenticated-network `git ls-remote --heads origin codex/dallas-collin-launch-prep` returned no matching branch. Local search found none of the new pipeline implementation. Do not assume the source was pushed or reconstruct it over existing work. Request commit/push or an export from that task, including untracked implementation, tests and PRD, excluding credentials and dependency directories.

Existing local `codex/twilio-live-integration` was clean apart from two unrelated duplicate documents; `git pull --ff-only` returned already up to date at b0695c9. Preserve those duplicates. No source code, production setting, provider send or database mutation occurred during this recovery audit.

## Verified database state (read-only)

Rehearsal `tbhwxgfzbiaqjurghntj` migration history:

| Version | Name |
|---|---|
| 20261012174903 | daily_list_ingestion |
| 20261012181333 | list_operations_setup |
| 20261012181357 | list_pipeline_snapshot |
| 20261012181402 | configure_list_source |
| 20261012181414 | resolve_list_record |

`list_pipeline_snapshot`, `configure_list_source`, and `resolve_list_record` exist as INVOKER functions. EXECUTE is denied to anon/authenticated and granted to service_role. `scan_list_pipeline` is absent from both function inventory and relevant migration history. This resolves the interrupted migration uncertainty, but is not a functional acceptance test.

Private schema wholesale_ingest contains 17 tables: contacts, daily_budgets, daily_digests, distress_signals, expected_runs, ingest_runs, jobs, lead_evaluations, properties, property_aliases, raw_payloads, records, review_events, settings, signal_observations, skip_trace_requests, sources.

All eight sources exist, disabled, with no procedure approval timestamp. America/Chicago configured times match the brief: Dallas foreclosure05:00/probate05:10/tax05:20/code05:30; Collin foreclosure05:05/probate05:15/tax05:25/McKinney code05:35. Foreclosure lookback30; probate overlap7/backfill30. These rows do NOT prove external GPT schedules or delivery credentials are configured.

Production `dvzhzlipbwzzcliujzyz` has atomic_intake_alert_delivery version20261010020730. None of the new pipeline migration names queried were present. Do not replay the combined local migration files when recovered: compare actual definitions and apply only missing reviewed content.

## Additional source finding

The available older checkout still has Claude-generated offer prices in `web/api/__init__.py` generate_offer and `frontend/supabase/functions/generate-offer/index.ts`. The human-only offer changes described in the handoff are unavailable locally. Their implementation and all remaining offer paths must be verified on the recovered branch before launch; no offer was generated or sent in this audit.

## Resume order

1. Recover original branch and PRD from the identified task; inspect dirty state and diff before checkout or merge. Preserve original work and do not overwrite the absent branch with a replacement.
2. Reconcile migration bodies against rehearsal definitions/history above. Finish scan RPC in isolation only, test privileges, atomicity, replay/conflict, partial batches and concurrent claims.
3. Complete downstream enrichment/DNC/consent, scoring/routing, delivered digest/alerts, buyer ranking and human approval safeguards using existing workflow boundaries.
4. Map the actual PRD's 15 requirements to code and test evidence; the PRD itself has not been recovered and its requirement numbering must not be invented.
5. Run relevant backend/frontend/pipeline/security suites; push reviewable branch and draft PR. No production release or launch certification yet.

Keep all original recipient, outreach, spend and provider acceptance gates. The 141 McKinney pilot candidates remain unverified; no candidate import occurred here.
