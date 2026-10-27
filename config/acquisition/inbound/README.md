# Hilltop inbound agent review package

Status: DRAFT / NOT DEPLOYED. This package is not a live agent or release approval.

`prompt.en-US.md` is the proposed general prompt. `tools.draft.json` contains the five custom tool definitions for the implemented signed server boundary. The URL uses the reserved `.invalid` domain so the checked-in draft cannot reach a real endpoint. No credentials, provider resources, phone routing, model selection or paid sessions are included. Tool availability and prompt wording do not grant server permissions.

Use the following proposed opening after disclosure review:

> Thank you for calling Hilltop Home Company. I'm an AI assistant. I can collect information about your property for Hilltop to review. How can I help you today?

The prompt and greeting are business copy awaiting approval, not a statement that legal disclosure requirements have been satisfied. Do not add a recording claim until the actual provider and Twilio controls and approved language are verified.

## Review and configuration

1. Finish Phase 1 acceptance and the shared foundation release gates. Complete live acceptance of the locally implemented contact restriction and callback-withdrawal path before activating this agent. All recorded channel scopes must reach the eventual executing channel; postal-address matching remains part of the direct-mail release gate. Confirm an accountable person can review human-help requests and that any separately approved transfer destination exists before adding transfer capability.
2. Verify privacy and retention controls with the provider and Twilio. A storage setting alone does not prove recording/transcription is off. The current receiver drops transcript/recording fields, but the provider may send or process them. Keep live routing off until the PRD's legal and technical controls are approved.
3. Review the prompt, greeting, English voice and model choice. Copy the prompt to the reviewed draft response engine, set the agent as starting speaker, and set the exact approved opening. Do not enable Spanish or multilingual support until the bilingual cases pass. Do not import this folder as an entire provider API payload; it intentionally omits required deployment choices.
4. Replace the `.invalid` URL only in a separately reviewed configuration artifact with the approved HTTPS tools endpoint. Keep POST, the name/call/args wrapper (`args_at_root=false`), JSON parameters, the 15-second per-attempt timeout and zero automatic retries initially. The server has a 10-second database transport timeout. Calibrate actual call latency in QA. A longer timeout is not proof of completion.
5. Keep all five schemas unchanged unless corresponding server validation and contract tests change together. Do not supply database keys in tool headers or dynamic variables. Retell supplies its signature; the server uses separately managed dedicated credentials. Do not attach legacy SMS, email, dial, appointment, offer, transfer, external MCP or knowledge-base tools. A future approved end-call control must also be tested before deployment; this five-tool package does not implement call termination.
6. Response variables map confirmed write receipts into separate intake, callback and human-request revision values. They are convenience state, not authority. Confirm Retell's rendering and numeric behavior. Do not assume dynamic variables survive a failed/interrupting request or authorize a write. Test UUID generation, exact retry retention, missing revision recovery and concurrent tool suppression with the selected model; inability to meet those cases blocks release and requires server-managed request-token/state support.
7. Choose and verify the approved silence reminder and maximum-call-duration settings, inbound-only Twilio routing, exact agent version and receiving number. The SQL route requires those identities and approval references; merely creating an agent does not authorize activation. Keep all acquisition inbound flags and database routes disabled until the controlled acceptance plan is approved.
8. Run the acceptance cases with synthetic information first. Record evidence, reviewer, exact agent version/prompt/tool hashes, result and unresolved findings for every case. The checked-in acceptance file has no passing results. Provider audio simulations or live test calls require their own approved scope and spend; none were executed by building this package.

## Verification boundaries

The shared tool-contract fixtures are validated both against the JSON schemas in the Node/Ajv pipeline and against the actual Python preparation boundary. These detect incompatible arguments and accidental extra selectors. They do not prove conversational behavior, provider schema import, speech quality, correct UUID/revision tracking, recording controls, bilingual behavior, HTTP delivery or approved live activation. Existing HTTP-to-SQL tests cover persistence separately with simulated provider transport.

The server remains stricter than provider JSON schemas for semantic assertions (for example, caller_requested requires requested_by_caller true; restrictions require nonempty unique channel scope for do_not_contact, all alone, or an empty scope for cancel_callback). Model-generated schemas are guidance; server validation remains authoritative. No success claim is allowed from a tool invocation, a static waiting sentence, or a failed request alone.

## Sources checked October 27, 2026

- [Retell custom functions](https://docs.retellai.com/build/single-multi-prompt/custom-function): wrapper, retries, response variables, interruptions and HTTP behavior.
- [Retell's generated Python API types](https://github.com/RetellAI/retell-python-sdk/blob/main/src/retell/types/llm_create_params.py): custom-tool configuration fields.
- [Voice agent API](https://docs.retellai.com/api-references/create-agent): separate agent settings and storage configuration.

This is an additive acquisition-only package. The legacy Retell/SMS prompt and transports are untouched.

The restriction tool additionally requires `ACQUISITION_INBOUND_RESTRICTIONS_ENABLED=true` along with the shared signed-tool gates. Its immutable request has no revision counter. Limited channel opt-outs do not grant permission for other channels. Keep this gate disabled until the same approved inbound acceptance as the other tools; callback and outreach execution remain independently blocked by eligibility.
