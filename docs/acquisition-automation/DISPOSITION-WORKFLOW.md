# Purchase path and disposition workflow

## Scope and current boundary

The canonical contract remains `deals`. The additive `acquisition_disposition_plans` child records internal intent: Hilltop proposes a principal acquisition or a wholesale assignment. Each proposal retains the original contract version, recorded execution transition and title-entry transition. Saving a proposal does not approve title, assignment legality, marketing, an amended contract, a buyer, a fee or a closing. It does not advance contract status.

A plan may be prepared while title findings remain unresolved. This grants no execution authority. Subsequent disposition review must independently require the exact current post-execution `title_findings`, current execution/deadline authority and, for an assignment, a reviewed legal basis tied to the executed contract. Draft preparation `title_review` or generic `assignment_basis` must not substitute for those checks.

## Guided app journey (candidate104)

Keep the existing numbered acquisition journey and navy/orange controls. In contract step 5, after original documents and title findings, show a compact **Purchase path** card:

1. Choose **Hilltop purchases the property** or **Propose an assignment**. Neither is pre-approved. Describe why this path is proposed.
2. Save an **internal proposal**. Show the saved path and the next required title/contract review; do not display a success state suggesting authority to market or close.
3. Allow a revised proposal or withdrawal of the latest personal proposal. Original history remains retained. Withdrawal must work after acquisition is paused.
4. Only a later, separately implemented disposition review may authorize the controlled transition. Buyer selection, disclosures, packages and closing follow their own gates.

The form must share ContractDraft's existing navigation and sibling-edit holds. Store the exact request before sending. A lost reply, reload or later denial retains the original version and payload until an exact receipt confirms it. Corrupt/conflicting recovery must remain held. Clear a new request only for a definite first-attempt rejection; GET failures never clear a pending save.

The guided card is implemented in candidate104 with exact original recovery and parent navigation/sibling holds. Full frontend930 tests, build/typecheck, lint and synthetic desktop/phone browser journeys passed. API/database foundation was verified separately in candidate103. These are local checks, not hosted or live acceptance.

## Persistence and API

Migration: `20261101071737_acquisition_disposition_plans.sql`. Pre-migration inventory: `evidence/2026-11-01-disposition-plan-local-catalog.json` (local disposable database; 111 columns, 70 constraints, 19 indexes, 9 policies, 5 security records).

Immutable proposals and withdrawals are owner/admin-only with actual workspace membership, MFA and current session checks. New proposals require acquisition activation and current title-review contract context. Exact actor/session/request retries survive pause. A withdrawal retains the original proposal, exit type and original execution/title roots. Raw writes are revoked, including service-role access; all saved decisions append an audit event.

GET/POST `/api/acquisition/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/disposition-plan` use the existing user-JWT store. Requests cannot supply a buyer, money, actor or legal authority. Receipts must match the exact request and always deny disposition/execution authority. State reads validate scope, sequence, explicit timestamp freshness and original withdrawal identity. Only definite POST 401/403/409 responses mark the current attempt rejected.

Compensation is forward-only: pause acquisition or withdraw a saved personal proposal through the controlled RPC. Retain all history and audits. No production migration is approved by this work.

## Remaining full disposition work

- Guided proposal card and exact parent recovery are locally verified; hosted/operator acceptance remains open.
- Add versioned post-execution legal/disposition review bound to current execution, deadlines, title findings, proposed exit and approved original legal evidence. Do not seed authority policies.
- Implement controlled lifecycle transitions, amendments and cancelled/expired/disputed handling without breaking legacy contract constraints.
- Isolate existing buyers and dependent routes/tables before matching or package generation; do not clone a separate buyer CRM.
- Implement buyer verification, accurate contractual-interest packages, required reviewed disclosures, distribution approval, assignment agreement/deposit, closing milestones and gross/expense/net accounting.
- Complete hosted/platform and operator acceptance separately from local tests. Preserve the full PRD's channel and provider gates.
