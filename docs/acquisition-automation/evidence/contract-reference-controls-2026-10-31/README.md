# Contract reference controls: local browser evidence

Synthetic preview only, using the real React components and the local API fixture. No production database, provider, live seller or executed contract.

Run the existing `frontend/tests/browser/contract-draft.vite.config.ts` preview from the frontend directory. Open `/tests/browser/contract-draft.html?linkFixture=true` in a fresh isolated session for the link cases; use `?referenceFixture=true` in another fresh session for terms/source review.

- Desktop1280x900 and phone375x812: choose original version1, document and a20-character reason. Simulate lost reply, save the reference, reload, and retry. Repeat for withdrawal. One link and one withdrawal remain, original sourceversion1 is unchanged, recovery clears and sibling controls unlock.
- Phone375x812: enter140000.29 as a sourced price for targetversion2, attach originalversion1/page reference, simulate lost reply, save, reload and retry. Exactly one new targetversion3 is present. Select originalversion1 in the review form and confirm the explicit new-review message.
- Screenshots were visually inspected. Both measured document and scroll widths match the viewport; no page or console errors. The missing preview favicon was corrected with a local data icon before final runs.

See results.json and mobile-terms-results.json for measured outcomes. These checks do not establish hosted Auth/Storage, scanner, legal, delivery or fulfillment acceptance.
