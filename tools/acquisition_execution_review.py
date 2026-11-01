"""Compare returned terms to the authorized prepared version without approving them."""
from datetime import datetime

from schemas.acquisition_contract_terms import ContractTermsDraft
from schemas.acquisition_execution_review import ExecutionFindings
from tools.acquisition_contract_terms import assess_contract_terms


def assess_execution_findings(findings: ExecutionFindings, prepared: ContractTermsDraft, *, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Explicit current instant required')
    terms = findings.terms
    reasons = list(assess_contract_terms(terms)['reason_codes'])
    for name in ('seller_signatures', 'buyer_signatures', 'signing_authority', 'complete_agreement'):
        if getattr(findings, name).finding != 'confirmed':
            reasons.append(name.upper() + '_REQUIRES_REVIEW')
    # Missing prepared values may be supplied by returned documents; known values
    # must not silently change. Compare values, not provenance or preparation notes.
    changed = []
    for name in ('purchase_price_cents', 'earnest_money_cents', 'assignment_allowed', 'assignment_provisions'):
        previous = getattr(prepared, name)
        if previous is not None and previous != getattr(terms, name):
            changed.append(name)
    for name in ('effective', 'inspection_deadline', 'closing_deadline'):
        previous = getattr(prepared, name)
        if previous.precision != 'unknown' and previous != getattr(terms, name):
            changed.append(name)
    if changed:
        reasons.append('RETURNED_TERMS_DIFFER_FROM_REVIEWED_VERSION')
    if terms.effective.instant is not None and terms.effective.instant > now:
        reasons.append('EFFECTIVE_TIME_NOT_REACHED')
    if terms.closing_deadline.instant is not None and terms.closing_deadline.instant <= now:
        reasons.append('CLOSING_DEADLINE_PASSED')
    return {'assessment_version': 'acquisition-execution-findings-v1',
            'status': 'requires_review' if reasons else 'ready_for_review',
            'reason_codes': list(dict.fromkeys(reasons)), 'changed_terms': changed,
            'source_verification_required': True, 'legal_review_approved': False,
            'execution_authorized': False}
