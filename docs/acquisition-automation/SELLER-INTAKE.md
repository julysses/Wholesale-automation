# Seller intake preparation

`tools/acquisition_intake.py` implements a pure, versioned preparation step for an authorized native Facebook lead retrieval. It is not yet connected to ingestion or persistence. It has no provider, CRM, offer, contact or outreach side effects.

The response lead ID must match the expected receipt identity. Field aliases are normalized while every original field/value occurrence is retained. Conflicting aliases, duplicate answers and multi-select values cannot silently overwrite one another. Bounds apply to names, values, field counts and total UTF-8 answer size. Original provider payload storage and provider authenticity remain the receiver/worker's responsibility.

Prices use decimal arithmetic and explicit US-dollar syntax. Blank remains missing; explicit zero stays zero. Ranges, suffixes such as `150k`, negatives, malformed grouping, excessive precision and non-US separators remain unknown and require review. No market estimate is introduced.

Missing address, city/state, authority assertion, condition, timeline, motivation, asking price or contact produces incomplete intake unless conflicting/ambiguous answers need review. Explicit denial of authority or interest produces unqualified intake when answers are unambiguous. Complete answers require canonical property review: a seller's free-text county/address and authority assertion are not verified ownership or territory evidence. The later canonical resolver must support qualified and duplicate outcomes using documented matching evidence. A phone match must never merge properties.

Consent/custom fields remain source evidence; this classifier never emits channel permission, offer approval or execution authorization. Permission extraction uses the dedicated evidence service and form configuration.

## Persistence inspection and next implementation

The catalog's existing `qualification_results` requires a non-null call_id, defaults legacy classification to COLD, and permits only HOT/WARM/COLD. It has call-specific timeline/condition/occupancy/sentiment constraints, a transcript foreign key, and a HOT notification trigger in migration 005. Reusing it for native intakes requires an explicit additive channel-neutral extension or the thin intake relation anticipated in SCHEMA-MAPPING.md, without inventing a call or triggering call automation.

`workspace_leads.bound_by` is a non-null profile reference. A provider system writer cannot truthfully pretend to be an interactive user. Add explicit integration provenance/system binding semantics while retaining existing user binding constraints and audit history. New leads must be bound in the same transaction, never left visible as unscoped legacy records. Missing property information needs explicit intake state rather than fabricated addresses treated as facts.

Next: channel-neutral immutable intake relation over existing receipts, canonical lead creation/resolution, attribution links, atomic current-lease completion, read model and operator review. Include rollback-on-failure, retry, cross-tenant, no-phone-only-merge and no-legacy-trigger tests. Current pure tests do not prove database ingestion or any release gate.

## Atomic persistence implementation

`20261026162924_acquisition_seller_intakes.sql` adds the thin `seller_intakes` relation over existing canonical leads and webhook receipts. It leaves legacy call qualification tables/triggers intact. The immutable record preserves the versioned preparation, source receipt, classification, hash and normalization warnings. Workspace owner/admin/operator reads are allowed through membership-based RLS; caller/agency/browser writes and raw service mutations are denied.

Canonical workspace binding now has exactly one origin: an existing human `bound_by`, or an integration reference constrained to the same workspace. Existing user-bound records remain valid. The provider writer never impersonates a user.

`complete_facebook_acquisition_intake` checks global activation, integration provider/enabled state, active workspace, receipt lead/form identity, lease token/state/expiry and payload retention. It accepts only the current preparation version and preliminary incomplete/unqualified/review classifications, with all verification/permission/execution assertions false. It stores a new lead and binding, intake, completion and audit in one transaction. No same-phone or address-only matching occurs. Repeating the same completed input/token returns the same IDs; conflicting input fails. A downstream insert failure rolls back all four writes, leaving the lease available for retry.

Missing address/city are empty source values, not invented facts; missing state and price remain null. Invalid phone/email values stay in intake evidence with normalization warnings; canonical contact columns receive only normalized values. No contact permission is created. SMS/email sequences are false, AI calling is paused, and the new source has a retention-review hold rather than legacy unattended cleanup. The final-order retention trigger is tested alongside the inspected legacy retention function. CRM/intake evidence retention is still a policy/workflow requirement before release; the inbox's raw-body expiry does not purge these separate business records.

This first writer creates one lead per distinct native event. Cross-inquiry canonical owner/property resolution, repeat-inquiry linking, qualified/duplicate transitions, campaigns/multi-touch attribution and the operator intake interface remain incomplete. The source is `facebook_acquisition`; channel is `facebook_lead_ad`. No fabricated call ID, HOT notification, property match or ownership verification is generated. No HTTP/provider worker wiring is live.

Compensation: disable the integration/worker and keep stored evidence. Do not delete intakes or reverse the additive migration. Release remains blocked pending canonical identity workflow, retention policy, full-schema rehearsal and actual end-to-end ingestion acceptance.
