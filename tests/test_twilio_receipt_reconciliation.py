"""Correlated callbacks repair ambiguous sends without status regression or redial."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import pytest
from tools.twilio_receipts import reconcile_twilio_receipt, reconcile_twilio_callback
from tests.test_twilio_integration import setup, sending, signed, SENDER
from tools.sms_client import SMSClient
from web.api import twilio_webhooks as hooks

PHONE = '+12147010100'
SID = 'SM' + 'b' * 32


class Table:
    def __init__(self, db):
        self.db, self.filters, self.payload = db, [], None
        self.insert = None
    def select(self, *_): return self
    def limit(self, *_): return self
    def eq(self, key, value):
        self.filters.append((key, value))
        return self
    def is_(self, key, value):
        assert value == 'null'
        return self.eq(key, None)
    def update(self, payload):
        self.payload = payload
        return self
    def upsert(self, payload, **_):
        self.insert = payload
        return self
    def execute(self):
        if self.insert is not None:
            if any(row['id'] == self.insert['id'] for row in self.db.rows):
                return SimpleNamespace(data=[])
            self.db.rows.append(deepcopy(self.insert))
            return SimpleNamespace(data=[deepcopy(self.insert)])
        if self.payload and self.db.before_update:
            callback, self.db.before_update = self.db.before_update, None
            callback(self.db)
        def value(row, key):
            if '->>' in key:
                column, field = key.split('->>')
                return (row.get(column) or {}).get(field)
            return row.get(key)
        rows = [r for r in self.db.rows if all(value(r, k) == v for k,v in self.filters)]
        if self.payload:
            for row in rows: row.update(deepcopy(self.payload))
        return SimpleNamespace(data=deepcopy(rows))


class DB:
    def __init__(self, status='unknown', bound=None):
        self.reference = str(uuid4())
        self.rows = [{'id':self.reference, 'provider':'twilio', 'direction':'outbound',
                      'phone_number':PHONE, 'status':status, 'body':'Original consented message',
                      'raw_payload': {'provider_sid':bound} if bound else {}}]
        self.before_update = None
    def table(self, name):
        assert name == 'sms_events'
        return Table(self)
    def rpc(self, name, args):
        assert name == 'record_twilio_event'
        self.archived = args
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={'saved':True,'duplicate':True}))


def apply(db, outcome, sid=SID):
    return reconcile_twilio_receipt(db, db.reference, PHONE, sid, outcome)


def test_delivered_callback_resolves_unknown_and_binds_sid_without_changing_message():
    db = DB()
    assert apply(db,'delivered') == 'delivered'
    assert db.rows[0]['raw_payload']['provider_sid'] == SID
    assert db.rows[0]['body'] == 'Original consented message'
    assert apply(db,'accepted') == 'delivered'
    assert apply(db,'queued') == 'delivered'


@pytest.mark.parametrize('status', ['failed','undelivered','canceled'])
def test_terminal_failure_survives_late_acceptance(status):
    db = DB('submitting')
    assert apply(db,status) == status
    assert apply(db,'accepted') == status


@pytest.mark.parametrize('field,value', [('phone_number','+12145550199'),('provider','other'),('direction','inbound')])
def test_mismatched_claim_is_not_modified(field, value):
    db = DB(); db.rows[0][field] = value
    before = deepcopy(db.rows)
    with pytest.raises(ValueError): apply(db,'delivered')
    assert db.rows == before


def test_bound_sid_cannot_be_replaced():
    db = DB(bound='SM'+'a'*32)
    with pytest.raises(ValueError): apply(db,'delivered')
    assert db.rows[0]['status'] == 'unknown'


def test_concurrent_delivery_wins_over_stale_acceptance_update():
    db = DB('submitting')
    db.before_update = lambda state: state.rows[0].update(status='delivered', raw_payload={'provider_sid':SID})
    assert apply(db,'accepted') == 'delivered'


def test_concurrent_other_sid_binding_cannot_be_overwritten_at_same_status():
    db = DB('accepted')
    db.before_update = lambda state: state.rows[0].update(raw_payload={'provider_sid':'SM'+'a'*32})
    with pytest.raises(ValueError): apply(db,'accepted')
    assert db.rows[0]['raw_payload']['provider_sid'] == 'SM'+'a'*32


def test_contradictory_terminal_outcomes_stay_unknown_for_review():
    db = DB()
    apply(db,'delivered')
    assert apply(db,'failed') == 'unknown'
    assert db.rows[0]['raw_payload']['delivery_conflict'] is True
    assert apply(db,'delivered') == 'unknown'


def test_legacy_callback_requires_unique_known_sid_and_matching_phone():
    db = DB('accepted', SID)
    payload = {'To':PHONE,'MessageSid':SID,'MessageStatus':'delivered'}
    assert reconcile_twilio_callback(db,payload) == (db.reference,'delivered')
    payload['To'] = '+12145550199'
    assert reconcile_twilio_callback(db,payload) == (None,None)
    payload['To'] = PHONE
    db.rows.append({**db.rows[0],'id':str(uuid4())})
    with pytest.raises(RuntimeError): reconcile_twilio_callback(db,payload)


def test_missing_explicit_reference_does_not_invent_a_claim():
    db = DB(); db.rows = []
    with pytest.raises(RuntimeError):
        reconcile_twilio_callback(db,{'app_message_id':db.reference,'To':PHONE,'MessageSid':SID,'MessageStatus':'delivered'})


def test_signed_duplicate_callback_repairs_claim_before_acknowledgment(setup, monkeypatch):
    client, _ = setup
    db = DB()
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    payload={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':SENDER,'To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',payload,'?message_id='+db.reference).status_code == 200
    assert db.rows[0]['status'] == 'delivered'
    assert db.archived['p_payload']['app_message_id'] == db.reference
    assert signed(client,'status',payload,'?message_id='+db.reference).status_code == 200
    assert db.rows[0]['status'] == 'delivered'


def test_signed_mismatched_sid_is_archived_but_not_acknowledged_as_reconciled(setup, monkeypatch):
    client, _ = setup
    db = DB(bound='SM'+'a'*32)
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    payload={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':SENDER,'To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',payload,'?message_id='+db.reference).status_code == 503
    assert db.rows[0]['status'] == 'unknown'


def test_signed_other_sender_cannot_bind_an_unknown_claim(setup, monkeypatch):
    client, _ = setup
    db = DB()
    monkeypatch.setattr(hooks,'get_supabase_client',lambda:db)
    monkeypatch.setattr(hooks,'reconcile_twilio_callback',reconcile_twilio_callback)
    payload={'AccountSid':'AC'+'a'*32,'MessageSid':SID,'From':'+12145550199','To':PHONE,'MessageStatus':'delivered'}
    assert signed(client,'status',payload,'?message_id='+db.reference).status_code == 403
    assert db.rows[0]['status'] == 'unknown'


class Consent:
    def select(self, *_): return self
    def eq(self, *_): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, *_): return self
    def execute(self):
        return SimpleNamespace(data=[{'raw_answers':{'phone':PHONE,'property_address':'Test',
            '_sms_consent':{'accepted':True,'rendered_disclosure_matches':True}}}])


class SendDB(DB):
    def table(self, name):
        return Consent() if name == 'lead_form_submissions' else super().table(name)
    def rpc(self, name, _args):
        if name == 'claim_twilio_sms':
            self.table('sms_events').upsert({'id':_args['p_id'],'lead_id':_args['p_lead'],
                'provider':'twilio','direction':'outbound','phone_number':_args['p_phone'],
                'body':_args['p_body'],'status':'submitting'},on_conflict='id',ignore_duplicates=True).execute()
            return SimpleNamespace(execute=lambda:SimpleNamespace(data={'claimed':True}))
        assert name == 'intake_phone_status'
        return SimpleNamespace(execute=lambda:SimpleNamespace(data={'suppressed':False}))


@pytest.mark.parametrize('outcome,timeout,accepted', [
    ('delivered',True,True), ('failed',True,False),
    ('delivered',False,True), ('failed',False,False),
])
def test_real_send_path_preserves_callback_before_http_return(sending, monkeypatch, outcome, timeout, accepted):
    _, sdk, message = sending
    db = SendDB(); db.reference = str(message.id); db.rows = []
    monkeypatch.setattr('tools.crm.get_supabase_client',lambda:db)
    monkeypatch.setattr('tools.sms_client.reconcile_twilio_receipt',reconcile_twilio_receipt)
    def provider(**_):
        apply(db,outcome)
        if timeout: raise TimeoutError('response lost after provider callback')
        return SimpleNamespace(sid=SID)
    sdk.messages.create.side_effect = provider
    assert SMSClient()._send_twilio(message,PHONE) is accepted
    assert db.rows[0]['status'] == outcome
    assert message.provider_message_id == SID
    sdk.messages.create.assert_called_once()
