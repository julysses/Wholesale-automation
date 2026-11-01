"""Buyer inputs preserve unknowns and cannot claim verification or sending authority."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from schemas.acquisition_buyers import AcquisitionBuyerDetails, AcquisitionBuyerRequest, AcquisitionBuyerReceipt


def details(**changes):
    return dict(first_name='Example',last_name='Buyer',target_zips=['75001'],property_types=['SFR'],
                strategies=['fix_flip'],active=True,source_note='Details supplied by buyer for review.',**changes)


@pytest.mark.parametrize('changes',[
    {'pof_verified':True},{'sms_opt_in':True},{'workspace_id':str(uuid4())},
    {'min_price_cents':True},{'max_price_cents':'10000'},{'max_repairs_cents':-1},
    {'phone':'2145550100'},{'email':'Buyer@Example.test'},{'email':'a@b'},
    {'company':'  Company  '},{'first_name':'Test\x00Name'},
    {'target_zips':['75001','75001']},{'target_zips':[75001]},
    {'min_price_cents':200,'max_price_cents':100},{'close_speed_days':False},
])
def test_rejects_injected_authority_and_ambiguous_details(changes):
    with pytest.raises(ValidationError):AcquisitionBuyerDetails.model_validate(details()|changes)


def test_missing_economics_stay_unknown_and_explicit_zero_stays_zero():
    value=AcquisitionBuyerDetails.model_validate(details())
    assert value.min_price_cents is None and value.max_price_cents is None and value.max_repairs_cents is None
    assert AcquisitionBuyerDetails.model_validate(details(min_price_cents=0)).min_price_cents==0


def test_receipt_binds_exact_request_workspace_and_historical_revision():
    workspace=uuid4();request=AcquisitionBuyerRequest(id=uuid4(),buyer_id=uuid4(),expected_revision=2,details=details())
    data=dict(request_id=request.id,workspace_id=workspace,buyer_id=request.buyer_id,revision=3,
              details=request.details,duplicate=True,profile_recorded=True,buyer_verified=False,
              contact_authorized=False,execution_authorized=False)
    receipt=AcquisitionBuyerReceipt.model_validate(data)
    assert receipt.confirms(request,workspace)
    assert not receipt.confirms(request,uuid4())
    assert not receipt.confirms(request.model_copy(update={'expected_revision':3}),workspace)
    changed=request.model_copy(update={'details':AcquisitionBuyerDetails.model_validate(details(company='Different company'))})
    assert not receipt.confirms(changed,workspace)
    for field in ('buyer_verified','contact_authorized','execution_authorized'):
        with pytest.raises(ValidationError):AcquisitionBuyerReceipt.model_validate(data|{field:True})


@pytest.mark.parametrize('revision',[True,-1,'0',2147483647])
def test_revision_must_be_exact_nonnegative_integer(revision):
    with pytest.raises(ValidationError):AcquisitionBuyerRequest(id=uuid4(),buyer_id=uuid4(),expected_revision=revision,details=details())
