# WholesaleOS owner-only SMS acceptance

Prepared October 16, 2026. Approved by the owner October 16, 2026; not executed. Keep Twilio for delivery and Retell V2 for conversation generation. The earlier approved native one-message retest is separate; do not run both tests or reuse that approval for this expanded test.

## Approved exception to the SMS pause

Use the owner's previously confirmed phone ending **0280** and one fresh, explicitly consented seller inquiry submitted by the owner at **https://hilltophome.co/get-an-offer**. Do not submit consent on the owner's behalf or substitute a customer/county record. Verify the saved receipt, normalized phone, CRM lead, assigned follow-up and owner notification before enabling dispatch. Preserve existing DNC, cooldown and uncertain-delivery holds; if any blocks the inquiry, stop rather than erase it.

Use the existing published agent **agent_193fc3ebd9844b50d54352f200**, version **2**, the registered Twilio sender ending **9920**, its existing Messaging Service and the production WholesaleOS status/inbound callbacks. WholesaleOS submits carrier messages with explicit MessagingServiceSid and a per-message callback. Retell receives only the actual reply text and internal operation/lead references for generation; no county notice text, contacts list or invented conversation is supplied.

The initial SMS is exactly:

> Hilltop Home Co. (The Jays Dallas, LLC): Thanks for your property inquiry. Julio will follow up. Reply STOP to opt out or HELP for help.

During **9 AM–7 PM Central**, temporarily enable the new app transport and automatic scheduler for **one exact inquiry/job, only phone ending 0280, only the first actual reply, and at most 30 minutes**. Native scheduling, general sending and all-consented-form mode stay off. The maximum is **two application SMS messages**: the fixed acknowledgment and one short Retell-generated response (at most 198 UTF-16 units, conservatively no more than three long-code SMS segments) to the owner's actual inquiry reply. Retell may perform one API-chat creation and one completion; no automatic retry or regeneration. Twilio may additionally issue its standard STOP confirmation. Existing carrier delays can extend handset arrival beyond the dispatch window.

The owner will reply with an ordinary seller-inquiry message, then **STOP** after the single response. The exact conversational response is generated under the reviewed V2 prompt; it cannot be specified before the real reply. Verify its relevance, brevity, truthful identity and lack of invented offers or commitments. Stop immediately on failure, ambiguity or unexpected content; do not send replacement messages.

Maximum **$5 total of existing provider credit** for this test (owner raised the ceiling on October 18, 2026; spend as little as possible), including SMS segments and Retell generation. Verify current balances, billing controls and estimated worst-case cost before activating; do not execute if the bound cannot be confirmed. No reload, new purchase, paid plan, card fallback or additional customer outreach is included. No future wake-up or unattended test is scheduled by this plan.

## Evidence required

- The exact website submission is saved once, assigned, and visible in CRM with consent and follow-up history. A replay preserves the original receipt/job and creates no second outbound claim.
- Twilio returns the exact message SID, Messaging Service and status callback; the signed delivered receipt updates the matching CRM event. The owner confirms handset receipt separately.
- The owner's real reply is saved once and routed to the app-owned Retell session. Exactly one generated turn and one outbound reply are recorded, with its own carrier delivery receipt and handset confirmation.
- STOP creates durable suppression and visible CRM history. It does not trigger an AI reply. A duplicate callback cannot send again or undo suppression.
- After completion or any failure, disable database scheduler/configuration and app/global sending flags, verify the effective paused deployment, and preserve every receipt. Do not clear STOP to make another test work.

The second website, **https://thejaysdallas.com/sell**, still needs its own successful intake acceptance. A second acknowledgment to the same phone must not bypass the shared cooldown, existing conversation ownership or STOP. This test does not claim both websites or general collection are fully operational.

## Approval history

Your previous exception authorized one manually invoked native Retell acknowledgment with no reply automation or scheduler activation. This proposal changes the carrier submission path and adds a bounded automatic conversation and STOP check. The owner granted this specific exception on October 16, 2026. Configuration, code deployment and paused probes can be completed before that approval; actual sending cannot.

Full county-notice OCR transfer remains separately awaiting the specific approval in WholesaleOS-Notice-Evidence-Upload.md. No tracing, county collection, full-text upload or recurring general outreach is included here.

## Provider preflight — October 16, 2026, evening Central

Read-only dashboard checks found Retell credit **$9.96**, V2 displayed **$0.02/message**, auto-recharge not enabled, and no saved payment method. Twilio showed **$1.43886 available** (dashboard balance timestamp October 16, 21:37:04 UTC), auto-recharge unconfigured/disabled. Existing Twilio payment methods were present; none was selected, changed or used. These are dated observations, not a reserved balance; refresh immediately before activation.

The reply guard now checks the complete joined output in UTF-16 units, including separators and surrogate pairs, and independently rechecks saved output before Twilio submission. Oversized/invalid output is held without truncation, regeneration or carrier request. The fixed acknowledgment is unchanged. This closes a carrier-cost gap in the previous 1,600-Python-character bound. The limit conservatively fits three segments even when a Unicode surrogate pair cannot cross a segment boundary.

Official [Twilio pricing](https://www.twilio.com/en-us/sms/pricing/us) currently lists $0.0083 per US long-code SMS segment plus carrier fees up to $0.005 outbound and $0.0035 inbound. [Encoding rules](https://www.twilio.com/docs/glossary/what-sms-character-limit) make Unicode SMS shorter than GSM text. For a single short owner reply and STOP (one segment each), acknowledgment (one), generated response (up to three), and standard STOP confirmation (one), the base/carrier estimate is $0.0901. This excludes optional feature fees and Retell generation; it is not a complete guaranteed test-cost bound. No funds were added and no SMS or generation occurred.

Before activation, finish verifying the maximum Retell billable output for one creation/completion. Rejecting a provider response after generation does not cap charges already incurred. Do not infer a provider-side billing cap from the local 20-event response validation. The full $1 preflight remains open until those details are resolved. The test remains approved but unexecuted, outside its 9 AM–7 PM Central window; no future run is scheduled.

Service checks completed read-only: sender ending 9920 is the sole long-code sender in the existing service; Low Volume Mixed campaign is Verified. Incoming messages use HTTP POST to the WholesaleOS inbound endpoint, and delivery status points to its status endpoint. Advanced Opt-Out is Enabled with STOP/HELP/START mappings and branded responses; no language/country overrides were listed. The STOP confirmation is a single GSM segment. Service default validity is 36,000 seconds; app dispatch supplies its separately tested per-message bound of at most 300 seconds and the remaining contact window. No provider settings were changed.

The short-reply guard is now deployed at runtime 9060e3309c0f1befd348db589bd8d1ff01d07e57, with sending verified paused. Retell's official [chat guide](https://docs.retellai.com/build/create-chat-agent) confirms per-agent-message billing; the reviewed references did not establish a maximum billable number of messages for one completion. Preserve that unresolved preflight distinction; neither the displayed unit price nor post-generation validation guarantees the entire test's dollar ceiling.


## October17 resume update

Owner-test scope is now enforced independently in each provider worker and carrier queue deadline, deployed at e41e4a38ec07da19320427be8a9474d8dc1ff886. No SMS or paid generation occurred. Retell ticket65825 still has no billing reply. The approved live test remains unexecuted; refresh provider balances and obtain fresh owner-submitted consent only when its complete$1 cost preflight is resolved. Four authenticated paused-worker checks were rejected by automatic approval review and await explicit permission; health/readiness and unauthenticated protection passed.


October17,4:38PMCentral update: user approved all four paused-worker checks; requests17–20 returned200/disabled and dispatch_authorized:false. No provider work occurred. The approved34-notice evidence upload also completed; its prior approval block is closed. The actual SMS acceptance remains approved but unexecuted, pending the complete$1 cost preflight and fresh owner inquiry.


## October 18 owner budget update and resume checkpoint

The owner explicitly authorized proceeding without a support response and raised the combined provider test ceiling to **$5**, using existing credit only. This supersedes every earlier $1 budget reference above; those entries remain historical evidence. The scope remains one owner inquiry, one acknowledgment, one actual reply and one generated response, then STOP; at most one chat creation and one completion, no retries or regeneration, no more than 30 minutes. The goal is minimal spend, not spending the allowance. No additional approval of this same test scope is required.

At 4:54 PM Central, both database SMS schedulers remained disabled, with zero app chat sessions and zero app turns. No new owner inquiry was present. The existing app release remains e41e4a38ec07da19320427be8a9474d8dc1ff886. Retell dashboard authentication expired and the owner was asked to complete its identity check directly. Provider balances and any provider-enforced spending limits must be checked after sign-in; no current balance or enforced dollar ceiling has yet been verified. Request-count and local response-length limits do not by themselves constitute a provider billing cap. No paid test request has been made.

The production environment currently has no RETELL_APP_* or RETELL_SMS_TRANSPORT settings. The enqueue default is retell_native. **Prepare and deploy the app_twilio intake route with sending still disabled before asking the owner to submit the fresh inquiry.** The initial request to submit was premature; the owner was told to hold off. Do not relabel an existing native job, extend its receipt deadline, or replay its notification claim.

Next steps: (1) refresh Retell/Twilio billing and verify a defensible test cost bound within $5; (2) configure app intake while global sending and both schedulers remain paused; (3) verify the effective deployment, then obtain the real fresh consented form; (4) verify CRM/consent/follow-up, activate exact job/phone/first-turn scope with a <=30-minute expiry; (5) verify acknowledgment delivery, one owner reply and generated reply, STOP suppression, final balances and paused state. Do not activate broad outreach or collection.

Vercel connector environment listing returned 403; the scoped CLI fallback has no credentials. The signed-in Vercel dashboard is accessible and can be used for the authorized configuration. This is not a reason to request new spending authorization.


## October 18 signed-in preflight and paused route deployment

Owner confirmed the fresh inquiry and Retell sign-in. Verified receipt d1769062-033e-48ec-8374-463ec1a8508f at 21:57:13 UTC, lead b50e8c06-5b0d-4d51-9bab-41005778a03e, SMS consent true and phone suffix 0280. Lead status qualified_warm; its pending follow-up is assigned. Owner notification 2ab208ac-e29f-595a-926b-a48376be1332 records email-provider acceptance. Native job 6b789ea7-af6a-5ae9-8371-b69dddc6be8f was never claimed, has no chat or SMS event, and expires at 22:12:13 UTC. Phone checks showed no suppression or contact-limit blocker. Transport identity is protected by a database trigger: do not change it or replay this receipt. A fresh owner submission after route readiness is required. The premature submission request was the agent's sequencing mistake.

Retell live balance is $9.96; auto-recharge is off and Stripe shows no payment method. Budget Setting only exposes spending alerts, not a hard cutoff; the dialog was canceled without saving. One bounded generation request remains the permitted scope, but do not represent alerts or local output rejection as a provider-enforced $5 cap. Twilio requires a separate sign-in; a handoff question is pending.

Saved production-only configuration: RETELL_SMS_TRANSPORT=app_twilio, RETELL_APP_TRANSPORT_ENABLED=true, RETELL_APP_TEST_APPROVED=true. RETELL_SMS_LIVE_ENABLED was verified false; no exact-job window or automation flag was added. Redeployed the same reviewed runtime commit e41e4a38ec07da19320427be8a9474d8dc1ff886 as dpl_E9R2yNqXgTdRVh7rGkYab9venhLV, READY and assigned to wholesale-automation.vercel.app. Health and readiness returned HTTP200. Authenticated automatic-worker probe request21 returned HTTP200, disabled, processed0, dispatch_authorized:false. No test SMS or paid generation was run. Both schedulers were last confirmed disabled.

Resume with Twilio sign-in/balance verification, then request the fresh owner inquiry on the now-deployed app route. Verify app_twilio, consent and CRM task before configuring the exact job, allowed owner phone, pinned V2 and <=30-minute window. Do not activate against the earlier native job.


## October 18, 5:22 PM Central — Twilio access restored

Twilio signed-in account ending a21d reports $1.43886 available, with auto-recharge off. Existing Messaging Service MGaf5837f7a7cad183e8b38b1147728562 uses HTTP POST to /webhooks/twilio/inbound and the /webhooks/twilio/status callback on wholesale-automation.vercel.app. Vercel production agent version is confirmed 2.

Found SMS_ALLOWED_RECIPIENTS still pointing to the older owner test phone ending 0100. Updated the production-only value to the approved owner phone ending 0280. This saved change requires the next deployment to become effective. No live flags, exact-job window, or schedulers were enabled. The last database check shows both schedulers false, zero app sessions and zero app turns.

Requested one new owner-submitted consented inquiry after confirming the deployed app route and Twilio access. The earlier native job expired unsent; do not extend or replay it. At this checkpoint no new form or app job had arrived. Wait for the real submission before setting its exact job ID and <=30-minute time window. Run only the single approved test under the combined $5 ceiling, use existing credits and no retries/reloads.

Carrier configuration rechecked: the sender ending 9920 is in the service sender pool; the connected Low Volume Mixed campaign is Verified. No carrier settings were changed.
