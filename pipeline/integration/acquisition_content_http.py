"""Content review through real local PostgREST; all records and keys are synthetic."""
from datetime import timedelta
from uuid import UUID

from schemas.acquisition_evidence import EvidenceReviewCandidate
from schemas.acquisition_mail_preparation import ContentPreparation, ContentReviewState


def verify_content_http(db, request, token, other, workspace, campaign, artifact, verification):
    scope = {'p_workspace': workspace, 'p_campaign': campaign}
    candidate_path = '/rpc/acquisition_evidence_review_candidate'
    candidate_body = {**scope, 'p_artifact': artifact}

    def rpc(name, body):
        status, result = request('/rpc/' + name, token(), body)
        if status != 200:
            raise AssertionError(f'Content HTTP {name} failed: {status}')
        return result

    candidate = EvidenceReviewCandidate.model_validate(rpc('acquisition_evidence_review_candidate', candidate_body))
    if (candidate.workspace_id, candidate.campaign_id, candidate.artifact_id, candidate.verification_id) != tuple(
            UUID(v) for v in (workspace, campaign, artifact, verification)):
        raise AssertionError('Content HTTP candidate scope changed')
    if request(candidate_path, token(other), candidate_body)[0] != 403 or request(candidate_path, None, candidate_body)[0] != 401:
        raise AssertionError('Content HTTP candidate access boundary failed')
    creative = '99400000-0000-4000-8000-000000000001'
    destination = '99400000-0000-4000-8000-000000000002'
    content = '99400000-0000-4000-8000-000000000003'
    review = '99400000-0000-4000-8000-000000000004'
    rpc('save_acquisition_mail_template', {**scope, 'p_id': creative, 'p_template': creative,
        'p_expected_version': 0, 'p_name': 'Synthetic content HTTP', 'p_format': 'letter',
        'p_tracking_mode': 'phone', 'p_body': 'Contact {{company_name}} at {{tracking_phone}}.'})
    rpc('review_acquisition_mail_destination', {**scope, 'p_id': destination, 'p_destination': destination,
        'p_expected_version': 0, 'p_action': 'approved', 'p_mode': 'phone', 'p_value': '+12125550100',
        'p_verification_ref': destination, 'p_verification_hash': 'b' * 64,
        'p_verified_at': '2026-01-01T00:00:00Z', 'p_expires_at': '2099-01-01T00:00:00Z',
        'p_note': 'Synthetic local destination review evidence.'})
    preparation = rpc('prepare_acquisition_mail_content', {**scope, 'p_creative': creative,
        'p_destination_review': destination, 'p_company_name': 'Hilltop Home Company'})
    ContentPreparation.model_validate(preparation)
    body = {**scope, 'p_id': review, 'p_content': content, 'p_expected_version': 0, 'p_action': 'approved',
        'p_creative': creative, 'p_destination_review': destination, 'p_company_name': 'Hilltop Home Company',
        'p_preparation_hash': preparation['preparation_hash'], 'p_evidence_ref': artifact,
        'p_evidence_hash': candidate.sha256, 'p_expires_at': candidate.max_approval_until.isoformat(),
        'p_note': 'Synthetic content review against exact registered file.'}
    review_path = '/rpc/review_acquisition_mail_content'
    invalid = {**body, 'p_expires_at': (candidate.max_approval_until + timedelta(seconds=1)).isoformat()}
    status, error = request(review_path, token(), invalid)
    if status == 200 or error.get('code') != '55000':
        raise AssertionError('Content HTTP excessive approval deadline accepted')
    for caller in (token(other), None):
        if request(review_path, caller, body)[0] not in (401, 403):
            raise AssertionError('Content HTTP unauthorized approval accepted')
    if db.query('SELECT count(*) AS n FROM private.acquisition_content_evidence_bindings')[0]['n']:
        raise AssertionError('Rejected HTTP approval created a binding')
    for duplicate in (False, True):
        receipt = rpc('review_acquisition_mail_content', body)
        if receipt != {'review_id': review, 'workspace_id': workspace, 'content_id': content,
                       'version': 1, 'duplicate': duplicate, 'execution_authorized': False}:
            raise AssertionError('Content HTTP approval receipt or exact retry changed')
    state_body = {**scope, 'p_content': content}
    state = ContentReviewState.model_validate(rpc('acquisition_mail_content_state', state_body))
    if not state.review_current or state.status != 'approved' or state.execution_authorized:
        raise AssertionError('Bound HTTP approval not current')
    binding = db.query('SELECT review_id,artifact_id,verification_id,sha256 FROM private.acquisition_content_evidence_bindings')
    if len(binding) != 1 or tuple(str(binding[0][k]) for k in ('review_id','artifact_id','verification_id','sha256')) != (review,artifact,verification,candidate.sha256):
        raise AssertionError('Content HTTP exact immutable binding missing')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_mail_content'")[0]['n'] != 1:
        raise AssertionError('Content HTTP approval retry duplicated audit')

    def after_signer_revocation():
        status, error = request(candidate_path, token(), candidate_body)
        if status == 200 or error.get('code') != '55000':
            raise AssertionError('Revoked HTTP candidate remains selectable')
        state = ContentReviewState.model_validate(rpc('acquisition_mail_content_state', state_body))
        if state.review_current or state.status != 'requires_review' or state.execution_authorized:
            raise AssertionError('Signer revocation failed to invalidate HTTP content review')
        # Historical exact retry acknowledges its old receipt, never restores current approval.
        if rpc('review_acquisition_mail_content', body)['duplicate'] is not True:
            raise AssertionError('Historical HTTP retry did not reconcile')
        newer = {**body, 'p_id': '99400000-0000-4000-8000-000000000005', 'p_expected_version': 1}
        status, error = request(review_path, token(), newer)
        if status == 200 or error.get('code') != '55000':
            raise AssertionError('New HTTP approval accepted revoked evidence')
        withdrawal = {**newer, 'p_action': 'withdrawn', **{key: None for key in (
            'p_creative','p_destination_review','p_company_name','p_preparation_hash','p_evidence_ref','p_evidence_hash','p_expires_at')}}
        rpc('review_acquisition_mail_content', withdrawal)
        state = ContentReviewState.model_validate(rpc('acquisition_mail_content_state', state_body))
        if state.status != 'withdrawn' or state.review_current or state.version != 2:
            raise AssertionError('Content HTTP withdrawal failed')
        if db.query('SELECT count(*) AS n FROM private.acquisition_content_evidence_bindings')[0]['n'] != 1:
            raise AssertionError('HTTP withdrawal rewrote binding history')
        if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_mail_content'")[0]['n'] != 2:
            raise AssertionError('Content HTTP rejected approval or retry duplicated audit')
    return after_signer_revocation
