# Online offer-request portal — shared intake integration

October 30, 2026. Phase 3 capability under the original sequential activation gates. The request/preparation contract and disabled form-version registry are implemented locally. No public acquisition route, production form/database write or provider is enabled.

## Existing paths inspected

`frontend/src/pages/LeadForm.tsx` provides a public multi-step form with saved-request recovery, navy styling and form configuration from `/api/forms`. `web/api/lead_forms_api.py` and existing public-intake migrations support the older website workflow, global intake owner configuration and separate follow-up behavior. Their legacy submission and follow-up behavior must remain compatible. The acquisition portal cannot inherit that global routing or follow-up behavior as workspace authorization.

The shared `tools/acquisition_intake.py::normalize_seller_fields` already preserves seller assertions, unknown prices, conflicts and preliminary classification without canonical-property, ownership, contact-permission or offer authority. The new preparer reuses it instead of creating a competing qualification engine.

## Implemented contract

`schemas/acquisition_online_offer.py` defines an exact request with a stable submission UUID, form version, seller reply contact, property address/city/state/postal code, authority assertion, condition, occupancy, timeline, motivation, optional decimal-text asking price and affirmative selections. Extra workspace, actor, MAO, offer and consent-wording fields are rejected. Unknown price remains null. Unsupported phone shapes/extensions are rejected; supported formats normalize consistently with the acquisition contact crosswalk while retaining the original submitted phone in evidence. Address validation here is shape only, not canonical verification.

`OfferFormDefinition` is a server-owned reviewed definition, not public input. It supplies the form key/version and exact wording for privacy acknowledgement, optional human callback request and optional email reply request. Production wording and links still require review. Synthetic test wording is not deployment copy.

`tools/acquisition_online_offer.py::prepare_online_offer` checks the submitted version, preserves the exact validated request/wording/selections and computes a deterministic SHA-256. Missing optional selections remain distinct from explicit false. A changed selection or displayed wording changes the fingerprint. It outputs `source_type=online_offer_portal`, shared normalized assertions and an explicitly unverified/non-authorizing classification. Telephone/email requests create no permission grant; future execution must consult shared eligibility.

The preparer performs no network access, private-owner lookup, identity merge, pricing calculation, CRM write or response to a seller. Its output contains sensitive submitted data and is for access-controlled server persistence only, never a public receipt or log payload.

## Required integration next

1. Inspect current private integration, receipt, seller_intake and lead constraints/RLS before SQL. Reuse and extend those logical entities. Add a server-owned public form registry binding an opaque form key and approved version to exactly one workspace/campaign, initially disabled. Do not accept workspace/campaign IDs from the seller or use existing global website ownership as authority.
2. Implement transactional acceptance/completion with stable submission identity scoped to that form, exact snapshot/hash retries, immutable version/consent evidence and safe uncertain-response recovery. Preserve all legacy website/Meta receipts. Do not coerce the new channel into a Facebook provider identity to fit current constraints.
3. Add the public read/submit endpoints with strict response projections, no-store behavior, body limits, durable rate limiting and reviewed bot verification. Bind any bot token to the approved form/action/host and validate it server-side. Never expose owner names, existence of matching private records, internal IDs, MAO, investor assumptions or raw prepared answers. A duplicate receipt may acknowledge the same request without exposing another submission.
4. Build the seller journey using the established navy/orange styling and mobile controls: (1) property and ownership/authority, (2) condition/occupancy/timeline/price, (3) reply details and exact optional selections, (4) review and submit. Persist the same request for unconfirmed retries; do not silently refresh wording or change the body of a pending request. Use a generic confirmation that Hilltop is reviewing it. No instant price or binding offer.
5. Connect accepted requests to the existing acquisition inquiry/property/underwriting/amount-review handoff with the correct workspace. Phone-only matches cannot merge unrelated properties. Canonical address/territory review, identity decisions and missing market data remain visible to the owner. Final written offers still require human approval and a reviewed template.
6. Verify all WEB-001–006 cases through the new endpoints and rendered UI, then approved hosted acceptance. Phase 1/2 gates must pass before activating this channel. The contract tests are not portal release acceptance.

## Validation checkpoint

62 offline tests passed across the new online-offer contract and existing shared intake tests. Cases include exact wording/selection preservation, deterministic and conflicting fingerprints, stale versions, missing prices, denied/uncertain authority, out-of-territory review, unsupported contact formats, callback/contact consistency, strict bool/decimal types and rejection of injected workspace/price/permission fields. No migration, public endpoint or existing form changed.


## Shared-table boundary inspection and first repair

Live read-only metadata at 22:55:07 UTC confirmed the current ledger still ends at 20261023221455. lead_form_configs has its UUID primary key, globally unique slug, legacy campaign FK, the two corresponding unique indexes, broad authenticated legacy policies plus approved-profile restriction, and anonymous read of active rows. No private acquisition_public_forms registry exists. See evidence/2026-10-30-online-form-source.json. Proposed acquisition migration 20261026205233 already blocks any legacy form association to an acquisition campaign and prevents raw TRUNCATE/TRIGGER operations; preserve that protection until its reviewed replacement exists.

The old public GET returned the entire service-loaded configuration. It now explicitly projects the fields used by LeadForm and strips internal top-level routing/settings and nested option scoring hints. The response uses no-store. Submit validation still loads the complete server configuration, without mutating it. Null/absent option lists retain legacy text-field rendering; malformed structures fail without disclosing config. This is HTTP output minimization, not a fix for raw-table legacy RLS and not new portal routing.

Before registering acquisition rows in this shared table, implement restrictive workspace/role read/write policies, immutable version/wording evidence and guarded server-owned routing. Ensure legacy authenticated/service-backed CRUD cannot read or mutate new acquisition configurations across workspaces, activate them through the old active flag or attach them to global-owner intake. Both the database and service-backed list/update endpoints need explicit tests. Do not remove the existing acquisition campaign-association guard simply to allow the new form insert.

Validation for the repair: 102 Python tests passed across public forms, online request contract and shared intake; 13 existing frontend outage/recovery/reset tests passed. No frontend code, schema, stored form configuration or production deployment was changed. Registry/persistence, bot/rate controls and new seller UI remain required.


## Disabled form-version registry — October 30

CLI-created proposed migration 20261030230704 extends lead_form_configs instead of creating a competing form store. The private acquisition_form_families relation contains only the immutable routing key/workspace/campaign tuple. Its composite foreign key binds each form version to the same campaign forever. The globally unique key cannot be claimed by another workspace or moved to a different campaign. Existing unscoped form rows retain their columns and behavior.

The owner/admin MFA save_acquisition_offer_form RPC accepts a stable request UUID, workspace/campaign, expected revision and exact OfferFormDefinition. It preserves exact wording, assigns an immutable revision and stores a database SHA-256 of jsonb::text (distinct from the preparer's canonical request-evidence hash). It serializes by request and form key; exact retries return the existing version, changed bodies/stale revisions conflict, and reused version labels cannot overwrite history. Session authority is locked and its wall-clock expiry rechecked after serialization waits. A single immutable audit event records each saved version. Saving is preparation only; no wording is certified as legally approved.

Rows require active=false, both confirmation messaging flags=false and no redirect. Anonymous table reads exclude acquisition versions; authenticated reads require actual workspace role/session, and raw writes cannot modify scoped versions. Immutable triggers also deny service-role edits/deletes and legacy form/campaign enrollment. The legacy submission table rejects these form IDs until a dedicated controlled acquisition acceptance path is implemented. The existing creative and lead campaign guards are unchanged.

Service-backed legacy form lists exclude scoped rows even with acquisition flags off. Public legacy GET/submit refuses them. Legacy PATCH accepts only known editable display/behavior fields, checks target scope, and refuses scoped campaign associations; CREATE also checks the campaign. These checks work before additive columns exist by treating absent workspace_id as legacy. Database guards remain authoritative for direct writes and races.

Validation: 98 related Python tests passed. Four new full-catalog registry journeys cover concurrent retry convergence, version history, role/tenant/MFA denial, invalid definitions, cross-campaign/key takeover, disabled activation, session revocation, expiry during a demonstrated advisory-lock wait, raw service mutation/legacy submission denial and preserved active legacy rendering. Full rehearsal passed 51 proposed migrations, 26 access probes, 64 workflows, 24 historical rows across 22 populated tables/103 definitions, and the existing 23 actual local PostgREST checks. The new registry RPC is tested directly against SQL in this increment, not through actual PostgREST or a rendered administration screen. Evidence: evidence/2026-10-30-offer-registry-result.json.

Compensation after any separately approved deployment: revoke authenticated EXECUTE on both public/private save_acquisition_offer_form wrappers through a reviewed forward migration and hide its preparation controls. Keep all existing versions, routing identities and audit history; never re-enable legacy mutable access or drop the added data. No production migration is authorized here.

Next: exact administration API/store response models and guided campaign setup; controlled public version selection/activation; transactional online submission using existing receipt/intake equivalents; rate/bot controls and the four-step seller UI. All original WEB and channel acceptance gates remain required.
