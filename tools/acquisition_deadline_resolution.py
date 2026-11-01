"""Compare a proposed date interpretation with server-loaded original terms.

No persistence, legal determination, policy approval or mutation is performed.
"""
from schemas.acquisition_contract_terms import ContractTermsDraft
from schemas.acquisition_deadline_resolution import ContractDeadlineResolutionRequest


def assess_deadline_resolution(request: ContractDeadlineResolutionRequest,
                               prepared: ContractTermsDraft, *, current_version: int) -> dict:
    if type(current_version) is not int or not 1 <= current_version <= 2147483647:
        raise ValueError('An exact current contract version is required')
    proposed = request.resolution
    original = getattr(prepared, proposed.term)
    reasons = []
    if request.expected_version != current_version:
        reasons.append('CONTRACT_VERSION_CHANGED')
    if original.precision == 'unknown':
        reasons.append('ORIGINAL_DATE_REQUIRED')
    elif original.precision == 'instant':
        reasons.append('TERM_ALREADY_HAS_EXPLICIT_INSTANT')
    elif original.calendar_date != proposed.calendar_date:
        reasons.append('ORIGINAL_DATE_CHANGED_REQUIRES_AMENDMENT')
    return {
        'assessment_version': 'acquisition-deadline-resolution-v1',
        'status': 'requires_review' if reasons else 'ready_for_review',
        'reason_codes': reasons,
        'term': proposed.term,
        'original_precision': original.precision,
        'source_verification_required': True,
        'reviewer_policy_required': True,
        'legal_review_approved': False,
        'execution_authorized': False,
    }
