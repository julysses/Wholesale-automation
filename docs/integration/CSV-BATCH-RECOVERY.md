# CSV AI scoring batch recovery — October 22

Candidate only; not deployed. This closes the all-or-nothing scoring checkpoint
gap without changing default free rules scoring or activating any schedule.

## Problem and implementation

The previous optional AI path could issue up to 400 model calls for a 10,000-row
upload but persisted scores only after the whole loop. A stopped process could
lose known completed scores and leave the entire import under one uncertain claim.

The still-unreleased thirteenth migration now creates ordered private batches of
at most 25 lead IDs. Each batch has a unique claim, snapshots, result and immutable
terminal response. The parent retains the complete reservation across other import
references. Parent locking permits only one submitted batch at a time. Every paid
batch result is saved before another batch can be selected. No background worker,
cron, self-invocation or schedule is introduced.

The CSV SDK path refuses more than 25 leads before obtaining a client, uses
`max_retries=0` and a 45-second SDK network timeout. That timeout is not a guarantee
of total request duration. Only confirmed complete output with the exact selected
IDs and valid scores can be applied. Human changes and completed tasks are held.
Unknown/invalid provider attempts halt further dispatch; submitted batches are
never automatically taken over or repeated.

Original upload reconciliation uses `p_initial_only=true` on the claim RPC. Once
any batch has been claimed, replaying the original data request reports current
progress and cannot advance a later paid batch. A committed data save whose first
claim never occurred can still reconcile the first attempt safely. Explicit
continuation uses the separate endpoint and never resubmits completed work.

| Action | Behavior |
| --- | --- |
| `GET /api/ai/imports/{id}/scoring` | Read-only, owner-bound saved progress; never calls a model |
| `POST /api/ai/imports/{id}/scoring` | One explicit continuation, at most one 25-lead model call |
| `/leads?csv_import={id}` | Signed-in progress panel with read-only refresh, one-batch continuation and score-all action |
| Score all remaining | One explicit paid action processes confirmed unsubmitted batches sequentially; persists each result and stops on uncertainty/review |
| Pause after current batch | Lets the submitted batch finish/save, then starts no next batch |
| Close/navigate away | Stops subsequent browser continuations; submitted batch keeps its durable claim/outcome |
| Unknown POST response | Shows last confirmed totals, disables continuation and requires read-only refresh |
| Unknown claim/provider | Stays submitting or review; no paid replay, including a new import reference |
| Lost known result acknowledgment | Refresh recovers the saved batch; only explicit continuation handles the next batch |

Progress separates scored, held, remaining and in-flight records. Unknown counts
are `null`, never invented zeros. An exact old finish replay returns its immutable
historical progress response; GET returns current aggregate progress. Another
approved actor cannot inspect/continue someone else's private import.

The API returns a `progress_url` for optional AI imports. Default browser imports
continue using free atomic rules scoring. The new panel is a recovery path for
AI imports; loading it or refreshing never grants paid dispatch authority.

## Current runtime evidence

Fresh read-only connector and CLI reads retain production deployment
`dpl_Dwjn7sjLUB5C9X2JsoezbSKjJ6go`, READY at
`a89815126d9a98ced016167d8e383641d133135f`. The API uses Vercel Python/FastAPI
through `api/index.py`; it does not proxy to the alternative Railway host.
The project reports Fluid Compute enabled. The returned metadata has no explicit
project timeout and did not establish the effective per-function override.

Vercel documents a 300-second Fluid default and a 4.5 MB request/response limit.
These are platform documentation facts, not a measured application deadline.
[Function limits](https://vercel.com/docs/functions/limitations),
[Python duration configuration](https://vercel.com/docs/functions/configuring-functions/duration).

The browser now refuses serialized uploads above 4,500,000 UTF-8 bytes before
submitting any rows, with an actionable message. It never silently truncates or
partially auto-splits an oversized file. A test preserves all 10,000 short rows
when the full body fits; that is a transport test, not a 10,000-row database or
real-model latency benchmark. Larger payloads need smaller operator-prepared files
or a separately reviewed staging/upload design.

No production settings, environment values, data, providers or schedules changed.
No secrets were printed or retained in runtime evidence.
`csv-runtime-observation-2026-10-22.json` records only reviewed metadata.

## Verified recovery

The real PostgreSQL/API harness uses synthetic rows and stubs only Auth/model
boundaries. It verifies:

- 60 leads finish as 25, 25 and 10; all 60 IDs appear in one model attempt each.
- Original data-request replay after the first completed batch starts no next
  paid batch; explicit continuation completes the remainder.
- A fresh API client reads the first saved 25 scores after a simulated restart.
- An unknown second batch preserves 25 completed scores, holds 25 and leaves 10
  unsubmitted. Retry starts no model and does not change the first batch evidence.
- A lost second finish acknowledgment recovers 50 saved scores; explicit continuation
  scores only the last 10. No completed ID is submitted twice.
- Worked records before claim create no paid attempt; other unsubmitted batches
  remain available. Stale records and completed tasks remain unchanged.
- Terminal batch updates/deletes are refused; old exact finish replay is immutable.
- Approved foreign-actor GET and POST are refused before model work.
- Eight sessions contend for one batch claim; one wins, eight exact finishes replay,
  and the final unsubmitted record completes through a new legitimate claim.
- Existing save/claim/result lost-ack, invalid-output and same-reference checks pass.

The full thirteen-migration upgrade/rollback/history/access and ten intake journeys
also pass (ten journeys in 124.46 seconds); `production-upgrade-result.json` and `csv-connected-scoring-result.json`
contain the final run. Frontend tests cover read-only mount, explicit single/all
continuation, pause, no advance after uncertainty, last-confirmed totals, invalid
links/receipts and oversized/all-row transport behavior. SDK tests enforce the
single-call bound and disabled retries.

Full backend: 1,334 passed/10 skipped. Full frontend: 274 tests/56 files;
build/typecheck/lint gate pass (143 existing findings). Pipeline source is unchanged
from its prior 231-test checkpoint.

This does not prove production Auth/JWT, real provider latency, maximum database
volume, production index locks or signed-in operator acceptance. Buyer UI, dependency/
security, exact release/recovery and live Meta/website/provider gates remain open.
PR #21 remains draft; broad sending schedules must remain paused pending review.
