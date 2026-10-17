# Retell generation with WholesaleOS-owned Twilio delivery

Implementation checkpoint: October 16, 2026. **In development; no live route or sender uses this adapter.** The approved one-message owner retest remains on its previously reviewed native Retell V2 route. Do not silently switch its transport, message or spending scope.

## Why this integration is needed

The native Retell BYO Twilio integration cannot currently supply MessagingServiceSid or statusCallback (support ticket65825). Its documented Get Chat response does not provide an exact carrier SID suitable for automatically binding a Twilio outcome to a CRM claim. Matching solely on phone and time is insufficient. Retell will remain the conversation engine; WholesaleOS will own Twilio submission and the exact carrier receipt.

Sources checked October16: [Retell Create Chat](https://docs.retellai.com/api-references/create-chat), [official numeric-version request type](https://github.com/RetellAI/retell-python-sdk/blob/main/src/retell/types/chat_create_params.py), [Retell completion](https://docs.retellai.com/api-references/create-chat-completion), [Get Chat](https://docs.retellai.com/api-references/get-chat), [Twilio Message validity](https://www.twilio.com/docs/messaging/api/message-resource).

## Implemented and locally verified

- `tools/retell_api_chat.py`: fixed generation-only endpoints; numeric agent version; operation/lead metadata binding; exact API-chat/agent/version/metadata verification before every completion; no native SMS operation.
- Actual recipient text is preserved. Empty/oversized input is rejected; no invented greeting or user turn. Initial acknowledgment must be a separately approved fixed message, not a fabricated completion prompt.
- No automatic POST retry or redirect. Timeouts, unexpected statuses, malformed receipts and mismatched sessions require reconciliation. Error text does not include provider bodies or credentials.
- Only bounded agent text with unique message IDs can become a reply candidate. Tool calls/results, injected context, unknown roles, media, duplicate/missing IDs and oversized replies hold the entire turn. Nothing is truncated or treated as delivery proof.
- Shared STOP/HELP/resubscription classification in `tools/sms_controls.py` is used by both the existing native reply router and the new adapter. Controls never reach new generation calls. The carrier/CRM handler remains responsible for suppression and any required control response.
- Creation ignores any startup transcript for delivery. Before generation, Get Chat verifies the saved session is an API chat with the expected internal metadata and pinned release. Never submit a completion to an unverified native SMS chat.

## Required remaining implementation — do not activate early

1. **Durable transport selection and ownership.** Assign one route to each fresh inquiry before claiming it. Preserve existing native jobs. Use the shared recipient advisory lock and ledger so native Retell, direct Twilio and the new transport cannot independently send the same acknowledgment. Do not convert already attempted or uncertain native jobs.
2. **Initial acknowledgment.** Use the approved fixed text as a Twilio message with a durable UUID, MessagingServiceSid and per-message callback. Do not ask Retell to invent a user turn to obtain a greeting. Capture consent/submission identity, finite dispatch deadline and exact content before claiming. Reuse the existing cross-channel limits without creating two claims that block each other.
3. **Persisted conversation and turn queue.** Only authenticated, durably saved carrier inbound receipts qualify. Bind session to lead, phone, sender and original inquiry; enforce one active conversation per recipient and one turn per carrier SID. Store real inbound text/hash. Serialize queued turns; an uncertain creation/completion blocks later turns until reconciled. Never renew expired jobs on retry.
4. **Claimed generation.** Commit a one-shot operation before each Retell POST. Create the API chat only when handling the first genuine reply. Persist session receipt before completion; store resulting message IDs/content and review holds. On a process crash, do not replay a possibly completed provider operation. Generation does not count as delivery. Tool-bearing turns need explicit handling or a human task; the current adapter holds them.
5. **Controlled dispatch.** Recheck current consent, DNC/STOP, allowed recipient, lead state, message age, contact hours and transport ownership immediately before Twilio. One durable claim per generated turn; exact callback-to-claim binding. Existing `SMSClient` claims initial outbound attempts and cannot simply be reused for conversational replies because cooldown/attempt-limit semantics differ. Add a narrowly bound reply claim requiring the actual inbound SID, rather than weakening existing prospecting limits.
6. **Finite carrier queue.** Set per-message validity bounded by the remaining allowed window/deadline. Twilio's current service default is ten hours. Validity limits only Twilio's queue, not downstream carrier latency. Do not retry uncertain sends or fall back to native Retell.
7. **Inbound routing and history.** Persist carrier STOP/reply and human follow-up before any AI action. For the app-owned route, never issue the native Retell TwiML redirect. API-chat webhook messages must not be duplicated as carrier messages or acquire a delivered status from transcript text. Preserve user-visible CRM history and operator tasks.
8. **Acceptance.** Exercise contention, repeated callbacks, callback-before-HTTP-response, timeout-after-provider-acceptance, duplicate/out-of-order inbound turns, changing consent/STOP, contact-window expiry, and mixed transport isolation. Then run a specifically bounded live test with current approval and actual handset evidence. Both website paths and reply/STOP behavior remain required before general launch.

## State and restart instructions

No provider call, live SMS, paid generation, database migration, environment change or new recurring job was executed for this component. Sending remains paused. Do not claim that the delivery-reporting gap is repaired merely because adapter tests pass. Next engineering step is the durable conversation/turn and transport-ownership layer above, followed by actual worker wiring and acceptance. Keep the existing approved native owner retest separate.
