"""Describe unresolved title findings without confirming title or authorizing an exit."""
from datetime import datetime
from schemas.acquisition_title_review import TITLE_FINDING_NAMES, TitleFindings


def assess_title_findings(findings: TitleFindings, *, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Explicit current instant required')
    reasons, actions = [], []
    if findings.report_as_of.precision == 'unknown':
        reasons.append('TITLE_REPORT_CUTOFF_UNKNOWN')
    elif findings.report_as_of.instant is not None and findings.report_as_of.instant > now:
        reasons.append('TITLE_REPORT_CUTOFF_IN_FUTURE')
    # Calendar precision stays calendar precision. Counsel-approved freshness and
    # timezone rules belong in server policy; never invent a midnight timestamp.
    for name in TITLE_FINDING_NAMES:
        finding = getattr(findings, name)
        if finding.finding != 'satisfactory':
            reasons.append(name.upper() + '_REQUIRES_RESOLUTION')
            actions.append({'finding': name, 'action': finding.required_action})
    return {'assessment_version': 'acquisition-title-findings-v1',
            'status': 'requires_resolution' if reasons else 'ready_for_review',
            'reason_codes': reasons, 'required_actions': actions,
            'source_verification_required': True, 'report_freshness_review_required': True,
            'recorded_execution_binding_required': True,
            'legal_review_approved': False, 'title_clearance_confirmed': False,
            'execution_authorized': False}
