"""Reviewed content binding and inert proof output; no external services."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_mail_render import MailRenderInput
from tools.acquisition_mail_render import content_binding, render_mail_proof

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
uid = lambda n: UUID(int=n)


def data():
    scope = dict(workspace_id=uid(1), campaign_id=uid(2))
    raw = dict(**scope, property_id=uid(3), tracking_id=uid(4), company_name='Hilltop & Co',
        property_address='123 Synthetic St\nUnit 2', now=NOW,
        template=dict(**scope, template_id=uid(5), version=1, format='letter', tracking_mode='phone',
            body='Hello from {{company_name}}. Call {{tracking_phone}} about {{property_address}}.'),
        destination=dict(**scope, id=uid(6), version=1, mode='phone', value='+12125550100',
            verification_ref=uid(7), verified_at=NOW-timedelta(days=2), expires_at=NOW+timedelta(days=2), revoked=False),
        review=dict(**scope, id=uid(8), approver_id=uid(9), evidence_ref=uid(10), binding_digest='0'*64,
            status='approved', reviewed_at=NOW-timedelta(days=1), expires_at=NOW+timedelta(days=1)))
    return reviewed(raw)


def reviewed(raw):
    obj = MailRenderInput.model_validate(raw)
    raw['review']['binding_digest'] = content_binding(obj.template, obj.destination, obj.company_name)
    return raw


def run(raw):
    return render_mail_proof(MailRenderInput.model_validate(raw))


def test_inert_deterministic_output_binds_review_and_tracking():
    raw = data(); result = run(raw)
    assert result == run(raw)
    assert result['status'] == 'proof_prepared' and result['execution_authorized'] is False
    assert 'Hilltop & Co' in result['text'] and '+12125550100' in result['text']
    assert 'Hilltop &amp; Co' in result['html_fragment']
    assert result['review_id'] == str(uid(8)) and result['tracking_id'] == str(uid(4))
    raw['now'] += timedelta(minutes=1)
    assert run(raw)['proof_digest'] == result['proof_digest']


@pytest.mark.parametrize('section,field,value', [
    ('template','body','Changed {{tracking_phone}}'),('template','version',2),
    ('template','template_id',uid(55)),('template','format','postcard'),
    ('destination','value','+12125550101'),('destination','version',2),
    ('destination','id',uid(66)),('destination','verification_ref',uid(77)),
    ('destination','expires_at',NOW+timedelta(days=3)),
])
def test_changed_content_cannot_reuse_review(section,field,value):
    raw=data();raw[section][field]=value
    with pytest.raises(ValueError,match='changed since review'):run(raw)


def test_company_identity_is_bound_to_review():
    raw=data();raw['company_name']='Other buyer'
    with pytest.raises(ValueError,match='changed since review'):run(raw)


@pytest.mark.parametrize('section',['template','destination','review'])
@pytest.mark.parametrize('field',['workspace_id','campaign_id'])
def test_scope_cannot_cross(section,field):
    raw=data();raw[section][field]=uid(100)
    with pytest.raises(ValueError,match='scope'):run(raw)


@pytest.mark.parametrize('section,field,value',[
    ('destination','revoked',True),('destination','expires_at',NOW),
    ('destination','verified_at',NOW+timedelta(seconds=1)),
    ('review','status','rejected'),('review','status','withdrawn'),('review','expires_at',NOW),
    ('review','reviewed_at',NOW+timedelta(seconds=1)),
    ('review','reviewed_at',NOW-timedelta(days=3)),
])
def test_expired_future_or_revoked_evidence_holds(section,field,value):
    raw=data();raw[section][field]=value
    with pytest.raises(ValueError):run(raw)


@pytest.mark.parametrize('body',[
    'No tracked response', '{{tracking_url}}', '{{unknown}} {{tracking_phone}}',
    '{{tracking_phone}} {{tracking_url}}', '{{tracking_phone}} {property}',
    '{{tracking_phone}}\x00', '{{tracking_phone}}\u202e',
])
def test_template_rejects_missing_mismatched_tokens_and_controls(body):
    raw=data();raw['template']['body']=body
    with pytest.raises(ValueError):reviewed(raw)


@pytest.mark.parametrize('phone',['2125550100','+0123456789','+12125550100 ext 1','+1','+12125550100\n'])
def test_invalid_tracked_phone(phone):
    raw=data();raw['destination']['value']=phone
    with pytest.raises(ValueError):reviewed(raw)


def website(raw, value):
    raw['template'].update(tracking_mode='landing_page',body='Visit {{tracking_url}} about {{property_address}}.')
    raw['destination'].update(mode='landing_page',value=value)
    return raw


@pytest.mark.parametrize('url',[
    'http://example.com', 'javascript:alert(1)', 'https://user:pass@example.com',
    'https://example.com?redirect=evil', 'https://example.com?', 'https://example.com#', 'https://example.com/#fragment',
    'https://127.0.0.1/', 'https://[::1]/', 'https://2130706433/',
    'https://127.1/', 'https://host.local/', 'https://example.com:443/',
    'https://example.com/with space', 'https://example.com/%0a',
    'https://example.com/\\evil', 'https://example.com/{{company_name}}',
])
def test_unsafe_destination_rejected(url):
    with pytest.raises(ValueError):reviewed(website(data(),url))


def test_https_postcard_and_safe_markup():
    raw=website(data(),'https://example.com/seller');raw['template']['format']='postcard'
    raw['template']['body'] += ' <img src=x onerror=alert(1)>'
    result=run(reviewed(raw))
    assert result['format']=='postcard' and 'https://example.com/seller' in result['text']
    assert '<img' not in result['html_fragment'] and '&lt;img' in result['html_fragment']


@pytest.mark.parametrize('field,value',[
    ('company_name','{{tracking_phone}}'), ('company_name','Fake\nIdentity'),
    ('property_address','{{tracking_url}}'), ('property_address','street\x00'),
    ('property_address','street\u202e'), ('property_address','  '),
])
def test_substitution_cannot_inject_tokens_or_controls(field,value):
    raw=data();raw[field]=value
    with pytest.raises(ValueError):run(raw)


@pytest.mark.parametrize('field,value',[
    ('property_id',uid(999)),('tracking_id',uid(999)),('property_address','123 Synthetic St\nUnit 3'),
])
def test_recipient_or_tracking_change_requires_new_proof(field,value):
    raw=data();before=run(raw);raw[field]=value
    assert run(raw)['proof_digest'] != before['proof_digest']


def test_markup_substitution_is_escaped_and_not_recursive():
    raw=data();raw['property_address']='<script>alert(1)</script>'
    result=run(raw)
    assert '<script>' not in result['html_fragment'] and '&lt;script&gt;' in result['html_fragment']


@pytest.mark.parametrize('section,field,value',[
    ('template','version',True),('destination','revoked','false'),
    ('review','reviewed_at',datetime(2026,10,28)),('review','binding_digest','not-a-hash'),
    ('review','execution_authorized',True),
])
def test_untyped_authority_and_unknown_fields_rejected(section,field,value):
    raw=data();raw[section][field]=value
    with pytest.raises(ValidationError):MailRenderInput.model_validate(raw)


def test_excessive_substitution_expansion_is_held():
    raw=data();raw['template']['body']='{{tracking_phone}} ' + '{{property_address}}'*100
    raw['property_address']='x'*1000
    with pytest.raises(ValueError,match='proof limit'):run(reviewed(raw))


def test_new_review_requires_new_proof_even_for_same_content():
    raw=data();before=run(raw);raw['review']['id']=uid(123)
    assert run(raw)['binding_digest']==before['binding_digest']
    assert run(raw)['proof_digest']!=before['proof_digest']


def test_content_validity_uses_earliest_evidence_expiry():
    raw=data()
    assert run(raw)['content_valid_until']==raw['review']['expires_at'].isoformat()
    raw['destination']['expires_at']=NOW+timedelta(minutes=30)
    result=run(reviewed(raw))
    assert result['content_valid_until']==raw['destination']['expires_at'].isoformat()
    raw['now']=raw['destination']['expires_at']
    with pytest.raises(ValueError,match='expired'):run(raw)
