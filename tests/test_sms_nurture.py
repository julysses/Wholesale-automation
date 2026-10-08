from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tests.test_backend_launch_contracts import Database, Table
from web.api import nurture_api as n

PHONE = '+12147010100'
class Query(Table):
    def lt(self, key, value):
        self.filters.append(lambda row: row.get(key, '') < value)
        return self
    def gte(self, key, value):
        self.filters.append(lambda row: row.get(key, '') >= value)
        return self
class DB(Database):
    def table(self, name): return Query(self,name)
    def rpc(self, name, args):
        assert name == 'claim_sms_nurture'
        rows = [r for r in self.tables['sms_nurture_jobs'] if r['status']=='scheduled'][:args['p_limit']]
        for row in rows:
            row.update(status='processing',claimed_at=datetime.now(timezone.utc).isoformat())
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=rows))

@pytest.fixture
def setup(monkeypatch):
    lead = str(uuid4())
    job = {'id':str(uuid4()),'lead_id':lead,'phone_number':PHONE,'body':'Hilltop TEST. Reply STOP to opt out.',
           'status':'scheduled','created_at':datetime.now(timezone.utc).isoformat(),'due_at':datetime.now(timezone.utc).isoformat()}
    db = DB({'sms_nurture_jobs':[job]})
    job = db.tables['sms_nurture_jobs'][0]
    sms = MagicMock(); sms._in_allowed_hours.return_value=True; sms._is_weekend.return_value=False
    monkeypatch.setattr(n,'SMSClient',lambda:sms)
    monkeypatch.setattr(n.settings,'sms_nurture_enabled',True)
    monkeypatch.setattr(n,'_readiness',lambda *_:{'blockers':[],'phone_number':PHONE,'body':job['body']})
    monkeypatch.setattr(n,'record_provider_alert',MagicMock())
    return db,job,sms

@pytest.mark.parametrize('outcome,status',[('accepted','accepted'),('delivered','accepted'),('unknown','review'),('submitting','review'),('failed','stopped'),(None,'stopped')])
def test_worker_records_result_and_never_redrives(setup,outcome,status):
    db,job,sms=setup
    def send(message,phone):
        assert str(message.id)==job['id'] and phone==PHONE
        if outcome: db.tables['sms_events']=[{'id':job['id'],'status':outcome}]
        return outcome in n.SUCCESS
    sms.send.side_effect=send
    assert n._drain(db)['processed']==1
    assert job['status']==status
    assert n._drain(db)['processed']==0
    sms.send.assert_called_once()

@pytest.mark.parametrize('blocker',['Seller replied','SMS consent revoked','Suppressed','Recipient outside allowlist'])
def test_latest_blockers_stop_before_provider(setup,monkeypatch,blocker):
    db,job,sms=setup
    monkeypatch.setattr(n,'_readiness',lambda *_:{'blockers':[blocker],'phone_number':PHONE,'body':job['body']})
    n._drain(db)
    assert job['status']=='stopped' and job['reason']==blocker
    sms.send.assert_not_called()

def test_changed_recipient_stops_without_send(setup,monkeypatch):
    db,job,sms=setup
    monkeypatch.setattr(n,'_readiness',lambda *_:{'blockers':[],'phone_number':'+12145550199'})
    n._drain(db)
    assert job['status']=='stopped'
    sms.send.assert_not_called()

def test_after_hours_defers_without_claim(setup):
    db,job,sms=setup
    sms._in_allowed_hours.return_value=False
    assert n._drain(db)['deferred']
    assert job['status']=='scheduled'
    sms.send.assert_not_called()

def test_crashed_claim_parks_without_replaying(setup):
    db,job,sms=setup
    job.update(status='processing',claimed_at=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat())
    assert n._drain(db)['aged_review']==1
    assert job['status']=='review'
    sms.send.assert_not_called()
    n.record_provider_alert.assert_called_once()

def test_reference_retry_reads_enrollment_without_new_insert(setup):
    db,job,sms=setup
    result=n._enroll(db,job['lead_id'],n.Enrollment(request_id=job['id'],acknowledged=True),str(uuid4()))
    assert result['id']==job['id'] and not db.inserts

def test_review_required_for_new_enrollment(setup):
    db,job,sms=setup
    with pytest.raises(HTTPException) as exc:
        n._enroll(db,job['lead_id'],n.Enrollment(request_id=uuid4()),str(uuid4()))
    assert exc.value.status_code==400 and not db.inserts

def test_worker_requires_secret_before_database(monkeypatch):
    app=FastAPI();app.include_router(n.router);client=TestClient(app)
    db=MagicMock();monkeypatch.setattr(n,'get_supabase_client',lambda:db)
    monkeypatch.setenv('CRON_SECRET','test-only')
    assert client.get('/webhooks/_worker/sms-nurture').status_code==401
    monkeypatch.delenv('CRON_SECRET')
    assert client.get('/webhooks/_worker/sms-nurture').status_code==503
    db.table.assert_not_called()
