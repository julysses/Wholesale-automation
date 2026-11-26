# Retell V2 review and controlled retest

Approved October 16, 2026. V2 is published and pinned in production; sending remains OFF. Read-only production connection checks passed. The confirmed-failed prior hold is closed with history preserved. Fresh inquiry and actual send remain pending a later active run within 9 AM–7 PM Central. No automatic future run is scheduled.

Retell dashboard sign-in is complete. Reviewed published V1 of agent agent_193fc3ebd9844b50d54352f200. Its original welcome is a long offer pitch with address/name variables and 24-hour offer/10-day closing language. Functions list contains end_call only. Auto-close inactive chats is OFF. The Retell webhook points to the production WholesaleOS endpoint with a five-second timeout; chat_started, chat_ended, transcript_updated and chat_analyzed are selected. These are conversation events, not Twilio carrier-delivery receipts.

The reviewed published V2 contains this exact 136-character ASCII welcome:

> Hilltop Home Co. (The Jays Dallas, LLC): Thanks for your property inquiry. Julio will follow up. Reply STOP to opt out or HELP for help.

The accompanying prompt prohibits invented commitments, offer/closing deadlines, fabricated CRM success, cold-list outreach, automatic sequences and replies without an actual user message. It preserves automated-assistant disclosure, human follow-up routing and opt-out instructions. Both fields were verified after reload. Welcome-only edits initially did not persist; saving the welcome together with the prompt revision succeeded. Published V1 was not changed.

## Approved bounded acceptance

1. After explicit approval of this exception to the SMS pause, publish the reviewed V2 and pin production to that exact version while sending stays off. Verify the deployment and read-only agent probe before dispatch. Do not assign a number-level native agent or activate recurring workers.
2. Reconcile only provider-confirmed failed test job e2e9231a-27ae-566f-8e3d-30c6096e5013 as terminal without replaying it. Preserve original carrier-undelivered evidence, error 30007, SID, consent and STOP history. Never bypass suppression, cooldowns or an uncertain provider outcome. The accepted/uncertain job ending 0100 and expired job ending 9307 remain untouched.
3. Use one fresh owner website inquiry for the previously confirmed phone ending 0280, with a new explicit consent receipt. Confirm its lead, follow-up assignment and notification receipt. No customer or county record is a test recipient. A fresh receipt is required; do not manufacture consent from an old record.
4. Temporarily enable only the existing owner allowlist and required sending flags. Keep all-consented-form sending, scheduler, county sources, tracing and unrelated reply automation off. Verify the effective deployed configuration; abort if any required guard cannot be verified.
5. During the configured 9 AM–7 PM Central window, invoke the authenticated exact-job endpoint once for that fresh job. Maximum one outbound acknowledgment, no automatic retry. Allow at most $1 of existing SMS/provider credit, no purchase or reload. Re-pause sending immediately afterward, including on failure.
6. Match provider evidence to the exact new job/chat before recording delivery. Obtain actual handset receipt from the owner. No automatic SID association based only on phone/time. Keep any uncertain outcome held.

This plan does not schedule a future run. If approval arrives outside contact hours, prepare safely and execute only when work resumes within the allowed window. No reply/STOP conversation test is included in this one-message exception; that bounded test is a separate launch acceptance step.

## Still required for full launch

Twilio's remediation statement has not been proven by a new delivery test. Native Retell still lacks per-message carrier callbacks; reliable CRM delivery reconciliation remains an engineering gate. Inactive-chat closure and supported inbound/STOP behavior also require verification before general activation. Both website paths need complete acceptance evidence.

Full notice OCR upload approval remains separate and pending. No county collection, trace purchase or OCR upload is authorized by this retest plan.

## Reviewed draft prompt

You are Hilltop Home Co's automated SMS assistant, a DBA of The Jays Dallas, LLC. Identify yourself honestly as an automated assistant when asked; never pretend to be human. Only WholesaleOS may initiate an SMS after a verified, consented property-seller website inquiry. This prompt is not permission to contact anyone.

Use the configured static welcome message exactly once at the beginning of the conversation. Do not invent a sender name, address, price, inspection, offer, appointment, or closing commitment. Do not promise an offer or closing deadline. If required inquiry context is missing or unresolved, stop and require human review.

Keep replies short, honest and limited to the submitted property inquiry. Ask one relevant question at a time. Do not mention foreclosure, delinquency, private financial facts or skip tracing. Do not advise on financing or legal matters, or make offers. Route requested follow-ups to a human; preserve the requested time verbatim and do not say it is booked. Do not claim that a CRM action succeeded without a verified tool result.

On STOP, unsubscribe, cancel, end, quit, revoke, opt out, do not contact, wrong number, or any clear request to stop: end the conversation. Do not persuade or send follow-up marketing. Do not treat your own STOP instructions as an opt-out. WholesaleOS handles suppression and control responses separately. If someone asks for HELP, identify Hilltop Home Co, a DBA of The Jays Dallas, LLC, and direct them to info@thejaysdallas.com.

This agent covers consented property-seller inquiries only. Do not use it for buyer, financing, general-contact or purchased-list outreach. Do not initiate calls, SMS sequences, reminders or additional outreach. Wait for an actual user reply before responding beyond the static welcome message.
