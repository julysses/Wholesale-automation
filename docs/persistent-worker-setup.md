# Persistent bulk worker deployment

## Implemented scope

`pipeline/collectors/persistent_worker.py` is a restart-safe **tax collector/delivery worker**, not a completed foreclosure/PropStream integration. It schedules Dallas and Collin tax batches after06:00America/Chicago, preserves collection state in SQLite, and delivers through the existing source-scoped rehearsal Keychain credentials. One process holds an OS lock. It writes a private status file containing counts/states, never raw contacts or credentials.

Accepted jobs are not rerun. An interrupted collection is held rather than silently regenerated; uncertain delivery is held as an exception without automatic retries; any explicitly reviewed recovery must reuse the saved manifests and server receipt identities. One county failure does not stop the other. Existing Supabase supervision raises missing/partial-source incidents inside WholesaleOS. Local worker exceptions are saved locally; no claim is made that their detailed reasons are already synchronized to the CRM.

No trace order, reservation, reload, seller outreach, browser session copying or production access exists in this worker. The cumulative$50PropStream cap remains enforced by the existing database functions and is unaffected.

## Mac deployment selected and installed — October14

Owner selected this Mac with existing credentials and explicitly declined additional PropStream/API cost. Do not ask again about hosting, API purchases, a trial or an upgrade. No cloud worker is authorized/needed for this deployment.

Installer: `python3 scripts/install_mac_collector.py`. It packages only the collector/runtime dependencies into `~/Library/Application Support/WholesaleOS/rehearsal-worker/runtime`, saves exact source hashes, and registers `~/Library/LaunchAgents/com.wholesaleos.rehearsal.collector.plist`. Private SQLite state, logs and raw county evidence live in the sibling `state` directory. No tokens are stored in the plist; existing source-scoped Keychain credentials are used. The initial direct-from-Documents service was blocked by macOS; the packaged runtime starts successfully without changing privacy permissions.

The service has one calendar trigger at06:17Maclocaltime daily. It does not run at login, loop continuously or restart after a failure. Each launch processes one pass and exits. A missed calendar event may run when the Mac wakes; existing source/day jobs prevent repeated collection. Mac must be awake, online and logged in. Power settings are unchanged. Successful unchanged status is quiet; exceptions are retained in the private status file and missing/partial source receipts are monitored inside WholesaleOS.

Inspect: `launchctl print gui/501/com.wholesaleos.rehearsal.collector`. Stop: `launchctl bootout gui/501/com.wholesaleos.rehearsal.collector`. Reinstall only when collection is idle: stopping during capture deliberately holds the interrupted job instead of manufacturing a new run. Preserve the state directory across upgrades/reboots; never reset it to retry uncertain delivery.

## PropStream connection evidence — October14

Signed-in Account shows Legacy plan, $50 prepaid, PropStream Connect **Start Free Trial**, and a single displayed integration: **BatchDialer / Connect**. No WholesaleOS/API integration is displayed. Official [BatchDialer integration documentation](https://www.propstream.com/news/push-to-batchdialer-seamless-api-sync-from-propstream-to-batchdialer-for-high-volume-calling) describes pushing selected contacts to BatchDialer; it does not document a general inbound skip-trace API for WholesaleOS. This does not prove private partner APIs do not exist. The owner declined additional API cost. Keep the browser handoff; do not pursue a paid API or activate the offered trial. The existing access-request document is unsent and no longer a prerequisite chosen by the owner.

Do not confuse PropStream with Prostream, Propstreet or PropSpace search results. No provider API endpoint or authentication scheme should be invented. Do not extract signed-in cookies/tokens, start a trial, add a subscription or repurchase the75completed traces.

## Acceptance still required

- [x] Mac host selected; persistent state/runtime and login service installed using existing scoped credentials.
- Verify a real county collection/delivery, crash recovery and the next scheduled run.
- Connect local worker exceptions/heartbeat to the existing CRM incident mechanism.
- Implement unattended foreclosure capture and structured verification.
- Obtain/document supported PropStream transport and verify quote, single submission, receipt and billing reconciliation under the existing total cap.
- Verify new eligible-only selection and no orders for completed/no-result/uncertain receipts.
- Keep contact availability distinct from channel clearance and outreach authorization.

### First live Mac run — accepted Collin, Dallas source exception

Collin run311ee85d-e46c-4c49-bdf6-c46bd3272a19 has19accepted batches /9,182tax-reviewrecords, one delivery attempt and no pendingbatch. These are review observations, not9,182qualified/newleads. Dallas collection halted before generating/delivering manifests: the official tax-roll page links to `https://www.dallascounty.org/Assets/uploads/docs/tax/trw/trwfile.754635.zip`, which returnedHTTP404on an independent exact-link check. No fallbackURLguess, fabricatedemptyrun or duplicateimport. SQLite holdsDallas ascollection_failed; its missing receipt remains an appmonitor exception. Nextday's job discovers the current officiallink again.

Private live state: `/Users/juliodominguez/Library/Application Support/WholesaleOS/rehearsal-worker/state`. LaunchAgent labelcom.wholesaleos.rehearsal.collector; logs contain no credentials/contacts. Installationa80887f pushed. No PropStreamcharge/upgrade/APIpurchase; no selleroutreach or productionmutation. Foreclosurecapture and PropStreambrowserhandoff remain unfinished.
