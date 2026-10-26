# Acquisition campaign attribution

## Implemented evidence projection

Facebook retrieval already requests and preserves campaign, ad set, ad, form, native lead identity, submission time, organic flag and platform in the immutable seller-intake preparation. The provider-evidence digest is preserved alongside the exact snapshot. This increment exposes that existing evidence; it does not create another campaign store or rewrite historical preparations.

GET `/api/acquisition/workspaces/{workspace}/intakes/{intake}/attribution` reads the intake under the caller's existing workspace RLS and returns metadata only. It does not expose seller answers or consent objects. Unrelated workspace access returns no intake. No service credential is used by the read API.

`facebook-attribution-v1` verifies the snapshot digest, validates identifier strings without numeric/boolean coercion, validates timezone-bearing submission timestamps and normalizes them to UTC. Invalid evidence returns `requires_review` and reason codes; missing evidence remains null with named missing fields. A fully populated metadata response is `available`; this means metadata availability, not completed business attribution or a verified campaign relationship. An organic flag never implies zero acquisition cost. Unknown spend, currency and internal campaign link remain null.

## Ingestion consistency

Before completion, the dedicated Facebook worker validates returned campaign/ad-set/ad identifiers. When the authenticated receipt and provider retrieval both supply the same identifier field, disagreement holds the existing processing job with `IDENTITY_CONFLICT`. Malformed identifiers hold with `INVALID_PROVIDER_DATA`. Missing provider identifiers are not filled from a different source, and no CRM intake is created for a conflict. Existing bounded reviewed recovery remains the correction path. Webhook adgroup identifiers are not assumed to be ad-set identifiers.

This changes neither the saved preparation format/hash nor legacy Facebook/SMS workers. There are no new provider calls, campaign mutations, credentials, schedules or migrations.

## Validation and remaining work

Offline tests cover exact metadata, UTC conversion, missing values, malformed identifiers, unsupported values, digest/identity mismatch, seller-data exclusion, unknown cost, workspace API forwarding and worker holds. Real SQL journeys verify retrieval evidence through the scoped attribution endpoint, cross-workspace denial and conflicting ad identities held before intake creation. Provider transport in these journeys is synthetic; real Meta/PostgREST acceptance remains pending.

The schema mapping designates existing `ad_campaigns` for acquisition attribution. Workspace ownership/enrollment, approved external account-to-campaign matching, multi-touch records, cost ingestion and currency/unit semantics, funnel metrics through qualified intake/offer/contract/close, and reporting UI remain open. Do not match campaigns by name, treat a provider ID as an authorized internal link, infer campaign spend from leads, or claim FB-006 complete from this metadata projection alone.

Compensation: keep acquisition worker/route flags disabled if this version must be held. Historical evidence is unchanged and remains available for later projections. Review identity conflicts using the existing audited recovery procedure; do not overwrite receipts to force a match.
