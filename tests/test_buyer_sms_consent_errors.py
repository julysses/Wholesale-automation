"""The deployed PostgREST adapter must preserve missing-buyer semantics."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError
from web.api.buyer_sms_consent import status

@pytest.mark.parametrize('code,expected',[('P0002',404),('42501',503),('XX000',503)])
def test_postgrest_consent_failure_is_not_reported_as_no_consent(code,expected):
    error=APIError({'code':code,'message':'Synthetic database error','details':None,'hint':None})
    def execute():raise error
    db=SimpleNamespace(rpc=lambda *_args:SimpleNamespace(execute=execute))
    with pytest.raises(HTTPException) as result:status(db,uuid4(),str(uuid4()))
    assert result.value.status_code==expected
