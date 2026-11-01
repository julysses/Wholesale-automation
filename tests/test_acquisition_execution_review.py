from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from schemas.acquisition_contract_terms import ContractTermsDraft
from schemas.acquisition_execution_review import ExecutionFindings, ExecutionReviewRequest
from tools.acquisition_execution_review import assess_execution_findings
from tests.test_acquisition_contract_terms import terms, UID

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
NAMES = ('seller_signatures', 'buyer_signatures', 'signing_authority', 'complete_agreement')


def findings():
    return {**{name: {'finding': 'confirmed', 'locator': 'Page 4, synthetic signature section',
                     'note': 'Synthetic human finding for isolated structural tests.'} for name in NAMES},
            'terms': terms()}


def request():
    return {'id': UID, 'expected_sequence': 0, 'expected_version': 1, 'status': 'approved',
            'artifact_id': UID, 'verification_id': UID, 'policy_id': UID,
            'expires_at': '2026-11-01T01:00:00Z', 'personally_reviewed': True,
            'note': 'Synthetic execution review with original document references.', 'findings': findings()}


def assess(value=None, prepared=None):
    return assess_execution_findings(ExecutionFindings.model_validate(value or findings()),
                                    ContractTermsDraft.model_validate(prepared or terms()), now=NOW)


def test_complete_findings_only_prepare_review_and_preserve_exact_payload():
    data=request(); parsed=ExecutionReviewRequest.model_validate(data)
    assert ExecutionReviewRequest.model_validate(parsed.model_dump(mode='json')) == parsed
    assert parsed.note == data['note']
    assert parsed.findings.seller_signatures.locator == data['findings']['seller_signatures']['locator']
    result=assess()
    assert result['status']=='ready_for_review'
    assert not result['legal_review_approved'] and not result['execution_authorized']
    assert result['source_verification_required']


@pytest.mark.parametrize('name',NAMES)
@pytest.mark.parametrize('state',['unknown','not_confirmed'])
def test_missing_or_negative_findings_hold_and_cannot_be_approved(name,state):
    value=findings();value[name]['finding']=state
    assert name.upper()+'_REQUIRES_REVIEW' in assess(value)['reason_codes']
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(request()|{'findings':value})


@pytest.mark.parametrize('change',[{'expected_version':True}, {'findings':None},
    {'execution_authorized':True}, {'personally_reviewed':False}, {'reviewed_by':UID}])
def test_rejects_approval_coercions_omissions_and_authority_overrides(change):
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(request()|change)


def test_withdrawal_preserves_original_instead_of_replacing_findings():
    data=request()|{'status':'withdrawn','personally_reviewed':False,'expires_at':None}
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(data)
    assert ExecutionReviewRequest.model_validate(data|{'findings':None}).findings is None


def test_signed_terms_changes_require_review_and_do_not_mutate_prepared_terms():
    prepared=terms();before=deepcopy(prepared);value=findings()
    value['terms']['purchase_price_cents']+=1
    result=assess(value,prepared)
    assert result['changed_terms']==['purchase_price_cents']
    assert 'RETURNED_TERMS_DIFFER_FROM_REVIEWED_VERSION' in result['reason_codes']
    assert prepared==before


def test_known_values_cannot_be_erased_but_unknown_prepared_values_can_be_supplied():
    value=findings();value['terms']['earnest_money_cents']=None
    result=assess(value)
    assert 'earnest_money_cents' in result['changed_terms'] and 'EARNEST_MONEY_MISSING' in result['reason_codes']
    prepared=terms();prepared['earnest_money_cents']=None
    assert assess(prepared=prepared)['changed_terms']==[]


def test_date_precision_remains_source_precision_without_inferred_midnight():
    value=findings();value['terms']['effective']={'precision':'date','calendar_date':'2026-10-31'}
    parsed=ExecutionFindings.model_validate(value)
    assert parsed.terms.effective.instant is None
    result=assess(value)
    assert 'EFFECTIVE_TIME_REQUIRES_REVIEW' in result['reason_codes']
    assert 'effective' in result['changed_terms']


def test_future_effective_and_elapsed_closing_hold_without_fabricated_extension():
    value=findings();value['terms']['effective']['instant']='2026-11-02T12:00:00Z'
    value['terms']['closing_deadline']['instant']='2026-10-31T12:00:00Z'
    result=assess(value)
    assert {'EFFECTIVE_TIME_NOT_REACHED','CLOSING_DEADLINE_PASSED'} <= set(result['reason_codes'])


def test_sources_and_citations_are_required_and_future_versions_rejected():
    data=request();data['findings']['terms']['sources'][0]['artifact_version']=2
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(data)
    data=request();data['findings']['seller_signatures']['locator']='   '
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(data)
    data=request();data['findings']['terms']['sources']=[]
    with pytest.raises(ValidationError):ExecutionReviewRequest.model_validate(data)


def test_assessment_rejects_implicit_current_timezone():
    with pytest.raises(ValueError):
        assess_execution_findings(ExecutionFindings.model_validate(findings()),
            ContractTermsDraft.model_validate(terms()),now=datetime(2026,11,1))
