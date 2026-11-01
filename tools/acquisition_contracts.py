"""Pure readiness review, not a transition, signature, legal finding or send permit.

A future repository must load this snapshot under workspace/session authorization,
then lock and recheck the current version/evidence before persisting any transition.
"""
from datetime import timedelta

from schemas.acquisition_contracts import CONTRACT_TRANSITIONS, ContractReviewSnapshot

VERSION = 'acquisition-contract-review-v3'
NEXT = CONTRACT_TRANSITIONS
BUYER_BOUND = {'seller_disclosure', 'assignee_disclosure',
               'buyer_verification', 'assignment_agreement', 'deposit_confirmation'}
EXCEPTIONS = {'cancelled': 'cancellation_review', 'expired': 'expiration_review',
              'disputed': 'dispute_report'}


def review_contract_transition(snapshot: ContractReviewSnapshot) -> dict:
    s = snapshot
    reasons = []
    if s.target_status not in NEXT[s.status]:
        reasons.append('TRANSITION_NOT_PERMITTED')
    if s.snapshot_at > s.now or s.now - s.snapshot_at > timedelta(minutes=5):
        reasons.append('SNAPSHOT_NOT_CURRENT')
    ids = [e.id for e in s.evidence]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate contract evidence')
    if any(e.workspace_id != s.workspace_id or e.contract_id != s.contract_id for e in s.evidence):
        raise ValueError('Contract evidence scope mismatch')

    required = set()
    if s.target_status in EXCEPTIONS:
        required.add(EXCEPTIONS[s.target_status])
    else:
        if s.purchase_price_cents is None:
            reasons.append('PURCHASE_PRICE_REQUIRED')
        if (s.purchase_price_cents is not None and s.earnest_money_cents is not None
                and s.earnest_money_cents > s.purchase_price_cents):
            reasons.append('EARNEST_MONEY_EXCEEDS_PURCHASE_PRICE')
        if s.target_status == 'pending_signature':
            required.update({'contract_review', 'signature_release'})
            if s.earnest_money_cents is None:
                reasons.append('EARNEST_MONEY_REQUIRED')
        if s.target_status in {'executed', 'title_review', 'disposition_review',
                               'assigned_or_direct_close', 'closed'}:
            required.add('executed_contract')
            if any(value is not None for value in (s.effective_date, s.inspection_deadline_date, s.closing_deadline_date)):
                reasons.append('DATE_ONLY_CONTRACT_TERMS_REQUIRE_REVIEW')
            if (s.effective_at is None or s.effective_at > s.now
                    or s.inspection_deadline is None or s.closing_deadline is None
                    or s.earnest_money_cents is None):
                reasons.append('CONTRACT_TERMS_INCOMPLETE')
            if (s.effective_at and s.closing_deadline and s.effective_at >= s.closing_deadline
                    or s.effective_at and s.inspection_deadline and s.inspection_deadline < s.effective_at
                    or s.inspection_deadline and s.closing_deadline and s.inspection_deadline > s.closing_deadline):
                reasons.append('CONTRACT_DEADLINES_REQUIRE_REVIEW')
            # Closing confirmation may legitimately be reconciled after its deadline.
            # Other forward progress is held for a reviewed extension/new version.
            if s.target_status != 'closed' and s.closing_deadline and s.closing_deadline <= s.now:
                reasons.append('CLOSING_DEADLINE_PASSED')
        if s.status == 'disputed':
            required.add('dispute_resolution')
        if s.target_status in {'disposition_review', 'assigned_or_direct_close', 'closed'}:
            required.update({'contract_review', 'title_review'})
            if s.exit_type is None:
                reasons.append('EXIT_TYPE_REQUIRED')
            if s.exit_type == 'wholesale_assignment':
                if s.assignment_allowed is not True:
                    reasons.append('ASSIGNMENT_NOT_CONFIRMED')
                required.add('assignment_basis')
        if s.target_status in {'assigned_or_direct_close', 'closed'}:
            required.add('structure_approval')
            if s.exit_type == 'wholesale_assignment':
                if s.buyer_id is None:
                    reasons.append('BUYER_REQUIRED')
                required.update({'seller_disclosure', 'assignee_disclosure', 'buyer_verification',
                                 'assignment_agreement', 'deposit_confirmation'})
        if s.target_status == 'closed':
            required.add('closing_confirmation')

    valid = set()
    for e in s.evidence:
        if (e.revoked or e.contract_version != s.contract_version
                or e.recorded_at > s.now or e.expires_at <= s.now):
            continue
        if e.kind in BUYER_BOUND and (e.buyer_id != s.buyer_id or e.buyer_id is None
                                      or e.exit_type != s.exit_type):
            continue
        if e.kind == 'assignment_basis' and e.exit_type != 'wholesale_assignment':
            continue
        if e.kind in {'structure_approval', 'closing_confirmation'} and (
                e.exit_type != s.exit_type or e.exit_type is None or e.buyer_id != s.buyer_id):
            continue
        valid.add(e.kind)
    missing = sorted(required - valid)
    reasons.extend('EVIDENCE_REQUIRED:' + kind for kind in missing)
    return {'version': VERSION, 'contract_id': str(s.contract_id),
            'contract_version': s.contract_version, 'current_status': s.status,
            'target_status': s.target_status, 'readiness': 'needs_review' if reasons else 'ready_for_review',
            'reason_codes': reasons, 'required_evidence': sorted(required),
            'term_precision': {name: 'instant' if getattr(s, instant) is not None else 'date' if getattr(s, calendar) is not None else 'unknown'
                               for name, instant, calendar in (('effective', 'effective_at', 'effective_date'),
                                  ('inspection_deadline', 'inspection_deadline', 'inspection_deadline_date'),
                                  ('closing_deadline', 'closing_deadline', 'closing_deadline_date'))},
            'execution_authorized': False}
