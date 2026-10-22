"""A saved change must not be acknowledged from another buyer's receipt."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from web.api import buyer_mutations as changes

@pytest.mark.parametrize('bad', [None, {'id':'request','state':'updated','kind':'update','buyer_id':'other','buyer':{'id':'other'},'transaction_count':0,'current_exists':True}, {'id':'request','state':'updated','kind':'update','buyer_id':'buyer','buyer':None,'transaction_count':0,'current_exists':True}])
def test_uncorrelated_saved_change_is_unconfirmed(bad):
    db=SimpleNamespace(rpc=lambda *args:SimpleNamespace(execute=lambda:SimpleNamespace(data=bad)))
    with patch.object(changes,'get_supabase_client',return_value=db),pytest.raises(HTTPException) as error:
        changes.execute('mutate_buyer',{'p_id':'request','p_operator':'operator','p_buyer':'buyer','p_kind':'update'})
    assert error.value.status_code==503


def test_omitted_profile_fields_cannot_silently_reset_existing_values():
    from pydantic import ValidationError
    with pytest.raises(ValidationError,match='all editable profile fields'):
        changes.Mutation(request_id='00000000-0000-4000-8000-000000000001',buyer_id='00000000-0000-4000-8000-000000000002',kind='update',expected={'id':'00000000-0000-4000-8000-000000000002'},updates={'first_name':'Synthetic','last_name':'Buyer','notes':'Only a note'})
