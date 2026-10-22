# Buyer saved outreach history: complete reads and honest unavailable states

October 22, 2026. Candidate-only read/UI repair. No backend, database, dependency,
provider, runtime flag, schedule or production setting changed. The same fourteen
forward migration proposals remain unapplied.

The old Outreach Log loaded at most 100 rows and ignored read errors. Both an empty
response and a failure could become “No outreach sent yet”. It offered no way to
find older records, review complete messages or identify the saved destination.

`BuyerOutreachHistory.tsx` now reads all current saved rows with an exact count,
stable created_at/id order, count consistency and unique record checks before
replacing confirmed data. It renders 25 rows per page. Search and channel filtering
apply to the complete confirmed set, including buyer, destination, message, subject,
status, provider and receipt ID. An initial failed/incomplete/changed read shows
unavailable totals and an explicit retry. A failed refresh retains the last complete
saved set with a warning. Verified empty data is labeled “No saved outreach records”.
These page checks detect incomplete/changed reads; they are not a database snapshot
across simultaneous updates.

The screen shows recorded direction, raw status, destination, provider/receipt ID,
record timestamps and recorded reply evidence. “sent” is not translated into a
confirmed delivery claim. Missing provider IDs and buyer names have visible
fallbacks. Expandable full messages are escaped React text, including saved HTML;
no message HTML is executed. The screen states that missing send logs require
provider review and delivery confirmation requires a recorded receipt.

History loads only when the operator opens its tab. The outreach summary's existing
“Review outreach activity” action invalidates this history and opens that tab; no
send or replay is initiated by reading, refreshing, paging or filtering. Confirmed
buyer imports now refresh the buyer list immediately rather than after a stale
three-second background-save delay, because their transaction is already committed.

## Evidence

- Eight new UI regressions pass: 1,003 saved records through a forced 200-row cap;
  25-row rendering; page navigation/search beyond row 1,000; literal punctuation;
  channel filtering; partial/error/changed/missing-count/repeated-page refusal;
  retained-data refresh recovery; raw status and inert HTML; actual page-tab lazy
  loading with no API/provider calls.
- All 303 frontend tests in 60 files pass. Build/typecheck pass. Lint gate passes
  with no new findings and 142 existing findings. Large-bundle warning remains.
- Backend, pipeline and migrations are unchanged, so prior backend 1,345/10 skipped,
  pipeline 231 and fourteen-migration/ten-journey checks were not rerun for this UI
  repair. The last Python audit locks/reports remain unchanged and hash-valid.
- Ignored logs: `logs/friday-outreach-history-{focused,frontend,build,lint}.log`.
  No signed-in production browser test was performed; Supabase reads are mocked in
  UI tests. This proves the read/error/display behavior, not live record coverage.

## Remaining history and release proof

Complete current saved rows are not proof that every actual attempt was recorded.
The buyer send endpoints call providers before inserting their logs; log failures
are reported separately. Skipped attempts are not persisted by those paths. Current
buyer inserts also do not populate `provider_msg_id`; repository search found no
buyer-log receipt/reply update path. Existing deletion cascades can remove a buyer's
saved history. These limitations require durable attempt/log/receipt and retention
review before broad buyer outreach acceptance. Do not manufacture receipt IDs,
reconstruct outcomes from “sent”, or resend unknown attempts to make history green.

The separate `/api/buyers/leaderboard` endpoint still has bounded top-result semantics;
this fix concerns the global saved-history tab, not that endpoint. Explicit buyer
classification/rescore, manual-create ambiguity, APN event history/production locks,
signed-in workflows, production JWT/tenancy and real build/deployment/rollback still
need acceptance. Live source consent/routing, sending flags, owner notification,
handset delivery/reply/STOP remain open. Broad schedules stay paused.
