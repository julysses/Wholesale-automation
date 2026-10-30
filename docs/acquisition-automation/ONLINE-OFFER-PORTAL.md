# Online offer-request portal — shared intake integration

October 30, 2026. Phase 3 capability under the original sequential activation gates. The request/preparation contract below is implemented; no public route, form, database write or provider is enabled by this increment.

## Existing paths inspected

`frontend/src/pages/LeadForm.tsx` provides a public multi-step form with saved-request recovery, navy styling and form configuration from `/api/forms`. `web/api/lead_forms_api.py` and existing public-intake migrations support the older website workflow, global intake owner configuration and separate follow-up behavior. Those routes must remain unchanged. The acquisition portal cannot inherit that global routing or follow-up behavior as workspace authorization.

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
