# Twilio integration — October 6, 2026

## Scope and safety
Existing sender +14698049920 and service MGaf5837f7a7cad183e8b38b1147728562. Campaign is in progress, not approved. SMS_LIVE_ENABLED remains false. No seller messages, account purchases or credential rotation authorized by this change.

## Implementation
- Native /webhooks/twilio/inbound and /status verify SDK signatures against configured HTTPS public URL, account SID and message identity; reject invalid requests before writes.
- record_twilio_event is server-only SECURITY INVOKER RPC. Transactionally persists deduplicated events, STOP suppression for every matching lead (including future imports via registry), pauses follow-up, and alerts operators. START never silently clears DNC. Event history preserves late/out-of-order delivery events.
- Outbound client fails closed without credentials/live gate. Requires matching server consent receipt and suppression clearance. Claims a durable outbound record before provider request, persists SID, supplies service SID and signed status callback URL, and never replays an existing attempt.
- Migration created with Supabase CLI and applied explicitly; no historical replay. Rollback SQL test confirmed duplicate receipt idempotence and unknown-phone STOP. anon/authenticated denied RPC, service_role allowed.
- 316 backend tests passed, including callback signature/account/missing-secret/storage failure and outbound claim/consent/suppression cases.

## Remaining execution
- Push, CI, merge and verify deployed endpoints.
- Transfer existing Twilio credential directly to Vercel production secrets; keep out of chat/logs/repo.
- Configure inbound and delivery URLs, Advanced Opt-Out/HELP, and verify saved settings.
- Live signed callback acceptance and actual inbound STOP test with authorized Julio number; outbound delivery must wait for approval.
