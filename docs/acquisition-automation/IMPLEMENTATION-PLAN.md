# WholesaleOS acquisition automation — implementation plan

PRD version: 1.0 · PRD date: October 25, 2026 · Business: Hilltop Home Company

Status: implementation in progress; see PROGRESS.md for verified increments and open release gates. This plan translates the user-provided PRD into work packages. The complete PRD supplied in the conversation remains controlling; this document is not a verbatim copy or a claim of implementation.

## Objective and boundaries

Build a shared acquisition system for Dallas and Collin Counties that sources distressed properties, captures seller interest, qualifies opportunities, prepares investment scenarios, and supports principal purchases or legally permitted assignments. Hilltop acts for its own account and does not provide brokerage, marketing, or other services to sellers.

Use existing authentication, workspace membership, roles, audit logging, deployment infrastructure, CRM, and county ingestion. Preserve production and paused SMS recovery. No production migrations, funded/published advertising, live outreach, mail fulfillment, binding offers, or contract execution are authorized by this planning checkpoint.

## Ordered delivery gates

| Gate | Deliverable | Evidence required before activation |
| --- | --- | --- |
| 0 | Baseline inventory and shared foundation | Entity mapping, additive migration rehearsal with representative records, tenant/role isolation, immutable audit and idempotency tests; eligibility fails closed |
| 1 | Facebook lead-generation integration | Approved test lead through verified webhook, durable ingestion, intake and attribution; replay, incomplete intake, credential expiry, opt-out and isolation tests; SMS schedulers unaffected |
| 2 | Inbound AI calling and direct mail | Inbound-only seller intake, reconciliation and human escalation tests; approved disclosures; vendor sandbox/proof validation; separate approval for actual mail |
| 3 | Automated proposed mail batches and online offer requests | Submission → underwriting → human approval → fulfillment reconciliation end to end; scheduler initially proposes batches only |
| 4 | Virtual acquisition caller | Limited human caller role, MFA, assignments, intentional click-to-call and fresh server-side eligibility; counsel-approved outbound policy |
| 5 | Agency calling pilot | Restricted cohorts, documented training/contractual controls, suspension and revocation tests, verified pilot logs before scaling |

These are sequential activation gates. All channels share identity, permissions, eligibility, pipeline, underwriting, and reporting. Building shared components does not authorize activating later phases.

## Work package 0 — inspect before SQL (MIG-001–005)

1. Verify the authoritative production code revision, deployed schema, migration ledger, auth/role model, worker/cron flags and provider configuration using bounded read-only checks. Record observations with timestamps. Do not treat the repository default branch as proof of deployed state.
2. Inventory tables, columns, constraints, indexes, triggers, functions, RLS policies, storage access, tenancy joins and existing webhook handlers. Inspect migration history and detect duplicate/colliding migrations.
3. Produce `SCHEMA-MAPPING.md`: logical entity, existing equivalent, proposed extension, workspace owner, foreign keys, uniqueness, RLS/role policy, migration and compensation procedure. Every mapping remains unverified until inspected.
4. Design forward-only additive migrations. Reuse existing equivalents; do not replay historical migrations. Document compensation and compatibility with old application code.
5. Rehearse on a disposable database with representative historical records. Prove membership/role RLS, cross-workspace foreign-key integrity, record preservation, idempotency and rollback/compensation behavior. Production migration requires separate approval.

Required logical entities to map:

| Entity | Required logical fields |
| --- | --- |
| acquisition_campaigns | id, workspace_id, channel, status, budget_cents, external_id |
| campaign_events | campaign_id, event_type, external_event_id, payload_ref |
| lead_sources | lead_id, campaign_id, source_type, utm_data |
| contact_points | owner_id, type, normalized_value, verification_status |
| contact_permissions | contact_point_id, channel, scope, evidence_ref, expires_at |
| contact_suppressions | contact_point_id, channel, reason, created_at |
| eligibility_decisions | contact_point_id, channel, decision, reason_codes, policy_version, checked_at |
| outreach_attempts | lead_id, channel, actor_id, result, provider_id |
| mail_jobs | lead_id, template_id, vendor_id, status, sent_at |
| seller_intakes | lead_id, property_id, motivation, timeline, asking_price |
| underwriting_scenarios | property_id, strategy, inputs, outputs, version |
| acquisition_offers | scenario_id, amount, status, approved_by, sent_at |
| acquisition_contracts | property_id, seller_id, contract_status, assignment_allowed, closing_date |
| buyer_profiles | buyer_id, workspace_id, buy_box, verification_status |
| disposition_records | contract_id, exit_type, buyer_id, assignment_fee, status |
| integration_events | provider, external_event_id, event_type, processed_at |

Add enforceable workspace ownership, evidence/provenance, timestamps and version fields where needed. Tables exposed to clients require RLS based on actual membership and authorized role. A service-role bypass must not bypass application authorization.

## Work package 1 — shared foundation

- Normalize contacts; preserve verification, source, exact consent language/version, affirmative selections, scope, timestamps, expiry and revocation. Apply suppressions across matching identities without merging unrelated properties based on telephone alone.
- Implement `POST /internal/outreach/eligibility/evaluate` using the PRD request/response contract. Authenticate the caller and derive/validate workspace authority server-side. Return decision, reason codes, policy version, decision ID, expiry and permitted actions.
- Until the applicable policy is approved, return REVIEW with `LEGAL_POLICY_NOT_APPROVED` and no permitted actions. BLOCK and REVIEW prevent execution. Missing policy, stale decisions and unavailable checks must never default to ALLOW.
- Evaluate channel, purpose, actor, contact evidence, suppression/DNC policy, exceptions, local hours and timezone. Human voice, AI voice, prerecorded messages, SMS and direct mail are distinct. Re-evaluate immediately before execution; client overrides are prohibited.
- Preserve exact decision inputs/results and counsel-reviewed exceptions. Texas counsel must approve principal-buyer and assignment-specific policy before live outbound calling.
- Use durable event receipt, transactional processing and unique provider-event identities. Test retries, concurrent delivery, out-of-order events, crashes and vendor acknowledgement uncertainty. Never blindly retry an uncertain external send or fulfillment.
- Store raw sensitive payloads behind access controls and retention limits. Audit contact decisions, underwriting versions, approvals, contract transitions and disposition approvals immutably.

## Work package 2 — Facebook first (FB-001–006)

Verify current official Meta API documentation and permissions at implementation time. Capture campaign/ad set/ad/form/lead IDs, submission time, contact/address fields and form-level consent evidence. Verify signatures before accepting events; durably persist and acknowledge promptly, then retrieve authorized details asynchronously with secure token handling.

Resolve owners/properties using verified identifiers; create intake classified as qualified, incomplete, duplicate, unqualified or human review. Record multi-touch attribution through acquisition cost, qualified lead, offer, contract and closed transaction. Generic form submission does not authorize unrestricted messaging or outbound AI voice.

Acceptance matrix: one approved lead creates one CRM record; replay produces no duplicates; missing property data enters incomplete workflow; invalid signatures reject; expired credentials produce an actionable alert; form/channel permissions persist; opt-outs block prohibited follow-up; workspace isolation holds; campaign publication/funding remains approval-controlled. Verify production SMS schedules remain paused.

## Work package 3 — inbound voice and mail (RET-001–006; MAIL-001–006)

Deploy inbound-only Retell behind the approved Twilio routing. Identify Hilltop and disclose the AI assistant. Recording/transcription stay disabled until legal and technical controls are approved. Authenticated server tools support lookup, lead/intake updates, callback requests and escalation. Tools cannot approve offers or execute contracts.

Capture address, ownership, condition, timeline and price expectations; match/create intake and prepare a preliminary scenario. Test interruptions, silence, unsupported languages, human requests, failed transfers, authentic callbacks and completion/failure reconciliation. English/Spanish support requires bilingual QA.

Prepare mail campaigns from scored Dallas/Collin properties. Verify addresses, handle deceased owners, deduplicate, apply preferences/legal rules and per-property frequency caps. Version templates, enforce budgets and unique tracking identifiers, and direct sellers to tracked inbound numbers or landing pages. Select a vendor adapter supporting idempotent job creation, statuses and reconciliation. Use sandbox/proofs before separately approved fulfillment.

## Work package 4 — portal and proposed mail automation (WEB-001–006)

Collect address, ownership/authority, condition, occupancy, timeline and asking price. Confirm Hilltop is reviewing the property and route the proposed offer to owner approval. Validate addresses, prevent private-owner enumeration, rate-limit, detect bots/abuse, and preserve consent versions/selections. Default to request-an-offer; show estimates only after explicit approval. Keep internal MAO/profit assumptions private. Final written offers require authorized approval and approved templates.

Daily automation may score eligible properties and prepare proposed mail batches. Fulfillment initially requires approval; any later budget-capped automatic policy requires explicit authorization. Enforce budgets and frequency caps again at execution.

## Work package 5 — human caller (CALL-001–008)

Provide assigned-lead views, property summaries, suggested questions, intake forms and manual Twilio click-to-call. One deliberate action initiates one permitted call after a fresh server-side eligibility check. Record no answer, wrong number, not interested, interested, callback, offer requested and do-not-contact outcomes; follow-up tasks remain eligibility-controlled.

The `acquisition_caller` role requires MFA, audit, revocable sessions and sensitive-data restrictions. Prohibit binding-offer approvals, bulk owner exports, policy edits and unrelated-workspace access. Report productivity, conversions, callbacks and quality. This is a human contractor/employee role, not an AI agent.

## Work package 6 — agency (AGENCY-001–006)

Add limited caller and agency-manager roles restricted to assigned eligible cohorts. Enforce export and integration restrictions; prohibit unsanctioned dialers, AI voice campaigns, purchased third-party lists and separate messaging systems. Require contractual obligations, training, audits, incident reporting and subcontractor controls. Attribute agency performance separately. Test immediate suspension, credential revocation and reassignment before the controlled pilot and any expansion.

## Shared underwriting (UW-001–008)

Support fix-and-flip, rental, development and assignment scenarios with base/downside/upside cases. Preserve provenance, assumptions, calculation versions, confidence and historical offers. Missing market inputs remain missing or explicitly estimated; never silently zero-fill them.

For flips: MAO = ARV − repairs − other costs − target profit. Break out acquisition closing, liens, repair contingency, financing, interest, holding, selling and other applicable costs without double-counting. Capture property characteristics, comparable sales, rent, timing, leverage and return assumptions. Report title, lien, occupancy, valuation and repair uncertainties, proposed ranges and MAO.

For assignments: gross fee = end-buyer price − contract price; track additional costs and net proceeds separately and independently validate buyer economics. AI must not state unverified estimates as facts. Human approval is required before a binding purchase offer is transmitted.

## Shared contract and disposition controls (DISP-001–010)

Controlled lifecycle: draft → pending_signature → executed → title_review → disposition_review → assigned_or_direct_close → closed. Include cancelled, expired and disputed terminal/exception states with explicitly authorized transitions.

Store executed documents, effective date, earnest money, inspection/closing deadlines and assignment provisions. Distinguish direct principal purchase from assignment. Disposition begins only with an enforceable contract and reviewed assignment basis; require title/contract review before marketing. Maintain verified buyer buy boxes by geography, type, price, renovation and closing capacity; rank matches and prepare a human-reviewable package that accurately describes contractual interest. Enforce required seller/assignee disclosures under reviewed Texas policy. Do not represent contractual interest as legal title. Track agreements, deposits, milestones, gross fee, expenses and net proceeds; human approval controls assignments and closing-structure changes.

## Open decisions and evidence

Select approved Meta app/forms/test identities and secret-storage path; inbound number/Retell configuration; counsel policy owner; retention periods; mail vendor/templates/budgets/frequency limits; market-data providers and confidence thresholds; offer approval roles/limits; contract/disclosure templates and title-review workflow. These are implementation dependencies, not reasons to stop read-only inventory or isolated foundation work.

Every gate must record test command, fixture scope, expected/actual result, artifact path, commit, environment, approver and activation status in `PROGRESS.md`. Check deployed state independently of CI success. Codex pulls before updates and pushes each completed update; GPT Work maintains planning/progress documents.
