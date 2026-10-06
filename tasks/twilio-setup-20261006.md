# Twilio setup checkpoint — October 6, 2026

## Verified in signed-in Twilio Console

- Existing Dallas number: +14698049920, SMS/MMS/voice capable. Both inbound routes still use Twilio demo URLs. No new number needed at this point.
- Standard Customer Profile approved; brand registered as The Jays Dallas, LLC.
- Low Volume Mixed campaign CM81b71bfdf3483a566e6ecf0161c840b9 rejected. Explicit reason: unable to verify campaign Call to Action/opt-in process.
- Existing campaign covers internal management lead alerts only; consent description says internal team, not customers. It links thejaysdallas.com policy pages. Requested Hilltop seller messages are a different stated scope.
- Messaging Service MGaf5837f7a7cad183e8b38b1147728562 exists; number configuration currently shows no selected Messaging Service.
- Repair form available. Final Update requires a correctness attestation and references a vetting fee. No attestation accepted, update submitted, purchase, credential transfer, routing change or SMS performed.

## Required input

Confirm whether Hilltop Home Co. is a DBA/brand of The Jays Dallas, LLC, or a separate legal business. Do not assert that relationship in registration or public policy until confirmed.

## Remaining work

1. Reconcile legal brand and messaging scope. Repair campaign with truthful, verifiable opt-in process; do not describe seller messages as internal alerts.
2. Verify public consent, policy and SMS terms match the actual program. Current Hilltop offer form has an optional unchecked SMS box with sender, rates and STOP; privacy policy mentions service-provider/Meta sharing and lacks an explicit mobile opt-in data exclusion. Confirm actual data practice before changing policy promises.
3. Show concrete corrected registration and any fee/attestation for final approval before resubmitting.
4. Complete native Twilio signature-verified inbound replies/STOP and delivery callbacks before replacing demo URLs. Latest remote production branch fd79915 still has no Twilio route in web/api/webhooks.py. Never route Twilio payloads to the differently signed Launch Control handler.
5. Store authorized Twilio credentials server-side; connect sender to approved campaign/service, deploy and verify callbacks.
6. Controlled delivery/STOP test only with Julio +12147010100. No seller outreach until acceptance passes.

Git pull succeeded for checkpoint branch; remote production changes fetched through fd79915. Existing untracked docs/deployment-vercel 2.md preserved. No application code changed this turn.
