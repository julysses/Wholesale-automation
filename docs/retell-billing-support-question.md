# Retell support follow-up — sent

Destination: existing Retell support ticket 65825.

Sent October 16, 2026, evening Central after explicit user approval. Posted message and cleared composer verified; reply pending. No settings, billing or test action requested.

Thank you for confirming the native BYO Twilio SMS behavior. We are preparing a tightly bounded owner test using Retell API chat for generation and our application for Twilio delivery.

The test makes exactly one create-chat request and one create-chat-completion request, with no retries, using a published single-prompt agent whose only tool is end_call. The dashboard displays $0.02 per message. We need to keep the entire test below $1 of existing credit.

Could you confirm:
1. Is one create-chat-completion request billed as one AI message, or can it produce multiple separately billed messages? What is the maximum for this setup?
2. Are the initial welcome message, auto-close message, end_call tool activity and post-chat analysis billed separately for API chats?
3. Is there a supported per-chat message/token/cost limit we can set before generation? If not, what conservative maximum cost should we allow for this single creation and completion?

Please do not change our settings, enable SMS, run tests, add credit or activate billing. We only need clarification of the billing behavior.

No phone numbers, property records, credentials or message transcripts are included in this message.
