from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.test_webhook_completion_delivery import MemoryDB
from tools.operational_alerts import record_provider_alert
from web.api import operations_api as operations
from web import auth
from web.app import app


def test_alert_is_durable_deduplicated_and_preserves_operator_read():
    db=MemoryDB(); reference=str(uuid4())
    first=record_provider_alert(db,'sendgrid',reference,'bounce')
    db.tables['app_notifications'][first]['read']=True
    assert record_provider_alert(db,'sendgrid',reference,'bounce')==first
    assert len(db.tables['app_notifications'])==1
    row=db.tables['app_notifications'][first]
    assert row['read'] is True
    assert row['recipient_role']=='admin'
    assert row['metadata']['integration_failure'] is True
    assert 'Do not resend' in row['body']


def test_unconfirmed_alert_does_not_report_success():
    db=MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data=[]
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
    with pytest.raises(RuntimeError):record_provider_alert(db,'twilio','tracked-reference','failed')


def test_in_app_drill_does_not_construct_external_providers(monkeypatch):
    db=MemoryDB()
    monkeypatch.setattr(operations,'get_supabase_client',lambda:db)
    reference=uuid4()
    first=operations.test_alert(reference)
    assert operations.test_alert(reference)==first
    assert len(db.tables['app_notifications'])==1
    row=db.tables['app_notifications'][first['notification_id']]
    assert row['title']=='TEST — launch failure alert'
    assert row['metadata']['test_drill'] is True
    assert 'No external message' in row['body']


def test_drill_requires_storage(monkeypatch):
    monkeypatch.setattr(operations,'get_supabase_client',lambda:None)
    with pytest.raises(HTTPException) as error:operations.test_alert(uuid4())
    assert error.value.status_code==503


@pytest.mark.parametrize('role,expected',[('user',403),('admin',200)])
def test_drill_only_approved_admin(role,expected,monkeypatch):
    identity=MagicMock()
    identity.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id='operator-1'))
    identity.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'status':'approved','role':role}]
    monkeypatch.setattr(auth,'get_supabase_client',lambda:identity)
    monkeypatch.setattr(operations,'get_supabase_client',lambda:MemoryDB())
    client=TestClient(app)
    assert client.post('/api/operations/test-alert',json={'request_id':str(uuid4())}).status_code==401
    response=client.post('/api/operations/test-alert',headers={'Authorization':'Bearer valid'},json={'request_id':str(uuid4())})
    assert response.status_code==expected
