from copy import deepcopy
from datetime import datetime,timezone
import pytest
from pydantic import ValidationError
from schemas.acquisition_title_review import TITLE_FINDING_NAMES, TitleFindings, TitleReviewRequest
from tools.acquisition_title_review import assess_title_findings

ID='af950000-0000-4000-8000-000000000001'
OTHER='af950000-0000-4000-8000-000000000002'
NOW=datetime(2026,11,1,12,tzinfo=timezone.utc)


def source(**changes):
    return dict(artifact_id=ID,artifact_version=2,sha256='a'*64,locator='Schedule A, page 1')|changes


def findings():
    return dict(report_as_of=dict(precision='date',calendar_date='2026-10-31',instant=None),
        report_as_of_source=source(),report_note='Synthetic title report scope and cutoff recorded from its original page.',
        **{name:dict(finding='satisfactory',note='Human reviewer inspected this synthetic title finding and its cited original.',
                    required_action=None,sources=[source()]) for name in TITLE_FINDING_NAMES})


def request():
    return dict(id=OTHER,expected_version=2,expected_sequence=0,status='approved',artifact_id=ID,verification_id=ID,
                policy_id=ID,expires_at='2026-11-01T13:00:00Z',personally_reviewed=True,
                note='Personal synthetic title review for a separate disposition-review decision.',findings=findings())


def assess(value):return assess_title_findings(TitleFindings.model_validate(value),now=NOW)


def test_satisfactory_human_assertions_never_establish_title_or_execution_authority():
    payload=request();before=deepcopy(payload);parsed=TitleReviewRequest.model_validate(payload)
    result=assess_title_findings(parsed.findings,now=NOW)
    assert result['status']=='ready_for_review' and result['reason_codes']==[]
    assert result['source_verification_required'] and result['recorded_execution_binding_required']
    assert result['report_freshness_review_required']
    assert not result['title_clearance_confirmed'] and not result['legal_review_approved'] and not result['execution_authorized']
    assert payload==before
    assert parsed.findings.report_as_of.instant is None
    assert parsed.model_dump(mode='json')['findings']['report_as_of']['calendar_date']=='2026-10-31'


@pytest.mark.parametrize('name',TITLE_FINDING_NAMES)
@pytest.mark.parametrize('state',['requires_resolution','unknown'])
def test_uncertainties_preserve_required_actions_and_cannot_be_approved(name,state):
    payload=request();value=payload['findings'];value[name].update(finding=state,sources=[],
        required_action='Obtain the missing original and reconcile this specific title issue.')
    result=assess(value)
    assert name.upper()+'_REQUIRES_RESOLUTION' in result['reason_codes']
    assert result['required_actions']==[{'finding':name,'action':value[name]['required_action']}]
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(payload)
    held=TitleReviewRequest.model_validate(payload|dict(status='requires_resolution',expires_at=None))
    assert getattr(held.findings,name).finding==state and held.expires_at is None


@pytest.mark.parametrize('change',[{'expected_version':True},{'expected_sequence':True},{'findings':None},
    {'personally_reviewed':False},{'execution_transition_id':ID},{'reviewed_by':ID},{'execution_authorized':True},
    {'expires_at':'2026-11-01'},{'expires_at':1793538000},{'note':' '*20},{'note':'A meaningful note with a null\x00 byte.'}])
def test_requests_reject_coercions_omissions_and_client_authority(change):
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(request()|change)


@pytest.mark.parametrize('change',[{'sources':[]},{'required_action':'Unresolved issue still needs a concrete resolution.'},
    {'note':' '*30},{'finding':True}])
def test_satisfactory_findings_require_real_citations_and_no_open_action(change):
    value=findings();value['ownership'].update(change)
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)


def test_report_cutoff_missing_remains_missing_and_requires_resolution():
    value=findings();value['report_as_of']=dict(precision='unknown',calendar_date=None,instant=None)
    value['report_as_of_source']=None
    assert assess(value)['reason_codes']==['TITLE_REPORT_CUTOFF_UNKNOWN']
    held=TitleReviewRequest.model_validate(request()|dict(status='requires_resolution',expires_at=None,findings=value))
    assert held.findings.report_as_of.precision=='unknown'
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(request()|dict(findings=value))


def test_explicit_future_instant_is_held_without_converting_calendar_dates():
    value=findings();value['report_as_of']=dict(precision='instant',calendar_date=None,instant='2026-11-02T00:00:00Z')
    assert assess(value)['reason_codes']==['TITLE_REPORT_CUTOFF_IN_FUTURE']
    with pytest.raises(ValueError):assess_title_findings(TitleFindings.model_validate(value),now=NOW.replace(tzinfo=None))
    value['report_as_of']=dict(precision='date',calendar_date='2026-10-31',instant='2026-10-31T00:00:00Z')
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)


@pytest.mark.parametrize('change',[{'artifact_version':3},{'artifact_version':True},{'sha256':'A'*64},
    {'locator':' '},{'locator':'page\n1'}])
def test_original_source_boundaries_reject_future_or_malformed_references(change):
    value=findings();value['ownership']['sources']=[source(**change)]
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(request()|dict(findings=value))


def test_conflicting_original_identity_and_duplicate_citation_are_rejected():
    value=findings();value['ownership']['sources']=[source(sha256='b'*64)]
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)
    value=findings();value['ownership']['sources']*=2
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)
    value=findings();value['report_as_of_source']=source(artifact_id=OTHER)
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(request()|dict(findings=value))


def test_distinct_supplemental_original_is_preserved_without_becoming_verified():
    value=findings();value['liens_and_payoffs']['sources']=[source(artifact_id=OTHER,artifact_version=1,sha256='b'*64,locator='Recorded release, page 2')]
    parsed=TitleReviewRequest.model_validate(request()|dict(findings=value))
    assert parsed.findings.liens_and_payoffs.sources[0].artifact_version==1
    assert assess(value)['source_verification_required']


def test_resolution_hold_and_withdrawal_cannot_renew_or_replace_approval():
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(request()|dict(status='requires_resolution'))
    held=TitleReviewRequest.model_validate(request()|dict(status='requires_resolution',expires_at=None))
    assert held.status=='requires_resolution'  # A human may hold even apparently satisfactory findings.
    data=request()|dict(status='withdrawn',personally_reviewed=False,expires_at=None)
    with pytest.raises(ValidationError):TitleReviewRequest.model_validate(data)
    withdrawn=TitleReviewRequest.model_validate(data|dict(findings=None))
    assert withdrawn.findings is None and not withdrawn.personally_reviewed


def test_missing_required_action_category_or_report_source_is_not_silently_defaulted():
    value=findings();del value['occupancy_and_possession']
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)
    value=findings();value['ownership'].update(finding='unknown',sources=[],required_action=None)
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)
    value=findings();value['report_as_of_source']=None
    with pytest.raises(ValidationError):TitleFindings.model_validate(value)
