# WholesaleOS owner-only SMS acceptance

Prepared October 16, 2026. Proposed, not executed or authorized yet. Keep Twilio for delivery and Retell V2 for conversation generation. The earlier approved native one-message retest is separate; do not run both tests or reuse that approval for this expanded test.

## Exact proposed exception to the SMS pause

Use the owner's previously confirmed phone ending **0280** and one fresh, explicitly consented seller inquiry submitted by the owner at **https://hilltophome.co/get-an-offer**. Do not submit consent on the owner's behalf or substitute a customer/county record. Verify the saved receipt, normalized phone, CRM lead, assigned follow-up and owner notification before enabling dispatch. Preserve existing DNC, cooldown and uncertain-delivery holds; if any blocks the inquiry, stop rather than erase it.

Use the existing published agent **agent_193fc3ebd9844b50d54352f200**, version **2**, the registered Twilio sender ending **9920**, its existing Messaging Service and the production WholesaleOS status/inbound callbacks. WholesaleOS submits carrier messages with explicit MessagingServiceSid and a per-message callback. Retell receives only the actual reply text and internal operation/lead references for generation; no county notice text, contacts list or invented conversation is supplied.

The initial SMS is exactly:

> Hilltop Home Co. (The Jays Dallas, LLC): Thanks for your property inquiry. Julio will follow up. Reply STOP to opt out or HELP for help.

During **9 AM–7 PM Central**, temporarily enable the new app transport and automatic scheduler for **one exact inquiry/job, only phone ending 0280, only the first actual reply, and at most 30 minutes**. Native scheduling, general sending and all-consented-form mode stay off. The maximum is **two application SMS messages**: the fixed acknowledgment and one short Retell-generated response to the owner's actual inquiry reply. Retell may perform one API-chat creation and one completion; no automatic retry or regeneration. Twilio may additionally issue its standard STOP confirmation. Existing carrier delays can extend handset arrival beyond the dispatch window.

The owner will reply with an ordinary seller-inquiry message, then **STOP** after the single response. The exact conversational response is generated under the reviewed V2 prompt; it cannot be specified before the real reply. Verify its relevance, brevity, truthful identity and lack of invented offers or commitments. Stop immediately on failure, ambiguity or unexpected content; do not send replacement messages.

Maximum **$1 total of existing provider credit** for this test, including SMS segments and Retell generation. Verify current balances, billing controls and estimated worst-case cost before activating; do not execute if the bound cannot be confirmed. No reload, new purchase, paid plan, card fallback or additional customer outreach is included. No future wake-up or unattended test is scheduled by this plan.

## Evidence required

- The exact website submission is saved once, assigned, and visible in CRM with consent and follow-up history. A replay preserves the original receipt/job and creates no second outbound claim.
- Twilio returns the exact message SID, Messaging Service and status callback; the signed delivered receipt updates the matching CRM event. The owner confirms handset receipt separately.
- The owner's real reply is saved once and routed to the app-owned Retell session. Exactly one generated turn and one outbound reply are recorded, with its own carrier delivery receipt and handset confirmation.
- STOP creates durable suppression and visible CRM history. It does not trigger an AI reply. A duplicate callback cannot send again or undo suppression.
- After completion or any failure, disable database scheduler/configuration and app/global sending flags, verify the effective paused deployment, and preserve every receipt. Do not clear STOP to make another test work.

The second website, **https://thejaysdallas.com/sell**, still needs its own successful intake acceptance. A second acknowledgment to the same phone must not bypass the shared cooldown, existing conversation ownership or STOP. This test does not claim both websites or general collection are fully operational.

## Why a new approval is necessary

Your previous exception authorized one manually invoked native Retell acknowledgment with no reply automation or scheduler activation. This proposal changes the carrier submission path and adds a bounded automatic conversation and STOP check. It therefore needs a specific exception to your still-active SMS pause. Configuration, code deployment and paused probes can be completed before that approval; actual sending cannot.

Full county-notice OCR transfer remains separately awaiting the specific approval in WholesaleOS-Notice-Evidence-Upload.md. No tracing, county collection, full-text upload or recurring general outreach is included here.
