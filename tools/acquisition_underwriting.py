"""Deterministic investment arithmetic, with no market lookup or offer execution.

Prices/costs remain input assumptions. All debt is a fixed supplied principal,
not a percentage that silently changes with the calculated offer. Interest and
points appear once; debt principal is never treated as an expense.
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, localcontext

from pydantic import BaseModel
from schemas.acquisition_underwriting import Assumption, Assignment, Rental, UnderwritingPreview

CALCULATION_VERSION = 'acquisition-underwriting-v1'
D = Decimal


def money(value):
    return None if value is None else str(value.quantize(D('.01'),rounding=ROUND_HALF_UP))


def ratio(value):
    return None if value is None else str(value.quantize(D('.000001'),rounding=ROUND_HALF_UP))


def _facts(model, prefix=''):
    found={}
    for name in type(model).model_fields:
        value=getattr(model,name)
        path=prefix+name
        if isinstance(value,Assumption):
            found[path]=value
        elif isinstance(value,BaseModel):
            found.update(_facts(value,path+'.'))
    return found


def _get(model,path):
    value=model
    for part in path.split('.'):
        value=getattr(value,part)
        if value is None:
            return None
    return value.value if isinstance(value,Assumption) else value


def _result(case,required):
    missing=[name for name in required if _get(case,name) is None]
    facts=_facts(case)
    order={'low':0,'medium':1,'high':2}
    confidence=min((v.confidence for v in facts.values() if v.value is not None),key=order.get,default='low')
    return {'status':'incomplete' if missing else 'calculated','missing_inputs':missing,
            'confidence':'low' if missing else confidence,'contains_estimates':any(v.basis=='estimate' for v in facts.values()),
            'fact_status':'inputs_not_independently_verified','viable':None,'mao':None,
            'proposed_offer_range':None,'warnings':[],'cost_breakdown':{},'metrics':{}}


COMMON = ['purchase_price','acquisition_closing','liens','holding_months','holding_monthly_ex_interest',
          'financing.principal','financing.average_balance','financing.annual_rate','financing.points_rate',
          'financing.other_fees','offer_floor_fraction']


def _costs(case):
    get=lambda key:_get(case,key)
    return {'acquisition_closing':get('acquisition_closing'),'liens':get('liens'),
            'holding_ex_interest':get('holding_months')*get('holding_monthly_ex_interest'),
            'financing_interest':get('financing.average_balance')*get('financing.annual_rate')*get('holding_months')/12,
            'financing_points':get('financing.principal')*get('financing.points_rate'),
            'financing_other_fees':get('financing.other_fees')}


def _offer(result,mao,floor):
    ceiling=mao.quantize(D('.01'),rounding=ROUND_FLOOR)
    result['mao']=str(ceiling)
    if ceiling>0:
        result['proposed_offer_range']={'low':str((ceiling*floor).quantize(D('.01'),rounding=ROUND_FLOOR)),'high':str(ceiling)}
    else:
        result['warnings'].append('NO_POSITIVE_OFFER_SUPPORTED')
        result['viable']=False
    if 'NONPOSITIVE_NET_CASH_REQUIRES_FINANCING_REVIEW' in result['warnings']:
        result['proposed_offer_range']=None


def _sale(case):
    flip=case.strategy=='fix_and_flip'
    value_key='arv' if flip else 'completed_value'
    work=['repairs','contingency'] if flip else ['hard_costs','soft_costs','infrastructure','permits','contingency']
    required=COMMON+[value_key,'selling_rate','selling_fixed','target_profit']+work
    result=_result(case,required)
    if result['missing_inputs']:
        return result
    get=lambda key:_get(case,key)
    costs=_costs(case)
    costs.update({key:get(key) for key in work})
    exit_value=get(value_key)
    costs['selling_variable']=exit_value*get('selling_rate')
    costs['selling_fixed']=get('selling_fixed')
    other=sum(costs.values(),D(0))
    total=get('purchase_price')+other
    profit=exit_value-total
    mao=exit_value-other-get('target_profit')
    equity=total-get('financing.principal')
    result['cost_breakdown']={key:money(value) for key,value in costs.items()}
    result['metrics']={'exit_value':money(exit_value),'total_project_cost':money(total),'profit':money(profit),
                       'net_project_cash_required':money(equity),
                       'profit_on_project_cost':ratio(profit/total) if total>0 else None,
                       'profit_on_net_cash':ratio(profit/equity) if equity>0 else None,
                       'profit_margin':ratio(profit/exit_value) if exit_value>0 else None}
    if equity<=0:
        result['warnings'].append('NONPOSITIVE_NET_CASH_REQUIRES_FINANCING_REVIEW')
    result['warnings'].append('CASH_TIMING_AND_PEAK_FUNDING_NOT_MODELED')
    result['viable']=mao>0 and get('purchase_price')<=mao and equity>0
    _offer(result,mao,get('offer_floor_fraction'))
    return result


RENTAL_FIELDS=['market_value','repairs','contingency','monthly_rent','vacancy_rate','property_tax_annual','insurance_annual',
               'maintenance_annual','utilities_annual','hoa_annual','other_operating_annual','management_rate',
               'capital_reserve_annual','amortization_months','target_cap_rate','target_cash_on_cash']


def _rental(case):
    result=_result(case,COMMON+RENTAL_FIELDS)
    if result['missing_inputs']:
        return result
    get=lambda key:_get(case,key)
    costs=_costs(case)  # Holding/interest here cover only the pre-stabilization period.
    costs.update(repairs=get('repairs'),contingency=get('contingency'))
    upfront=sum(costs.values(),D(0))
    gross=get('monthly_rent')*12
    effective=gross*(1-get('vacancy_rate'))
    operating={key:get(key) for key in ['property_tax_annual','insurance_annual','maintenance_annual',
                                      'utilities_annual','hoa_annual','other_operating_annual']}
    operating['management_annual']=effective*get('management_rate')
    noi=effective-sum(operating.values(),D(0))
    principal=get('financing.principal')
    monthly_rate=get('financing.annual_rate')/12
    term=case.amortization_months
    if term==0:
        debt=principal*get('financing.annual_rate')
    elif monthly_rate==0:
        debt=principal/D(term)*12
    else:
        factor=(1+monthly_rate)**term
        debt=principal*monthly_rate*factor/(factor-1)*12
    cashflow=noi-get('capital_reserve_annual')-debt
    basis=get('purchase_price')+upfront
    equity=basis-principal
    ceilings={'cap_rate_ceiling':noi/get('target_cap_rate')-upfront,
              'cash_on_cash_ceiling':cashflow/get('target_cash_on_cash')+principal-upfront,
              'market_value_ceiling':get('market_value')-upfront}
    mao=min(ceilings.values())
    result['cost_breakdown']={key:money(value) for key,value in costs.items()}
    result['annual_operating_breakdown']={key:money(value) for key,value in operating.items()}
    result['metrics']={'gross_rent_annual':money(gross),'effective_rent_annual':money(effective),'noi_annual':money(noi),
                       'capital_reserve_annual':money(get('capital_reserve_annual')),'debt_service_annual':money(debt),
                       'cashflow_annual':money(cashflow),'total_project_basis':money(basis),'net_project_cash_required':money(equity),
                       'cap_rate_on_cost':ratio(noi/basis) if basis>0 else None,
                       'cash_on_cash':ratio(cashflow/equity) if equity>0 else None,
                       'debt_service_coverage':ratio(noi/debt) if debt>0 else None,
                       'equity_at_market_value':money(get('market_value')-principal),
                       **{key:money(value) for key,value in ceilings.items()}}
    result['viable']=mao>0 and get('purchase_price')<=mao and cashflow>0 and equity>0
    result['warnings'].append('STABILIZED_YEAR_ONLY_NO_REFINANCE_OR_EXIT_MODELED')
    if equity<=0:
        result['warnings'].append('NONPOSITIVE_NET_CASH_REQUIRES_FINANCING_REVIEW')
    _offer(result,mao,get('offer_floor_fraction'))
    return result


def _assignment(case):
    required=['contract_price','end_buyer_price','assignment_expenses','target_net_fee','offer_floor_fraction']
    result=_result(case,required)
    buyer=_calculate(case.buyer_case)
    result['buyer_economics']=buyer
    buy=_get(case,'end_buyer_price'); contract=_get(case,'contract_price'); expenses=_get(case,'assignment_expenses')
    gross=buy-contract if buy is not None and contract is not None else None
    result['metrics']={'gross_assignment_spread':money(gross),
                       'net_assignment_proceeds':money(gross-expenses) if gross is not None and expenses is not None else None}
    result['missing_inputs']+=['buyer_case.'+key for key in buyer['missing_inputs']]
    if result['missing_inputs']:
        result['status']='incomplete'
        result['confidence']='low'
        return result
    supported=min(buy,D(buyer['mao']))
    mao=supported-expenses-_get(case,'target_net_fee')
    result['metrics']['buyer_supported_price']=money(supported)
    result['cost_breakdown']={'assignment_expenses':money(expenses)}
    _offer(result,mao,_get(case,'offer_floor_fraction'))
    result['viable']=buyer['viable'] is True and mao>0 and contract<=mao
    if not buyer['viable']:
        result['warnings'].append('END_BUYER_ECONOMICS_DO_NOT_SUPPORT_PROPOSED_PRICE')
        result['proposed_offer_range']=None
    result['warnings'].append('ASSIGNABILITY_TITLE_AND_DISCLOSURES_REQUIRE_REVIEW')
    return result


def _calculate(case):
    if isinstance(case,Assignment):
        return _assignment(case)
    if isinstance(case,Rental):
        return _rental(case)
    return _sale(case)


def calculate_preview(request: UnderwritingPreview):
    with localcontext() as context:
        context.prec=40
        cases={name:_calculate(case) for name,case in request.cases.items()}
    metric={'fix_and_flip':'profit','development':'profit','rental':'cashflow_annual','wholesale':'net_assignment_proceeds'}[request.cases['base'].strategy]
    values=[cases[name]['metrics'].get(metric) for name in ('downside','base','upside')]
    ordered=None if any(value is None for value in values) else D(values[0])<=D(values[1])<=D(values[2])
    return {'calculation_version':CALCULATION_VERSION,'strategy':request.cases['base'].strategy,
            'status':'incomplete' if any(case['status']=='incomplete' for case in cases.values()) else 'calculated',
            'rounding_policy':'unrounded_calculations_display_half_up_offer_ceilings_floor',
            'financing_assumptions':['simple_interest_on_supplied_average_balance','points_on_supplied_principal',
                                     'rental_amortization_begins_after_interest_only_stabilization_period'],
            'financing_warning':'Fixed debt inputs require re-underwriting for a changed purchase price; peak funding is not modeled',
            'case_order_consistent':ordered,'warnings':['CASE_LABEL_ORDER_REQUIRES_REVIEW'] if ordered is False else [],
            'binding_offer':False,'human_approval_required':True,'persisted':False,
            'uncertainties':request.uncertainties,'inputs':request.model_dump(mode='json'),'cases':cases}
