from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError
from schemas.acquisition_underwriting import UnderwritingPreview
from tools.acquisition_underwriting import calculate_preview


def fact(value):
    return {'value':str(value) if value is not None else None,'source':'synthetic fixture',
            'basis':'estimate','confidence':'medium','as_of':'2026-01-01'}


def flip():
    values={'purchase_price':150000,'acquisition_closing':3000,'liens':2000,'holding_months':6,
            'holding_monthly_ex_interest':500,'offer_floor_fraction':'.9','arv':300000,'repairs':30000,
            'contingency':3000,'selling_rate':'.06','selling_fixed':2000,'target_profit':40000}
    return {'strategy':'fix_and_flip',**{k:fact(v) for k,v in values.items()},'financing':{
        k:fact(v) for k,v in {'principal':120000,'average_balance':120000,'annual_rate':'.12','points_rate':'.02','other_fees':500}.items()}}


def rental():
    case=flip()
    for key in ['arv','selling_rate','selling_fixed','target_profit']:
        del case[key]
    values={'market_value':250000,'holding_months':0,'monthly_rent':2500,'vacancy_rate':'.05',
            'property_tax_annual':3000,'insurance_annual':1000,'maintenance_annual':1000,'utilities_annual':0,
            'hoa_annual':0,'other_operating_annual':0,'management_rate':'.1','capital_reserve_annual':1000,
            'target_cap_rate':'.08','target_cash_on_cash':'.1'}
    case.update({k:fact(v) for k,v in values.items()})
    case.update(strategy='rental',amortization_months=0)
    case['financing']['annual_rate']=fact('.06')
    return case


def preview(case, **kw):
    return calculate_preview(UnderwritingPreview.model_validate({'cases':{name:deepcopy(case) for name in ['base','downside','upside']},**kw}))


def test_flip_explicit_costs_do_not_double_count_principal_or_interest():
    result=preview(flip())
    base=result['cases']['base']
    assert base['mao']=='188900.00'
    assert base['metrics']['profit']=='78900.00'
    assert base['metrics']['total_project_cost']=='221100.00'
    assert base['metrics']['net_project_cash_required']=='101100.00'
    assert base['cost_breakdown']['financing_interest']=='7200.00'
    assert base['cost_breakdown']['financing_points']=='2400.00'
    assert base['proposed_offer_range']=={'low':'170010.00','high':'188900.00'}
    assert base['viable'] is True
    assert result['human_approval_required'] is True and result['binding_offer'] is False
    assert result['persisted'] is False
    assert result['inputs']['cases']['base']['arv']['source']=='synthetic fixture'


@pytest.mark.parametrize('missing',['arv','repairs','liens','financing'])
def test_missing_inputs_never_silently_become_zero(missing):
    case=flip(); del case[missing]
    base=preview(case)['cases']['base']
    assert base['status']=='incomplete'
    assert base['mao'] is None and base['viable'] is None
    assert base['proposed_offer_range'] is None
    assert any(key.startswith(missing) for key in base['missing_inputs'])
    assert base['confidence']=='low'


def test_null_and_explicit_zero_have_different_meanings():
    case=flip();case['liens']=fact(None)
    assert preview(case)['cases']['base']['mao'] is None
    case['liens']=fact(0)
    assert preview(case)['cases']['base']['mao']=='190900.00'


@pytest.mark.parametrize('field,value',[('arv','NaN'),('arv','Infinity'),('repairs',-1),('selling_rate','1.01'),('arv','1.001')])
def test_invalid_money_and_rates_are_rejected(field,value):
    case=flip();case[field]=fact(value)
    with pytest.raises(ValidationError):preview(case)


def test_loan_average_cannot_exceed_principal_and_unexpected_cost_bucket_rejected():
    case=flip();case['financing']['average_balance']=fact(120001)
    with pytest.raises(ValidationError):preview(case)
    case=flip();case['other_costs']=fact(100)
    with pytest.raises(ValidationError):preview(case)


def test_negative_mao_is_visible_and_produces_no_offer():
    case=flip();case['arv']=fact(50000)
    base=preview(case)['cases']['base']
    assert Decimal(base['mao'])<0 and base['proposed_offer_range'] is None
    assert base['viable'] is False


def test_rental_noi_excludes_debt_and_reserves_but_cashflow_includes_them():
    base=preview(rental())['cases']['base']
    assert base['metrics']['noi_annual']=='20650.00'
    assert base['metrics']['debt_service_annual']=='7200.00'
    assert base['metrics']['cashflow_annual']=='12450.00'
    assert base['metrics']['total_project_basis']=='190900.00'
    assert base['metrics']['cap_rate_ceiling']=='217225.00'
    assert base['metrics']['cash_on_cash_ceiling']=='203600.00'
    assert base['metrics']['market_value_ceiling']=='209100.00'
    assert base['mao']=='203600.00'
    assert base['viable'] is True


def test_amortizing_rental_uses_principal_and_interest_payment():
    case=rental();case['amortization_months']=360
    base=preview(case)['cases']['base']
    assert base['metrics']['debt_service_annual']=='8633.53'
    assert base['metrics']['cashflow_annual']=='11016.47'
    case['financing']['annual_rate']=fact(0)
    assert preview(case)['cases']['base']['metrics']['debt_service_annual']=='4000.00'
    case['amortization_months']=6
    with pytest.raises(ValidationError):preview(case)


def test_rental_zero_targets_are_not_division_by_zero_defaults():
    case=rental();case['target_cap_rate']=fact(0)
    with pytest.raises(ValidationError):preview(case)


def test_development_breaks_out_construction_soft_costs_and_financing():
    case=flip()
    for key in ['arv','repairs']:
        del case[key]
    values={'purchase_price':200000,'completed_value':1000000,'hard_costs':400000,'soft_costs':60000,
            'infrastructure':20000,'permits':10000,'contingency':40000,'acquisition_closing':6000,'liens':0,
            'holding_months':12,'holding_monthly_ex_interest':2000,'selling_fixed':8000,'target_profit':150000}
    case.update({k:fact(v) for k,v in values.items()});case['strategy']='development'
    case['financing']={k:fact(v) for k,v in {'principal':500000,'average_balance':300000,'annual_rate':'.1','points_rate':'.02','other_fees':2000}.items()}
    base=preview(case)['cases']['base']
    assert sum(Decimal(value) for value in base['cost_breakdown'].values()) == Decimal('670000')
    assert base['mao']=='180000.00'
    assert base['metrics']['profit']=='130000.00'
    assert base['viable'] is False
    assert base['cost_breakdown']['financing_interest']=='30000.00'


def assignment():
    return {'strategy':'wholesale','contract_price':fact(130000),'end_buyer_price':fact(150000),
            'assignment_expenses':fact(2000),'target_net_fee':fact(15000),'offer_floor_fraction':fact('.9'),'buyer_case':flip()}


def test_assignment_preserves_gross_vs_net_and_independent_buyer_price_limit():
    base=preview(assignment())['cases']['base']
    assert base['metrics']['gross_assignment_spread']=='20000.00'
    assert base['metrics']['net_assignment_proceeds']=='18000.00'
    assert base['mao']=='133000.00' and base['viable'] is True
    case=assignment();case['buyer_case']['arv']=fact(240000)
    base=preview(case)['cases']['base']
    assert base['metrics']['gross_assignment_spread']=='20000.00'
    assert base['viable'] is False and base['proposed_offer_range'] is None
    assert 'END_BUYER_ECONOMICS_DO_NOT_SUPPORT_PROPOSED_PRICE' in base['warnings']


def test_assignment_does_not_invent_buyer_economics_or_accept_mismatched_price():
    case=assignment();del case['buyer_case']['arv']
    base=preview(case)['cases']['base']
    assert base['metrics']['gross_assignment_spread']=='20000.00'
    assert base['mao'] is None and 'buyer_case.arv' in base['missing_inputs']
    case=assignment();case['end_buyer_price']=fact(151000)
    with pytest.raises(ValidationError):preview(case)


def test_case_set_and_provenance_are_required():
    with pytest.raises(ValidationError):UnderwritingPreview.model_validate({'cases':{'base':flip()}})
    case=flip();case['arv']['source']=''
    with pytest.raises(ValidationError):preview(case)
    case=flip();case['arv']['basis']='verified'
    with pytest.raises(ValidationError):preview(case)


def test_offer_ceiling_never_rounds_above_exact_mao():
    case=flip();case['selling_rate']=fact('.06000001')
    base=preview(case)['cases']['base']
    assert base['mao']=='188899.99'  # Exact ceiling is 188899.997.


def test_explicit_downside_and_upside_are_calculated_without_synthetic_market_data():
    base=flip();down=deepcopy(base);up=deepcopy(base)
    down['arv']=fact(240000);up['arv']=fact(330000)
    result=calculate_preview(UnderwritingPreview.model_validate({'cases':{'base':base,'downside':down,'upside':up}}))
    assert result['cases']['downside']['mao']=='132500.00'
    assert result['cases']['upside']['mao']=='217100.00'
    assert result['cases']['base']['mao']=='188900.00'


def test_nonpositive_net_cash_suppresses_offer_range_and_roi():
    case=flip();case['financing']['principal']=fact(500000)
    base=preview(case)['cases']['base']
    assert base['viable'] is False
    assert base['metrics']['profit_on_net_cash'] is None
    assert base['proposed_offer_range'] is None


def test_case_labels_do_not_hide_optimistic_downside():
    base=flip();down=deepcopy(base);down['arv']=fact(400000)
    result=calculate_preview(UnderwritingPreview.model_validate({'cases':{'base':base,'downside':down,'upside':base}}))
    assert result['case_order_consistent'] is False
    assert result['warnings']==['CASE_LABEL_ORDER_REQUIRES_REVIEW']
