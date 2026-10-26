# Seller intake preparation

`tools/acquisition_intake.py` implements a pure, versioned preparation step for an authorized native Facebook lead retrieval. The acquisition worker now calls it before atomic intake persistence. The pure preparation function itself has no provider, CRM, offer, contact or outreach side effects.

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

This first writer creates one lead per distinct native event. Cross-inquiry canonical owner/property resolution, repeat-inquiry linking, qualified/duplicate transitions, campaigns/multi-touch attribution and the operator intake interface remain incomplete. The source is `facebook_acquisition`; channel is `facebook_lead_ad`. No fabricated call ID, HOT notification, property match or ownership verification is generated. The HTTP receiver and retrieval worker are implemented behind disabled-by-default gates; no production wiring is activated.

Compensation: disable the integration/worker and keep stored evidence. Do not delete intakes or reverse the additive migration. Release remains blocked pending canonical identity workflow, retention policy, full-schema rehearsal and actual end-to-end ingestion acceptance.

### Retrieved consent evidence

The preparer now preserves selected provider response fields in `provider_evidence`, including full field-data and custom-disclaimer arrays, with a deterministic JSON hash. Missing, empty and declined disclaimer responses are distinct and remain unreviewed. A deep copy prevents later mutation of the source dictionary from rewriting the prepared snapshot. Both response and prepared snapshot sizes are bounded before persistence. This does not replace form-language version review or create contact_permissions records.

## Workspace identity candidate lookup

`20261026171817_acquisition_intake_candidates.sql` and GET `/api/acquisition/workspaces/{workspace}/intakes/{intake}/candidates?limit=20` add a read-only comparison step over the original immutable intake answers and existing workspace-bound CRM leads. Actual owner/admin/operator role and current session are required. Unscoped legacy records and other workspaces are not searched; caller, service-role and unrelated users cannot use the function. County property metadata is returned only through an existing workspace property/lead binding.

The returned candidates distinguish `EXACT_ADDRESS_TEXT` (address, city and state all match after case/whitespace normalization, with Texas/TX equivalence) from `CONTACT_ONLY`. Phone and email signals reuse the strict contact normalizer; extensions and ambiguous numbers do not match. Punctuation, street abbreviations, unit differences, missing fields and seller assertions are not guessed into verified identity. Contact-only results can identify possible repeat inquiries but never authorize merging properties or owners. Original phone/email values are not returned in candidate results.

Results have deterministic address-first ordering, an explicit truncation flag, a maximum of 50 candidates and a candidate snapshot hash. The hash is comparison evidence, not an authorization token; a later write must reread current evidence and authority. Existing intake classification, CRM rows, permissions, bindings and audit history are unchanged by discovery. The original intake hash is returned alongside the candidate hash. No qualified/duplicate determination has been implemented yet.

Next: append-only reviewed resolution, canonical property verification, repeat-inquiry associations, correction/revocation history and a reviewer interface. A result outside the initial Dallas/Collin territory must remain subject to explicit territory review. County-wide/unbound search requires its own authorized enrollment workflow; no global directory access is introduced here. Large-workspace performance and search indexes remain to be measured before scale-up.

Compensation: disable the candidate API feature with the existing acquisition application gate. Keep the additive functions and all historical records; no data rollback is required because discovery writes nothing. Tests cover exact-address versus same-phone/unit mismatch, missing fields, malformed contacts, cross-tenant/session/role denial, bounded ordering, and an actual Facebook intake-to-candidate journey on disposable PostgreSQL. Real PostgREST/provider acceptance is still separate.

## Reviewed identity links and corrections

`20261026173422_acquisition_intake_identity_reviews.sql` adds immutable identity-review history over existing intakes and canonical workspace property bindings. It does not rewrite a lead, property, owner assertion, original intake classification or receipt. The new table uses composite tenant/identity foreign keys, actual owner/admin/operator read RLS, no direct application/service writes or truncate, and append-only audit events.

The state endpoint is GET `/api/acquisition/workspaces/{workspace}/intakes/{intake}/identity-state?target={canonical-lead}`. It returns the original preparation hash, review sequence, target snapshot/hash, latest review and whether that reviewed link is currently valid. The target must already have a canonical property-to-lead binding in the same workspace. Self-links and unbound/global/cross-workspace targets are denied. The target snapshot includes county parcel/address/unit evidence and a normalized contact fingerprint, not raw contact values. A candidate match does not establish any of these facts as legally verified.

POST `.../identity-reviews` accepts a stable request UUID, expected sequence, original preparation hash and one of:

- `link_property`: documented parcel or independently verified-address evidence, target snapshot hash and a review note.
- `repeat_inquiry`: the same property evidence plus a separate seller identity evidence reference. A matching telephone number is insufficient evidence by itself.
- `revoke`: a correction note with no target or new identity assertions. Earlier decisions remain available through paginated GET `.../identity-reviews?before={sequence}&limit=20`.

An owner/admin with MFA and a currently approved live session must approve. Activation, workspace, membership/session, source intake, target binding, CRM lead and county property locks protect the initial decision through commit. Exact retries return the original review; changed requests conflict, and stale sequence/source/target evidence is rejected. A later documented review supersedes the previous decision without erasing it. State reads invalidate links after reviewed target evidence changes, reviewer membership changes/revocation, profile suspension or activation disable. Revocation remains available while global activation is disabled (workspace and reviewer authority still required).

These are human-reviewed associations, not title verification, consent grants, qualified-lead determinations or authority to send offers. Every state response explicitly retains ownership verification, permission and outreach as false. Downstream underwriting/qualification still needs to consume a fresh valid link under its own authorization checks; this release does not silently route existing calculations or CRM tasks to another lead. The reviewer UI and qualification/duplicate classification transitions are next.

Compensation: disable linking through the existing activation gate, preserve all history, and revoke incorrect associations with a new review. Do not drop tables or reverse data migrations. Tests cover concurrent exact requests, stale sequences/evidence, non-merging, RLS, service-write denial, MFA/live sessions, missing independent evidence, changed reviewer authority, disabled-gate revocation and the API-to-real-SQL journey.

## Operator intake review interface

The default-off acquisition dashboard now includes an on-demand Seller intake identity review panel. Its UUID-cursor list and detail APIs use the existing authenticated store and seller_intakes RLS; another workspace receives no detail. The queue preserves the original classification. Selected evidence displays submitted answers, missing fields, normalization/review flags, scoped candidates, exact target snapshots, current-link validity and paginated history.

Only current owner/admin membership exposes enabled decision controls, while the server remains authoritative for MFA, session, activation, evidence and concurrency checks. Linking requires independent property evidence; repeat inquiries require separate seller evidence; revocation sends no target assertions. An explicit acknowledgment and fresh state/hash check precede initial submission. Unknown outcomes retain the stable UUID/body, freeze edits and provide exact-request reconciliation. Queue refresh does not unmount the pending decision. Workspace/account changes reset the review scope. No automatic retries, property merging, qualification transition, contact or offer transmission is added.

Browser QA used only the synthetic local fixture: recorded a link, verified current state/history, revoked it and verified both historical entries with no current link; console errors were empty. Evidence: `evidence/2026-10-26-intake-review-browser.png`. Real PostgREST/JWT/browser integration and mobile QA remain separate acceptance items. Fresh reviewed-link consumption by underwriting and final qualification remains incomplete.
