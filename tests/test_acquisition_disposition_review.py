from copy import deepcopy
import pytest
from pydantic import ValidationError
from schemas.acquisition_disposition_review import COMMON_FINDINGS, ASSIGNMENT_FINDINGS, DispositionFindings, DispositionReviewRequest
from tools.acquisition_disposition_review import assess_disposition_findings

ID='af105000-0000-4000-8000-000000000001'
OTHER='af105000-0000-4000-8000-000000000002'


def finding():
    return dict(finding='satisfactory',note='Human review of the original contract clause and supporting evidence.',required_action=None,
                sources=[dict(artifact_id=ID,artifact_version=2,sha256='a'*64,locator='Original contract clause 12, page 4')])


def findings(assignment=False):
    return dict(exit_type='wholesale_assignment' if assignment else 'principal_acquisition',
                **{name:finding() for name in COMMON_FINDINGS},
                assignment={name:finding() for name in ASSIGNMENT_FINDINGS} if assignment else None)


def request(assignment=False):
    return dict(id=OTHER,expected_version=2,expected_sequence=0,status='approved',plan_id=ID,original_review_id=None,
        policy_id=ID,expires_at='2026-11-01T13:00:00Z',personally_reviewed=True,
        note='Synthetic post-execution disposition findings for separate human review.',findings=findings(assignment))


@pytest.mark.parametrize('assignment',[False,True])
def test_complete_human_assertions_require_original_authority_and_never_authorize_exit(assignment):
    payload=request(assignment);before=deepcopy(payload)
    parsed=DispositionReviewRequest.model_validate(payload)
    result=assess_disposition_findings(parsed.findings)
    assert result['status']=='ready_for_review' and result['reason_codes']==[]
    assert result['assignment_legal_review_required']==assignment
    for key in ('source_verification_required','current_proposal_binding_required','recorded_execution_binding_required',
                'current_deadline_review_required','current_post_execution_title_required','reviewer_policy_required'):
        assert result[key]
    for key in ('disposition_approved','legal_review_approved','marketing_authorized','execution_authorized'):
        assert result[key] is False
    assert payload==before


@pytest.mark.parametrize('name',COMMON_FINDINGS+ASSIGNMENT_FINDINGS)
@pytest.mark.parametrize('state',['unknown','requires_resolution'])
def test_each_unresolved_finding_retains_specific_action_and_blocks_approval(name,state):
    payload=request(True);value=payload['findings']
    target=value[name] if name in COMMON_FINDINGS else value['assignment'][name]
    target.update(finding=state,sources=[],required_action='Obtain the original evidence and reconcile this specific requirement.')
    result=assess_disposition_findings(DispositionFindings.model_validate(value))
    assert result['reason_codes']==[name.upper()+'_REQUIRES_RESOLUTION']
    assert result['required_actions']==[dict(finding=name,action=target['required_action'])]
    with pytest.raises(ValidationError):DispositionReviewRequest.model_validate(payload)
    held=DispositionReviewRequest.model_validate(payload|dict(status='requires_resolution',expires_at=None))
    assert held.findings.exit_type=='wholesale_assignment'


@pytest.mark.parametrize('change',[{'expected_version':True},{'expected_sequence':True},{'expected_sequence':2147483647},
    {'personally_reviewed':False},{'findings':None},{'execution_transition_id':ID},{'title_review_id':ID},
    {'reviewed_by':ID},{'assignment_allowed':True},{'disposition_approved':True},{'original_review_id':ID},
    {'expires_at':'2026-11-01'},{'expires_at':1793538000},{'expires_at':None},{'note':' '*30},{'note':'Invalid null byte in the note\x00'}])
def test_invalid_requests_cannot_supply_authority_or_coerce_inputs(change):
    with pytest.raises(ValidationError):DispositionReviewRequest.model_validate(request()|change)


@pytest.mark.parametrize('assignment',[False,True])
def test_assignment_findings_cannot_be_omitted_or_attached_to_principal_path(assignment):
    value=findings(assignment);value['exit_type']='principal_acquisition' if assignment else 'wholesale_assignment'
    with pytest.raises(ValidationError):DispositionFindings.model_validate(value)


@pytest.mark.parametrize('change',[{'sources':[]},{'required_action':'This unresolved action must not accompany a satisfactory finding.'},
    {'sources':[dict(artifact_id=ID,artifact_version=2,sha256='a'*64,locator='\n')]},
    {'sources':[dict(artifact_id=ID,artifact_version=2,sha256='b'*64,locator='Another clause')]}])
def test_satisfactory_findings_need_consistent_original_sources(change):
    value=findings(True);value['assignment']['legal_basis'].update(change)
    with pytest.raises(ValidationError):DispositionFindings.model_validate(value)


def test_future_source_versions_rejected_but_original_versions_retained():
    payload=request(True)
    payload['findings']['assignment']['legal_basis']['sources'][0].update(artifact_id=OTHER,artifact_version=3)
    with pytest.raises(ValidationError):DispositionReviewRequest.model_validate(payload)
    payload['findings']['assignment']['legal_basis']['sources'][0]['artifact_version']=1
    assert DispositionReviewRequest.model_validate(payload).findings.assignment.legal_basis.sources[0].artifact_version==1


def test_withdrawal_preserves_original_identity_without_replacing_findings():
    payload=request()|dict(status='withdrawn',expected_sequence=1,original_review_id=ID,expires_at=None,personally_reviewed=False,findings=None)
    assert str(DispositionReviewRequest.model_validate(payload).original_review_id)==ID
    for change in ({'original_review_id':None},{'original_review_id':OTHER},{'expected_sequence':0},{'personally_reviewed':True},
                   {'expires_at':'2026-11-01T13:00:00Z'},{'findings':findings()}):
        with pytest.raises(ValidationError):DispositionReviewRequest.model_validate(payload|change)
