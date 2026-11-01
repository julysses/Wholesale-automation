"""Pure preparation assessment; persistence must resolve sources under tenant authorization."""
from schemas.acquisition_contract_terms import ContractTermsDraft


def assess_contract_terms(terms: ContractTermsDraft) -> dict:
    reasons = []
    if terms.purchase_price_cents is None:
        reasons.append('PURCHASE_PRICE_MISSING')
    if terms.earnest_money_cents is None:
        reasons.append('EARNEST_MONEY_MISSING')
    if terms.assignment_allowed is None:
        reasons.append('ASSIGNMENT_PROVISIONS_REQUIRE_REVIEW')
    dates = [(name, getattr(terms, name)) for name in ('effective', 'inspection_deadline', 'closing_deadline')]
    for name, value in dates:
        if value.precision == 'unknown':
            reasons.append(name.upper()+'_MISSING')
        elif value.precision == 'date':
            reasons.append(name.upper()+'_TIME_REQUIRES_REVIEW')
    # Compare only like precision. Never create a timezone/cutoff to compare a date to an instant.
    for left_name, right_name in (('effective', 'inspection_deadline'), ('effective', 'closing_deadline'), ('inspection_deadline', 'closing_deadline')):
        left, right = getattr(terms, left_name), getattr(terms, right_name)
        if left.precision == right.precision and left.precision != 'unknown':
            a, b = (left.instant, right.instant) if left.precision == 'instant' else (left.calendar_date, right.calendar_date)
            if a > b or left_name == 'effective' and right_name == 'closing_deadline' and a == b:
                reasons.append('TERM_DATE_ORDER_REQUIRES_REVIEW')
    if terms.purchase_price_cents is not None and terms.earnest_money_cents is not None and terms.earnest_money_cents > terms.purchase_price_cents:
        reasons.append('EARNEST_MONEY_EXCEEDS_PURCHASE_PRICE')
    return {'calculation_version': 'acquisition-contract-terms-v1', 'status': 'requires_review' if reasons else 'ready_for_review',
            'reason_codes': list(dict.fromkeys(reasons)), 'source_verification_required': True,
            'legal_review_approved': False, 'execution_authorized': False}
