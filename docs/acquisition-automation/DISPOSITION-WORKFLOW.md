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

## Post-execution findings input (candidate105)

`schemas/acquisition_disposition_review.py` defines separate principal/assignment input shapes. Common findings cover contractual interest, closing structure and remaining obligations. Assignment adds assignment provisions, legal basis, seller-disclosure requirements and assignee-disclosure requirements. This records a human review of the applicable requirements; it does not encode or invent legal requirements. Each satisfactory finding requires original citations; every unknown/unresolved finding requires an explicit next action. Original artifact versions/hashes must agree across findings. Client-supplied title/execution/reviewer authority is rejected.

Review requests select the saved proposal and reviewer policy. The controlled writer must derive and check the exact live bindings; IDs in a request are selectors, not authorization. Approval-shaped inputs require satisfactory findings and expiry; held findings have no expiry. Withdrawal identifies the original review and cannot supply replacement findings or renew authority. The pure assessment always returns false for legal/disposition/marketing/execution authority, even with complete inputs. No route, persistence or new approval capability is enabled by candidate105.

### Required next persistence and execution boundary

Inventory the current review ledger, policies, constraints, indexes, grants/RLS, source-reference helpers and migrations before writing SQL. Extend the existing immutable review ledger with a distinct post-execution disposition-findings kind; do not reuse draft preparation kinds or create another CRM.

The new controlled writer/state path must:

- Bind the current exact proposal and exit type, recorded execution/title-entry transitions, current post-execution title decision and original execution/deadline authority. A superseding/withdrawn proposal or title decision invalidates current disposition approval without rewriting the historical receipt.
- Resolve every cited original document and clause to its retained contract version/hash, current verification/scanner/retention authority and applicable reviewed policy. Assignment legal-basis evidence needs a distinct counsel-approved policy; generic preparation assignment reviews are insufficient. Do not provision that policy automatically.
- Pin actual workspace/member/session, contract/version, proposal/title/execution/deadline and reviewer/source/policy authority under the existing lock order; recheck expirations after waits. Cap approval expiry by all bound authority lifetimes.
- Preserve exact actor/session/request retries, immutable originals, explicit resolution holds, independent original withdrawal after pause, and one audit per saved review. Historical receipts grant no current authority.
- Expose typed user-JWT application routes, bounded current choices and original history, with strict receipt/context checks and uncertain-save recovery. Add the findings form inside the same guided contract step.
- Only then add the separately controlled transition into disposition review. Buyer distribution, agreement execution, changed closing structure and closing remain separate approvals.

Acceptance must include real full-catalog migration/RLS tests, observed revocation during waits, superseded proposal/title binding, mixed versions and original sources, lost-response replay through the mounted API, and desktop/phone parent-recovery QA. Domain input tests alone do not satisfy this persistence or release gate.

## Immutable disposition storage (candidate106, locally verified)

The existing review ledger now has a distinct disposition-findings shape. Every record binds a recorded proposal, its exit/execution/title-entry roots and a recorded post-execution title decision. Resolve title findings first: an unresolved title decision can support a disposition resolution hold, but cannot support disposition approval. Original withdrawals retain all these references, including the original title status. Historical reference integrity never establishes current authority; the forthcoming controlled writer must independently check freshness, current proposal/title sequences, policies, sessions and original evidence.

Four focused PostgreSQL tests passed24.451s. The initial wrong-version fixture accidentally repeated the retained original version; corrected it to a different version and reran successfully. Tests cover malformed findings/citations, both exits, exact scope/version/proposal/title/execution roots, journal consistency, held title, retained withdrawal roots, immutable rows, RLS/MFA/session isolation, forbidden raw writes/TRUNCATE and generic-writer rejection. Full95-migration rehearsal passed26 access checks,279 workflows and148 actual API checks; preserved24 historical rows,22 populated tables,103 definitions and Storage. Session36587 terminal0; evidence `evidence/2026-11-01-disposition-storage-result.json`. No writer, API, policy provisioning, lifecycle transition or live action is enabled by this storage change.

## Private original-source resolver (candidate107, locally verified)

The private resolver derives the purchase-contract artifact and exact verification from the selected current proposal's recorded execution review. It accepts no client replacement for that root. Satisfactory contractual-interest and assignment-provisions findings must cite that executed original. It resolves all other citations through original versioned references, verifies their exact hashes/scans, locks retention/scanner/member/session authority, and rechecks authority after waits. Superseded or withdrawn proposals are rejected. Results explicitly deny legal/disposition/marketing/execution authority; the future writer must independently bind current title, execution/deadline and reviewed legal/reviewer policy.

Pre-migration inventory: `evidence/2026-11-01-disposition-source-local-catalog.json` (142 columns,91 constraints,23 indexes,10 policies,6 security records). Migration `20261101074845_acquisition_disposition_source_resolution.sql` creates an ungranted private helper only. Five focused PostgreSQL tests passed30.923s, including mixed original versions, exact root derivation, proposal replacement/withdrawal, private-role denial and observed retention revocation during a wait. Full96-migration rehearsal passed26 access checks,284 workflows and148 actual API checks;24 historical rows,22 populated tables,103 definitions and Storage preserved. Session23291 terminal0; evidence `evidence/2026-11-01-disposition-sources-result.json`. No application writer or legal policy is enabled.

## Exit-specific reviewer policy (candidate108, verification in progress)

Inventory before SQL: `evidence/2026-11-01-disposition-policy-local-catalog.json` records142 columns,91 constraints,23 indexes,10 RLS policies and6 security records from the disposable candidate107 schema. Migration `20261101080541_acquisition_disposition_policy_scope.sql` adds a private child of the existing reviewer-policy record. It preserves the parent row shape because historical title approvals compare their entire retained parent-policy snapshot.

Each scope binds the exact workspace, reviewer, disposition kind and purchase-contract purpose by composite foreign key. It selects either principal acquisition or assignment. Assignment requires a retained workspace-owned legal-source artifact; principal purchase cannot inherit that assignment field. Explicit reviewed-by/approval-reference, finite validity and revocation fields have no defaults or seeds. The child has RLS and no public, anonymous, authenticated or service-role grants. This stores administrative review provenance; it does not establish that a person is counsel or that the referenced document is sufficient legal advice.

A private policy-only predicate verifies the exact combined reviewer/scope snapshot, current dates, revocations, workspace/reviewer and selected exit. It deliberately does not establish contract, source, title, execution, session or legal authority. A nullable disposition snapshot extends the existing review ledger without rewriting historical rows. The controlled writer must populate it for new findings and reject snapshotless approvals when evaluating current authority.

Four focused PostgreSQL tests passed24.781s, covering title-policy compatibility, exact snapshot matching, principal/assignment separation, tenant/source/reviewer constraints, private role denial, revocation and time bounds. Full97-migration upgrade/application rehearsal is running in session99245, log `/tmp/disposition-policy-upgrade.log`; do not restart it merely because a polling call times out. Until that rehearsal passes, this candidate is uncommitted and unverified for publication. The repair successor41287270262 must also pass all six jobs before any pending feature push.

### Writer and app continuation

1. Derive the current proposal, original executed-contract review and post-execution title decision server-side. Missing title findings lead the operator back to title review; a held title finding permits only a disposition resolution hold.
2. Lock the combined original-source set in sorted order before acquiring source authority. Resolve disposition sources, pin execution/title sources and reviewer authority, and lock deadline authority using the established order. Lock the disposition parent and scope rows; recheck all expiration/revocation conditions after waits.
3. Require an assignment's policy-bound legal source in both its legal-basis citations and its verified original-source journal. A matching artifact ID alone is insufficient. Approval additionally requires current exact title and execution/deadline authority; cap expiry by every bound lifetime. Held findings have no approval expiry.
4. Save one immutable decision/audit with exact request fingerprint and combined policy snapshot. Preserve actor/session-bound retry before current activation checks, and independent original withdrawal after pause. Withdrawal copies original proposal/exit/execution/title roots without replacing findings.
5. Evaluate current approval separately from historical receipts, including latest proposal/title decision and exact policy snapshots. Leave signing, marketing, assignment, buyer selection and closing unavailable. Do not broaden the existing title/execution stage checks until implementing and testing the separately controlled lifecycle transition.
6. Mount typed application routes, current choices and original history; then present findings inside the existing contract step using the navy/orange design, concrete next actions and original-save recovery. Preserve all broader PRD channel, provider, hosted, legal, buyer and closing requirements.

Compensation: revoke the privately managed scope or pause acquisition; retain immutable history. No production migration or live policy provisioning is authorized by this change.

## Controlled disposition review (candidate109, local verification in progress)

Migration `20261101080958_acquisition_disposition_review_write.sql` implements controlled write/state functions over the original ledger. It derives the recorded proposal, execution and latest title findings; resolves original evidence; binds the exact reviewer/scope snapshot; pins title/execution/deadline/source authority and rechecks after waits. Approval requires current bounded title and execution, the current proposal and verified policy-bound assignment legal citations. An unresolved legal finding may be recorded as a hold with a concrete next action; it cannot approve. The canonical contract status and transaction terms remain unchanged.

Exact original requests return historical receipts after pause without claiming current authority. Original personal withdrawals retain the proposal, execution and title roots and remain possible after policy revocation. Current-state reads independently evaluate superseded proposal/title decisions, policy snapshots, source and reviewer sessions, expiry and revocation. Both public entry points use the existing authenticated user context; private definer writers and read functions have explicit role grants and empty search paths. No service-role fallback, live policy or lifecycle transition is introduced.

Pre-SQL inventory: `evidence/2026-11-01-disposition-write-local-catalog.json` (155 columns,102 constraints,25 indexes,10 policies,7 security records). Initial7-test writer run completed with6 passes and1 fixture failure: the revocation case targeted the legacy preparation title policy instead of the actual post-execution findings policy. Corrected the fixture to FINDINGS_POLICY and added observed waits for title and deadline policy revocation. Final9-test focused run is session91928, log `/tmp/disposition-write-focused-final.log`. Do not claim verified until terminal success. Candidate109 is not yet added to the full-upgrade manifest/runner; finish candidate108's existing session99245 first, then add the writer cases, exact migration hash and perform the98-migration populated-upgrade/API rehearsal. Mounted backend routes and guided UI remain next work, not complete.

Candidate108 final verification: session99245 terminal0;97 migrations,26 access,288 workflows and148 actual API checks passed with historical rows/definitions/Storage preserved. Evidence: `evidence/2026-11-01-disposition-policy-result.json`. Candidate109 is separate and still requires its full rehearsal.

Candidate109 focused verification completed:9 tests passed62.597s; session91928 terminal0. Manifest and full-catalog runner now include the writer and nine cases. Full98-migration rehearsal is running in session62143 (`/tmp/disposition-write-upgrade.log`). Keep the exact run; writer is not yet committed or approved for publication.

## Mounted disposition API (candidate110, gateway test not yet connected)

GET/POST disposition-review now validate exact user-JWT scope, original request identity, non-executing historical receipts, current state freshness and original hold/withdrawal semantics. Definite POST rejection markers are separate from uncertain save outcomes and GET failures. Full backend4527 tests passed; real gateway helper `acquisition_disposition_review_http.py` is prepared but not yet called. Connect it after the existing title-history/purchase-path journey, passing original api_body to renew the synthetic title at sequence6 and create a sequence3 assignment proposal, then rerun gateway validation. No UI, transition or live legal policy is implied by these API routes.

Candidate109 final full verification:98 migrations,26 access,297 workflows and148 actual API checks passed; session62143 terminal0. Historical rows, definitions and Storage preserved. Evidence: `evidence/2026-11-01-disposition-write-result.json`. Candidate110 gateway integration remains separately pending.

Candidate110 final gateway verification: helper is now connected after the title and purchase-path journeys. Reapplied98 migrations and26 access checks, passed153 actual API checks, and preserved historical records/Storage. Workflow297 evidence is reused from candidate109, explicitly marked not rerun in this targeted result. Actual approval/hold/withdrawal commit-loss recovery, workspace/role/version/conflict rejection and unchanged canonical contract passed. Session73749 terminal0; evidence `evidence/2026-11-01-disposition-mounted-api-result.json`. Backend4527 passed. UI/discovery/history and lifecycle transitions remain open.
