from copy import deepcopy
import pytest
from pydantic import ValidationError
from schemas.acquisition_contract_terms import ContractDateTerm, ContractTermsDraft, ContractTermsRequest
from tools.acquisition_contract_terms import assess_contract_terms

UID='af000000-0000-4000-8000-000000000001'
def terms():
    return {'purchase_price_cents':14000000,'earnest_money_cents':100000,'assignment_allowed':True,
        'assignment_provisions':'Synthetic provision expressly permitting assignment, for structural testing only.',
        'effective':{'precision':'instant','instant':'2026-10-31T12:00:00-05:00'},
        'inspection_deadline':{'precision':'instant','instant':'2026-11-05T17:00:00-06:00'},
        'closing_deadline':{'precision':'instant','instant':'2026-11-30T17:00:00-06:00'},
        'sources':[{'term':name,'artifact_id':UID,'artifact_version':1,'sha256':'a'*64,'locator':'Page 1, synthetic '+name}
                   for name in ('purchase_price','earnest_money','assignment','effective','inspection_deadline','closing_deadline')],
        'note':'Synthetic terms prepared from explicitly identified original clauses.'}


def test_complete_terms_remain_unverified_and_non_executing():
    value=ContractTermsRequest(id=UID,expected_version=1,terms=terms())
    result=assess_contract_terms(value.terms)
    assert result['status']=='ready_for_review' and result['source_verification_required']
    assert not result['legal_review_approved'] and not result['execution_authorized']
    assert value.terms.effective.instant.utcoffset().total_seconds()==-18000


def test_unknown_money_and_dates_never_become_zero_or_inferred_instants():
    value=terms();value.update(purchase_price_cents=None,earnest_money_cents=None,assignment_allowed=None,assignment_provisions=None,sources=[])
    for name in ('effective','inspection_deadline','closing_deadline'):value[name]={'precision':'unknown'}
    parsed=ContractTermsDraft.model_validate(value);result=assess_contract_terms(parsed)
    assert parsed.purchase_price_cents is None and parsed.earnest_money_cents is None
    assert len(result['reason_codes'])==6 and result['status']=='requires_review'

@pytest.mark.parametrize('value',[{'precision':'unknown','calendar_date':'2026-10-31'},
    {'precision':'date','calendar_date':'2026-10-31T12:00:00Z'}, {'precision':'date','calendar_date':123},
    {'precision':'instant','instant':'2026-10-31'}, {'precision':'instant','instant':'2026-10-31T12:00:00'},
    {'precision':'instant','instant':1790000000}, {'precision':'date','calendar_date':'2026-10-31','instant':'2026-10-31T12:00:00Z'}])
def test_rejects_inferred_or_conflicting_date_precision(value):
    with pytest.raises(ValidationError):ContractDateTerm.model_validate(value)

@pytest.mark.parametrize('change',[{'purchase_price_cents':True},{'purchase_price_cents':140000.50},
    {'purchase_price_cents':'14000000'},{'earnest_money_cents':-1},{'assignment_allowed':'true'},
    {'assignment_provisions':None},{'sources':[]},{'execution_authorized':True},{'note':' '*20}])
def test_terms_reject_coercions_missing_sources_and_authority_claims(change):
    with pytest.raises(ValidationError):ContractTermsDraft.model_validate(terms()|change)


def test_date_only_preserved_and_contradictions_require_review():
    value=terms();value['effective']={'precision':'date','calendar_date':'2026-12-01'}
    value['closing_deadline']={'precision':'date','calendar_date':'2026-11-30'}
    parsed=ContractTermsDraft.model_validate(value);result=assess_contract_terms(parsed)
    assert parsed.effective.instant is None
    assert parsed.model_dump(mode='json')['effective']['calendar_date']=='2026-12-01'
    assert 'EFFECTIVE_TIME_REQUIRES_REVIEW' in result['reason_codes']
    assert 'TERM_DATE_ORDER_REQUIRES_REVIEW' in result['reason_codes']


def test_duplicate_sources_and_future_source_versions_rejected():
    value=terms();value['sources'][1]=deepcopy(value['sources'][0])
    with pytest.raises(ValidationError):ContractTermsDraft.model_validate(value)
    value=terms();value['sources'][0]['artifact_version']=2
    with pytest.raises(ValidationError):ContractTermsRequest(id=UID,expected_version=1,terms=value)


def test_zero_earnest_is_distinct_from_missing_and_excess_needs_review():
    value=terms()|{'earnest_money_cents':0}
    assert 'EARNEST_MONEY_MISSING' not in assess_contract_terms(ContractTermsDraft.model_validate(value))['reason_codes']
    value['earnest_money_cents']=15000000
    assert 'EARNEST_MONEY_EXCEEDS_PURCHASE_PRICE' in assess_contract_terms(ContractTermsDraft.model_validate(value))['reason_codes']
