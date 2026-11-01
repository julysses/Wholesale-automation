"""Assess human input completeness; never authorize distribution or a transaction."""
from schemas.acquisition_disposition_review import DispositionFindings


def assess_disposition_findings(findings: DispositionFindings) -> dict:
    unresolved = [(name, finding) for name, finding in findings.entries() if finding.finding != 'satisfactory']
    return {
        'assessment_version': 'acquisition-disposition-findings-v1',
        'exit_type': findings.exit_type,
        'status': 'requires_resolution' if unresolved else 'ready_for_review',
        'reason_codes': [name.upper() + '_REQUIRES_RESOLUTION' for name, _ in unresolved],
        'required_actions': [{'finding': name, 'action': finding.required_action} for name, finding in unresolved],
        'source_verification_required': True,
        'current_proposal_binding_required': True,
        'recorded_execution_binding_required': True,
        'current_deadline_review_required': True,
        'current_post_execution_title_required': True,
        'reviewer_policy_required': True,
        'assignment_legal_review_required': findings.exit_type == 'wholesale_assignment',
        'disposition_approved': False,
        'legal_review_approved': False,
        'marketing_authorized': False,
        'execution_authorized': False,
    }
