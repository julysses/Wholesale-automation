# Facebook inquiry runner — deployment contract

The supervised entry point is implemented but **not installed, scheduled or enabled**. Read `docs/acquisition-automation/PHASE-1-RELEASE-PACKET.md` before proposing a deployment. This runner processes already accepted inquiries; it does not subscribe a Page, publish an ad, contact a seller, purge data or change database activation.

## Command and configuration

```sh
python -m tools.acquisition_facebook_runner --max-cycles 1
```

This command is inert with the supplied example configuration and exits 78. It does not read the example file or dotenv automatically. The runner requires `ACQUISITION_FACEBOOK_RUNNER_ENABLED=true` in addition to the existing worker's application/worker flags, private integration/global gates and reviewed server-only credentials. Never supply tokens in command arguments. Use the host's secret manager and the exact approved project, Page and integration.

An approved supervisor may run a finite sequence with `--max-cycles` (1–10000) and `--interval-seconds` (30–3600; default 30). Default is exactly one cycle. No background task, cron job, Railway service or paid worker is created by this repository change. This CLI calls the existing Python worker directly and does not need the HTTP trigger secret. If the HTTP worker endpoint is independently deployed, its trigger remains separately protected.

One cycle claims at most one event using the existing SQL lease, retrieves the authorized lead and settles its intake or deferral. Claims, attempt budgets and retry deadlines stay in PostgreSQL. The runner never resets a lease, creates an alternate recovery request, writes an intake directly or overrides a queue hold. Concurrent instances remain subject to SQL claims, but the initial deployment should use one supervised instance.

## Exit and monitoring contract

Each newline-delimited JSON event contains component, random run ID, UTC timestamp and cycle number. Events are `cycle_started`, `cycle_finished` and `stopped`. Confirmed results contain only status, approved classification/duplicate fields or an allowlisted reason code. They contain no seller fields, external lead IDs, workspace IDs, tokens, payloads or raw exception text.

| Exit | Meaning | Supervisor action |
| --- | --- | --- |
| 0 | Finite run finished or stop requested; inspect confirmed results | Schedule only within the approved cadence; idle is not proof of provider acceptance |
| 1 | Operation/result unconfirmed, unexpected error or total timeout | Alert and reconcile queue health. Never assume nothing committed. If a restart is approved, wait at least 120 seconds from the failed attempt so the original lease can expire; retain server backoff/attempt limits |
| 2 | A confirmed inquiry was parked for review | Alert the owner and stop automatic restarts. Use Inquiry Health and the documented MFA recovery workflow after fixing the cause |
| 78 | Runner is disabled | Keep stopped; do not enable flags as an automatic repair |

The existing worker still performs its exact bounded completion retry before reporting an unconfirmed result. The runner itself does not immediately repeat an uncertain cycle. A 60-second total cycle deadline bounds a slow response stream as well as individual HTTP timeouts. Cancellation leaves the database lease and any committed result intact for reconciliation.

SIGINT/SIGTERM sets a stop request: an in-flight cycle may settle within that 60-second bound, then no next claim starts. The supervisor must allow at least 70 seconds of graceful shutdown before forced termination. SIGKILL/host loss cannot report a final event; SQL leases remain the recovery source.

Before activation, configure and prove external monitoring for: nonzero exit; `cycle_started` with no finish/stop after 70 seconds; unexpected process absence; and missing next start beyond the approved interval plus startup allowance. Connect alerts to an approved destination and verify receipt. These logs are the monitoring interface, not an implemented alert delivery service. The app's database queue-health view must continue to report worker runtime as unknown until an authenticated runtime-health integration is separately implemented.

## Acceptance and limits

Offline tests exercise disabled real CLI startup, bounds, result/error redaction, timeout, gate changes between cycles, stop during/after work, actual subprocess SIGTERM, and the actual Python worker with synthetic database/Meta transport. They do not call live Meta, create a hosted worker, verify secret custody or prove alert delivery. Use current hosted acceptance, monitored retention and a separately approved fresh test lead before live ingestion.

Compensation: stop the supervised process and disable the runner/worker flags and approved integration controls; retain receipt/audit/recovery history. Preserve paused SMS and county ingestion. This runner does not manage retention; an approved monitored retention service and policy remain launch prerequisites.
