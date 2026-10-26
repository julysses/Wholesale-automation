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

The schema mapping designates existing `ad_campaigns` for acquisition attribution. Workspace-owned draft creation is now implemented (see CAMPAIGN-ISOLATION.md); existing campaign enrollment, approved external account-to-campaign matching, multi-touch records, cost ingestion and currency/unit semantics, funnel metrics through qualified intake/offer/contract/close, and reporting UI remain open. Do not match campaigns by name, treat a provider ID as an authorized internal link, infer campaign spend from leads, or claim FB-006 complete from this metadata projection alone.

Compensation: keep acquisition worker/route flags disabled if this version must be held. Historical evidence is unchanged and remains available for later projections. Review identity conflicts using the existing audited recovery procedure; do not overwrite receipts to force a match.

## Persistent original touches and reviewed snapshots

Migration `20261026221434_acquisition_lead_sources.sql` adds the missing multi-touch association foundation over existing canonical CRM records. `acquisition_lead_sources` uses the intake ID as its stable source ID, references the original workspace lead, provider receipt and integration, and records preparation hash/version plus typed external lead/form/campaign/ad-set/ad identifiers. There is no unique constraint on lead ID: multiple source touches can be retained. Current native Facebook intake still creates a separate inquiry lead per receipt; canonical-property/repeat-inquiry rollups must use reviewed identity links and are not implemented by this relation alone.

An AFTER INSERT intake trigger creates the immutable source and its audit in the same transaction. Failed projection rolls back intake and CRM creation; successful retries cannot duplicate source/audit. The migration backfills existing acquisition intake evidence without creating new leads, changing intake answers, or rewriting legacy source/campaign fields. No seller answers, phone numbers or email addresses are copied into this metadata relation. Invalid/missing provider IDs are null; source receipt identity remains original. `submitted_at_raw` is preserved raw evidence, not a validated timestamp; use validated UTC projection before date-based reporting. Native-form UTM is unknown/null, not an invented empty attribution claim.

`acquisition_source_campaign_reviews` preserves the exact campaign-link review used for a source snapshot. The controlled capture RPC derives campaign and provenance server-side from source and reviewed link; clients supply only a request UUID and exact review UUID. Live owner/admin/operator access is required. It shares the campaign review's external-ID lock and locks workspace, integration, reviewer/profile and campaign through commit. A stale, revoked, mismatched or unapproved link cannot produce a new capture. Exact retries can confirm historical captures; that does not establish current attribution. Unique source/review pairs and immutable audits prevent duplicate or overwritten snapshots.

API contracts:

- GET `/workspaces/{workspace}/leads/{lead}/sources`: bounded UUID-cursor pages of original-lead source metadata, user-JWT/RLS scoped.
- POST `/workspaces/{workspace}/intakes/{intake}/source-campaign-reviews`: `{id, link_review_id}` to capture an exact current reviewed association; no client-supplied campaign/account/actor.
- GET on the capture path: bounded history plus `attribution_current`, derived by comparing each captured review with current campaign-link authority after reading history. This is a reporting snapshot, not transaction authority. All results deny execution authority.

Capture is an explicit reviewed action; the dashboard connection is documented below. New intake creation automatically records only the original source. There is no implicit campaign match or historical canonical-lead merge. Full multi-touch reporting additionally needs canonical identity rollups, capture orchestration, cost coverage/currency, campaign events and deduplicated funnel stages.

Both exposed tables enable RLS and grant authenticated scoped SELECT only; application/service roles have no direct mutation/truncate grants. Composite workspace foreign keys and private DEFINER/public INVOKER capture follow existing foundation controls. Compensation keeps gates disabled and preserves source/review/audit history; incorrect campaign attribution is revoked through the existing review workflow rather than deleted. No production migration has run. Full populated production-schema upgrade, retention-policy review and actual PostgREST acceptance remain release gates.

## Source capture dashboard

`SourceAttribution.tsx` now connects explicit capture and history to the campaign-review panel. Owner/admin/operator access permits preserving an existing reviewed link; campaign linking itself still requires owner/admin/MFA. The panel displays the exact campaign and review for each snapshot and labels current versus historical attribution without representing it as outreach or spending permission.

The capture-history API now returns workspace/source/preparation context, the current link review/campaign and a separate `current_capture` lookup independent of the requested history page. The UI can therefore prevent duplicate capture even when the current snapshot is elsewhere in the paginated history. Fresh preflight compares review/campaign/preparation identity and existing capture before sending. Database locks remain authoritative under concurrency.

Unknown capture replies retain the exact UUID/review and expected response context in user/workspace/intake-keyed tab session storage. Reload restores reconciliation; a later rejected retry cannot discard the earlier unknown request. Parent campaign and intake edits are locked while unresolved. Successful historical retry confirms only the saved snapshot, then refreshes current status. Tab closure clears browser recovery storage, requiring ledger reconciliation before recreating an uncertain capture.

Rendered synthetic QA on October 26 covered draft creation, campaign ownership review, capture, and revocation preserving a historical snapshot, with no console errors. Screenshot: `evidence/2026-10-26-source-attribution-browser.jpg`. Component/API/integrated SQL tests additionally cover revoked authority, stale preflight, wrong-tenant responses and cursor-independent current capture. Live provider/PostgREST and mobile acceptance are still pending. The canonical-property source endpoint is described below; its dashboard view and cost/funnel reporting remain open.


## Canonical property source reporting

Migration `20261026223054_acquisition_property_source_touches.sql` adds a read-only RPC over the existing immutable sources and identity/campaign reviews. GET `/api/acquisition/workspaces/{workspace}/leads/{lead}/source-touches?after={uuid}&limit=20` requires a canonical property-bound lead and live owner/admin/operator access. Both canonical lead and underlying property must agree with the workspace binding. User JWT forwarding and the existing role helper remain authoritative; anonymous, service-role and limited caller access are denied.

Original lead sources are included directly. Other inquiries appear only through their currently valid reviewed property or repeat-inquiry association to this exact lead/property. Revoked, replaced and stale identity links are excluded. Original lead/source IDs remain separate, and each touch identifies its association type and exact identity review. This is inquiry-touch evidence, not verified ownership, unique sellers or conversion counts.

Current campaign attribution requires both a current campaign-link review and a snapshot captured against that exact review. Otherwise the response retains any latest historical capture separately and leaves current campaign null. Missing campaign evidence does not discard an otherwise eligible property touch. Seller answers and contact details are not returned.

The UUID cursor advances across bounded candidate pages, including excluded candidates. An empty `items` page may still have `next_after`; consumers must follow that cursor rather than infer completion from an empty page. Limits are 1–50. `scanned_count` and `excluded_count` describe only this candidate page; `totals_available` is false. Each request is a reporting snapshot, and separate pages do not share a database transaction. Refresh rather than treating accumulated pages as an immutable total during concurrent review changes. All ownership, contact-permission and execution authority flags remain false.

Compensation: disable the reporting route/feature if necessary and retain immutable source/review history. This additive migration creates only functions and a supporting target-review index; it does not rewrite CRM records. No production migration was applied. The property-source dashboard, cost coverage/currency, campaign events and funnel metrics remain open.


## Property-source dashboard

The selected bound property in the acquisition underwriting workspace now offers **View property inquiry sources**. `PropertySources.tsx` fetches only after opening and keys requests by user, workspace, canonical lead, property and cursor. The parent remounts on property selection and the workspace parent remounts on user/workspace changes. Unbound leads do not expose this control.

The panel validates exact response scope, denied execution/ownership/contact flags, candidate counts, ordered source IDs, advancing cursors and consistent current campaign capture before displaying evidence. Errors and refreshes hide earlier data. Separate inquiry IDs, association type, exact identity review, current campaign and historical campaign attribution remain distinguishable. An empty page with excluded candidates still enables continuation. Previous-page navigation and refresh from the first page avoid presenting accumulated pages as one consistent total. No writes, source merging or provider calls are introduced.

Component tests cover lazy loading, historical/current display, empty-page continuation, first-page refresh, denied refresh and malformed/wrong-scope responses. Feature-enabled build and lint baseline pass. Rendered browser and mobile proof for this panel remain pending; component coverage does not establish live PostgREST/provider acceptance.


Rendered browser verification (October 26): the isolated real-component fixture passed empty-candidate continuation, reviewed repeat-inquiry display, historical campaign labeling, identity-review expansion and reset to the first source page. At 375px, identifiers wrap and navigation stacks without clipping. No console errors were reported. Screenshot: `evidence/2026-10-26-property-sources-mobile.jpg`. This verifies synthetic presentation; live API persistence, PostgREST authorization and provider acceptance remain separate release gates.
