"""Native intake consent passes the real SMS guard without real provider calls."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

import pytest

from config.settings import settings
from schemas.outreach import OutreachChannel, OutreachMessage
from tests.test_webhook_completion_delivery import MemoryDB, MemoryTable
from tools import crm, sms_client
from tools.facebook_consent import (
    HILLTOP_CONSENT_FORM_ID, SMS_CHECKBOX_KEY, AI_CHECKBOX_KEY, facebook_consent_record,
)
from tools.sms_client import SMSClient
from web.api import lead_forms_api as forms, webhooks

PHONE = '+12147010100'


class Query(MemoryTable):
    def order(self, *_args, **_kwargs):
        return self
    def is_(self, key, value):
        assert key == 'raw_payload->>provider_sid' and value == 'null'
        # Native intake fixtures exercise first-send unbound claims. Concurrent
        # JSON/SID comparisons are covered by the receipt-reconciliation suite.
        matches = [row for row in self.db.tables.get(self.name, {}).values()
                   if all(row.get(k) == v for k,v in self.filters.items())]
        assert all((row.get('raw_payload') or {}).get('provider_sid') is None for row in matches)
        return self


class DB(MemoryDB):
    def __init__(self):
        self.tables = {'app_settings': {'owner': {'key': 'lead_owner_user_id', 'value': 'owner-1'}},
                       'profiles': {'owner-1': {'id': 'owner-1', 'status': 'approved'}}}
        self.suppressed = False

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, _payload):
        if name == 'claim_intake_notification':
            def claim():
                notice = _payload['p_notification']
                notice_id = str(uuid5(NAMESPACE_URL, f"wholesaleos:intake-alert:{_payload['p_lead_id']}"))
                assert notice['id'] == notice_id
                rows = self.tables.setdefault('app_notifications', {})
                row = rows.setdefault(notice_id, {
                    **notice, 'metadata': {**notice['metadata'], 'delivery_state': 'pending'},
                })
                if row['metadata'].get('delivery_state') != 'pending':
                    return SimpleNamespace(data={'claimed': False, 'notification_id': notice_id})
                row['metadata'].update(delivery_state='processing', delivery_claim=_payload['p_claim_id'])
                return SimpleNamespace(data={'claimed': True, 'notification_id': notice_id,
                                             'claim_id': _payload['p_claim_id']})
            return SimpleNamespace(execute=claim)
        if name == 'finish_intake_notification':
            def finish():
                notice_id = str(uuid5(NAMESPACE_URL, f"wholesaleos:intake-alert:{_payload['p_lead_id']}"))
                row = self.tables['app_notifications'][notice_id]
                claimed = (row['metadata'].get('delivery_state') == 'processing'
                           and row['metadata'].get('delivery_claim') == _payload['p_claim_id'])
                if claimed:
                    outcomes = _payload['p_outcomes']
                    complete = (outcomes['owner_email'] == 'accepted' and outcomes['seller_sms'] in
                                ('accepted', 'no_consent_or_phone', 'suppressed_or_duplicate'))
                    row['metadata'].update(outcomes, delivery_state='completed' if complete else 'review')
                    row['body'] = _payload['p_body']
                return SimpleNamespace(data={'finished': claimed, 'notification_id': notice_id})
            return SimpleNamespace(execute=finish)
        if name == 'claim_twilio_sms':
            existing = _payload['p_id'] in self.tables.get('sms_events', {})
            if not existing:
                self.table('sms_events').upsert({'id':_payload['p_id'], 'lead_id':_payload['p_lead'],
                    'phone_number':_payload['p_phone'], 'body':_payload['p_body'], 'provider':'twilio',
                    'direction':'outbound','status':'submitting'},on_conflict='id',ignore_duplicates=True).execute()
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={'claimed':not existing}))
        assert name == 'intake_phone_status'
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={'suppressed': self.suppressed, 'duplicate': False}))


@pytest.fixture
def intake(monkeypatch):
    import twilio.rest
    db, sdk, email = DB(), MagicMock(), MagicMock()
    sdk.messages.create.return_value.sid = 'SM' + 'a' * 32
    email.send.return_value = True
    monkeypatch.setattr(twilio.rest, 'Client', lambda *_args, **_kwargs: sdk)
    monkeypatch.setattr(crm, 'get_supabase_client', lambda: db)
    monkeypatch.setattr(forms, '_get_supabase', lambda: db)
    monkeypatch.setattr(forms, 'EmailClient', lambda: email)
    for key, value in {'sms_live_enabled': True, 'sms_allowed_recipients': PHONE,
        'sms_provider': 'twilio', 'twilio_account_sid': 'AC' + 'b' * 32, 'twilio_auth_token': 'test-only',
        'twilio_from_number': '+14698049920', 'twilio_messaging_service_sid': 'MG' + 'c' * 32,
        'twilio_webhook_base_url': 'https://wholesale-automation.vercel.app',
        'notification_email': 'owner@example.com', 'tcpa_allowed_start_hour': 9,
        'tcpa_allowed_end_hour': 19, 'sms_weekend_blocked': True}.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(sms_client, '_texas_now', lambda: datetime(2026, 10, 8, 12, tzinfo=ZoneInfo('America/Chicago')))
    return db, sdk, email


def data(sms='1', ai='0'):
    return SimpleNamespace(form_id=HILLTOP_CONSENT_FORM_ID, created_time='2026-10-07T20:00:00Z',
        fields={'full_name': 'Controlled Native Seller', 'phone_number': PHONE, 'street_address': 'TEST ONLY'},
        custom_disclaimer_responses=[{'checkbox_key': SMS_CHECKBOX_KEY, 'is_checked': sms},
                                     {'checkbox_key': AI_CHECKBOX_KEY, 'is_checked': ai}])


@pytest.mark.asyncio
@pytest.mark.parametrize('sms,ai,expected', [('1', '0', 1), ('0', '1', 0), ('0', '0', 0), ('yes', '1', 0)])
async def test_native_intake_notifies_owner_and_separates_channels(intake, sms, ai, expected):
    db, sdk, email = intake
    adapter = MagicMock(); adapter.fetch_lead_form_data.return_value = data(sms, ai)
    entry = SimpleNamespace(leadgen_id='controlled-native', campaign_id='')
    await webhooks._process_facebook_lead(entry, adapter)
    await webhooks._process_facebook_lead(entry, adapter)
    assert len(db.tables['leads']) == 1
    assert len(db.tables['tasks']) == 1
    assert len(db.tables['app_notifications']) == 1
    email.send.assert_called_once()
    assert sdk.messages.create.call_count == expected
    assert len(db.tables.get('sms_events', {})) == expected
    notice = next(iter(db.tables['app_notifications'].values()))
    assert notice['metadata']['seller_sms'] == ('accepted' if expected else 'no_consent_or_phone')
    assert notice['metadata']['delivery_state'] == 'completed'
    assert notice['metadata']['consent_receipt']['phone'] == PHONE
    lead = next(iter(db.tables['leads'].values()))
    assert lead['assigned_to'] == 'owner-1'
    assert lead['ai_calling_paused'] is True


def fixture_lead(db):
    lead_id = str(uuid4())
    lead = {'id': lead_id, 'dnc': False, 'source': 'facebook_lead_ad', 'internal_notes': 'FB leadgen_id=controlled-native',
            'owner_phone_1': PHONE, 'property_address': 'TEST ONLY'}
    receipt = facebook_consent_record(data(), 'controlled-native')
    notice_id = str(uuid5(NAMESPACE_URL, f'wholesaleos:intake-alert:{lead_id}'))
    db.tables['leads'] = {lead_id: lead}
    db.tables['app_notifications'] = {notice_id: {'id': notice_id, 'metadata': {'source': 'facebook_lead_ad', 'consent_receipt': receipt}}}
    return OutreachMessage(lead_id=lead_id, channel=OutreachChannel.SMS, body='TEST ONLY', compliance_cleared=True), lead, receipt


@pytest.mark.parametrize('kind', ['wrong_phone', 'missing_phone', 'future_time', 'unknown_form', 'disclosure',
    'other_lead', 'dnc', 'suppressed', 'missing_lead', 'other_source', 'duplicate_box', 'ai_only', 'stale_website_refusal'])
def test_incomplete_or_revoked_native_evidence_refuses(intake, kind):
    db, sdk, _ = intake
    message, lead, receipt = fixture_lead(db)
    if kind == 'wrong_phone': receipt['phone'] = '+12145550199'
    if kind == 'missing_phone': receipt.pop('phone')
    if kind == 'future_time': receipt['submitted_at'] = '2099-01-01T00:00:00Z'
    if kind == 'unknown_form': receipt['form_id'] = 'unknown'
    if kind == 'disclosure': receipt['sms']['disclosure'] = 'different'
    if kind == 'other_lead': lead['internal_notes'] = 'FB leadgen_id=other'
    if kind == 'dnc': lead['dnc'] = True
    if kind == 'suppressed': db.suppressed = True
    if kind == 'missing_lead': db.tables['leads'] = {}
    if kind == 'other_source': lead['source'] = 'buyer_import'
    if kind == 'duplicate_box': receipt['raw_responses'].append(receipt['raw_responses'][0].copy())
    if kind == 'ai_only': receipt['raw_responses'] = [{'checkbox_key': AI_CHECKBOX_KEY, 'is_checked': '1'}]
    if kind == 'stale_website_refusal':
        db.tables['lead_form_submissions'] = {'later': {'lead_id': str(message.lead_id), 'raw_answers': {'phone': PHONE, '_sms_consent': {'accepted': False}}}}
    assert SMSClient().send(message, PHONE) is False
    sdk.messages.create.assert_not_called()
    assert not db.tables.get('sms_events')


@pytest.mark.parametrize('phone', [PHONE + '.evil', '+52147010100', '0' + PHONE, PHONE + '9'])
def test_invalid_phone_cannot_match_by_last_ten_digits(intake, phone):
    db, sdk, _ = intake
    message, _, receipt = fixture_lead(db)
    receipt['phone'] = phone
    assert SMSClient().send(message, PHONE) is False
    sdk.messages.create.assert_not_called()


def test_native_consent_does_not_bypass_after_hours(intake, monkeypatch):
    db, sdk, _ = intake
    message, _, _ = fixture_lead(db)
    monkeypatch.setattr(sms_client, '_texas_now', lambda: datetime(2026, 10, 8, 19, tzinfo=ZoneInfo('America/Chicago')))
    assert SMSClient().send(message, PHONE) is False
    sdk.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_ambiguous_sms_attempt_alerts_operator_and_never_replays(intake):
    db, sdk, email = intake
    sdk.messages.create.side_effect = TimeoutError('response unknown')
    adapter = MagicMock(); adapter.fetch_lead_form_data.return_value = data()
    entry = SimpleNamespace(leadgen_id='controlled-native-timeout', campaign_id='')
    await webhooks._process_facebook_lead(entry, adapter)
    await webhooks._process_facebook_lead(entry, adapter)
    assert sdk.messages.create.call_count == 1
    email.send.assert_called_once()
    assert next(iter(db.tables['sms_events'].values()))['status'] == 'unknown'
    notice = next(row for row in db.tables['app_notifications'].values() if row.get('type') == 'pipeline_step')
    assert notice['metadata']['delivery_state'] == 'review'
    alerts = [row for row in db.tables['app_notifications'].values() if row.get('metadata', {}).get('integration_failure')]
    assert len(alerts) == 1
    assert alerts[0]['metadata']['provider'] == 'twilio'
