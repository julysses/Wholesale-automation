"""Calendar precision, explicit offsets and original-version interpretation holds."""
from copy import deepcopy
from datetime import date
from uuid import UUID
import pytest
from pydantic import ValidationError
from schemas.acquisition_contract_terms import ContractTermsDraft
from schemas.acquisition_deadline_resolution import ContractDeadlineResolutionRequest
from tools.acquisition_deadline_resolution import assess_deadline_resolution


def source():
    return dict(term='closing_deadline', artifact_id=str(UUID(int=1)), artifact_version=1,
                sha256='a'*64, locator='Page 8, explicit closing time clause')


def body():
    return dict(id=str(UUID(int=2)), expected_version=2, resolution=dict(term='closing_deadline',
        calendar_date='2026-11-20', local_time='17:00:00', time_zone='America/Chicago',
        resolved_instant='2026-11-20T17:00:00-06:00', basis='explicit_document_time', source=source(),
        rationale='The cited original explicitly supplies this time for the preserved date.'))


def terms():
    return ContractTermsDraft(purchase_price_cents=None,earnest_money_cents=None,assignment_allowed=None,
        assignment_provisions=None,effective={'precision':'unknown'},inspection_deadline={'precision':'unknown'},
        closing_deadline={'precision':'date','calendar_date':'2026-11-20'},sources=[source()],
        note='Original calendar-only closing term is preserved for reviewed interpretation.')


def test_resolution_preserves_original_precision_and_never_grants_authority():
    prepared=terms();before=prepared.model_dump(mode='json');request=ContractDeadlineResolutionRequest.model_validate(body())
    assessment=assess_deadline_resolution(request,prepared,current_version=2)
    assert assessment['status']=='ready_for_review'
    assert assessment['source_verification_required'] and assessment['reviewer_policy_required']
    assert not assessment['legal_review_approved'] and not assessment['execution_authorized']
    assert prepared.model_dump(mode='json')==before and prepared.closing_deadline.instant is None
    assert request.resolution.calendar_date==date(2026,11,20)


@pytest.mark.parametrize('change',[
    {'local_time':'24:00:00'},{'local_time':'17:00'},{'local_time':1700},
    {'time_zone':'Central'},{'time_zone':'America/Chicago '},{'time_zone':'../UTC'},
    {'resolved_instant':'2026-11-20T17:00:00'},{'resolved_instant':1790000000},
    {'resolved_instant':'2026-11-20T17:00:00-05:00'},{'resolved_instant':'2026-11-21T17:00:00-06:00'},
    {'calendar_date':'2026-11-20T00:00:00Z'},{'calendar_date':True},{'rationale':' '*20},
    {'basis':'inferred_midnight'},{'execution_authorized':True},
])
def test_ambiguous_or_inconsistent_input_is_rejected(change):
    value=body();value['resolution'].update(change)
    with pytest.raises(ValidationError):ContractDeadlineResolutionRequest.model_validate(value)


@pytest.mark.parametrize('offset',['-05:00','-06:00'])
def test_repeated_dst_hour_requires_and_preserves_explicit_offset(offset):
    value=body();value['resolution'].update(calendar_date='2026-11-01',local_time='01:30:00',
        resolved_instant='2026-11-01T01:30:00'+offset)
    parsed=ContractDeadlineResolutionRequest.model_validate(value)
    assert parsed.resolution.resolved_instant.isoformat().endswith(offset)


def test_nonexistent_dst_local_time_is_rejected():
    value=body();value['resolution'].update(calendar_date='2026-03-08',local_time='02:30:00',
        resolved_instant='2026-03-08T02:30:00-06:00')
    with pytest.raises(ValidationError):ContractDeadlineResolutionRequest.model_validate(value)


@pytest.mark.parametrize('change', [{'term':'effective'},{'artifact_version':3}])
def test_source_must_match_term_and_retained_version(change):
    value=body();value['resolution']['source'].update(change)
    with pytest.raises(ValidationError):ContractDeadlineResolutionRequest.model_validate(value)


def test_changed_date_is_an_amendment_not_an_interpretation():
    value=body();value['resolution'].update(calendar_date='2026-11-21',resolved_instant='2026-11-21T17:00:00-06:00')
    assessment=assess_deadline_resolution(ContractDeadlineResolutionRequest.model_validate(value),terms(),current_version=2)
    assert assessment['reason_codes']==['ORIGINAL_DATE_CHANGED_REQUIRES_AMENDMENT']
    assert assessment['status']=='requires_review'


@pytest.mark.parametrize('original,reason',[
    ({'precision':'unknown'},'ORIGINAL_DATE_REQUIRED'),
    ({'precision':'instant','instant':'2026-11-20T17:00:00-06:00'},'TERM_ALREADY_HAS_EXPLICIT_INSTANT'),
])
def test_resolution_cannot_fill_an_unknown_date_or_replace_an_explicit_instant(original,reason):
    prepared=terms().model_dump(mode='json');prepared['closing_deadline']=original
    assessment=assess_deadline_resolution(ContractDeadlineResolutionRequest.model_validate(body()),ContractTermsDraft.model_validate(prepared),current_version=2)
    assert assessment['reason_codes']==[reason]


def test_stale_version_remains_held_and_actor_assertions_are_rejected():
    request=ContractDeadlineResolutionRequest.model_validate(body())
    assert assess_deadline_resolution(request,terms(),current_version=3)['reason_codes']==['CONTRACT_VERSION_CHANGED']
    for field in ('workspace_id','actor_id','approved_by','policy_id','execution_authorized'):
        value=deepcopy(body());value[field]=str(UUID(int=3))
        with pytest.raises(ValidationError):ContractDeadlineResolutionRequest.model_validate(value)
