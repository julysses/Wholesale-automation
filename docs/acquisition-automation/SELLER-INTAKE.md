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
