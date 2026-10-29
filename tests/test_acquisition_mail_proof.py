"""Server-loaded proof provenance, freshness, escaping and authority boundaries."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from tools.acquisition_mail_proof import build_reviewed_mail_proof, ProofUnavailable

NOW = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
uid = lambda n: str(UUID(int=n))


def context():
    snapshot = {'workspace_id': uid(1), 'campaign_id': uid(2), 'renderer_version': 'acquisition-mail-render-v1',
        'company_name': 'Hilltop & Co',
        'template': {'creative_id': uid(3), 'template_id': uid(4), 'version': 1, 'format': 'letter', 'tracking_mode': 'phone',
            'body': 'Hello from {{company_name}}. Call {{tracking_phone}} about {{property_address}}.'},
        'destination': {'review_id': uid(5), 'destination_id': uid(6), 'version': 1, 'mode': 'phone', 'value': '+12145550100',
            'verification_ref': uid(7), 'verification_hash': 'a'*64, 'verified_epoch': int((NOW-timedelta(days=1)).timestamp()),
            'expires_epoch': int((NOW+timedelta(days=2)).timestamp()), 'reviewer_id': uid(8), 'reviewer_membership_epoch': int((NOW-timedelta(days=3)).timestamp())}}
    prep = {'status': 'content_prepared', 'execution_authorized': False, 'content_approved': False,
            'snapshot': snapshot, 'preparation_hash': 'b'*64, 'checked_at': NOW.isoformat(),
            'destination_valid_until': (NOW+timedelta(days=2)).isoformat()}
    record = {'id': uid(9), 'workspace_id': uid(1), 'campaign_id': uid(2), 'content_id': uid(10), 'version': 1, 'action': 'approved',
        'creative_id': uid(3), 'destination_review_id': uid(5), 'company_name': 'Hilltop & Co', 'renderer_version': 'acquisition-mail-render-v1',
        'preparation_hash': 'b'*64, 'evidence_ref': uid(11), 'evidence_hash': 'c'*64, 'expires_at': (NOW+timedelta(days=1)).isoformat(),
        'review_note': 'Reviewed exact wording and routing evidence.', 'actor_id': uid(8),
        'actor_membership_updated_at': (NOW-timedelta(days=3)).isoformat(), 'request_hash': 'd'*64,
        'created_at': (NOW-timedelta(minutes=2)).isoformat()}
    state = {'workspace_id': uid(1), 'campaign_id': uid(2), 'content_id': uid(10), 'version': 1, 'latest_review': record,
        'review_current': True, 'status': 'approved', 'preparation': prep, 'execution_authorized': False, 'checked_at': NOW.isoformat()}
    return {'workspace_id': uid(1), 'campaign_id': uid(2), 'content_id': uid(10), 'lead_id': uid(12),
        'property': {'property_id': uid(13), 'lead_id': uid(12), 'address_std': '123 <Fixture> St', 'unit': '2',
                     'city': 'Dallas', 'state': 'TX', 'zip': None}, 'review_state': state, 'checked_at': NOW.isoformat(), 'execution_authorized': False}


def render(raw=None, now=NOW, **scope):
    args={'workspace_id': UUID(uid(1)), 'campaign_id': UUID(uid(2)), 'content_id': UUID(uid(10)), 'lead_id': UUID(uid(12))}|scope
    return build_reviewed_mail_proof(context() if raw is None else raw, now=now, **args)


def test_proof_reconstructs_binding_from_current_sources_without_authority():
    proof=render()
    assert proof['proof_kind']=='internal_content_preview'
    assert proof['tracking_id_kind']=='preview_only'
    assert all(proof[key] is False for key in ('execution_authorized','postal_verified','recipient_authorized','vendor_proof'))
    assert '123 <Fixture> St\nUnit 2\nDallas, TX' in proof['text']
    assert '&lt;Fixture&gt;' in proof['html_fragment'] and 'Hilltop &amp; Co' in proof['html_fragment']
    assert proof['review_id']==uid(9) and proof['content_id']==uid(10) and proof['property_id']==uid(13)
    assert proof['proof_digest']==render(now=NOW+timedelta(seconds=1))['proof_digest']
    assert proof['source_checked_at']==NOW.isoformat()


@pytest.mark.parametrize('scope',['workspace_id','campaign_id','content_id','lead_id'])
def test_requested_scope_cannot_substitute_other_source(scope):
    with pytest.raises(ValueError):render(**{scope: UUID(uid(99))})


@pytest.mark.parametrize('section,key,value',[
    ('root','execution_authorized',True),('root','lead_id',uid(99)),('root','extra','private data'),
    ('property','lead_id',uid(99)),('property','address_std','{{tracking_phone}}'),('property','city',''),
    ('property','unit','\u202e2'),('property','zip','90210\nInjected'),('property','owner_phone','private'),
    ('state','review_current',False),('state','preparation',None),('state','execution_authorized',0),
    ('state','checked_at',(NOW-timedelta(seconds=1)).isoformat()),
])
def test_inconsistent_or_unsafe_context_cannot_render(section,key,value):
    raw=context();target=raw if section=='root' else raw['review_state'] if section=='state' else raw[section]
    target[key]=value
    with pytest.raises(ValueError):render(raw)


@pytest.mark.parametrize('seconds',[-6,31])
def test_old_or_future_database_snapshot_is_not_used(seconds):
    with pytest.raises(ProofUnavailable):render(now=NOW+timedelta(seconds=seconds))


def test_expiry_during_transport_requires_fresh_review():
    raw=context();raw['review_state']['latest_review']['expires_at']=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ProofUnavailable):render(raw,now=NOW+timedelta(seconds=1))


def test_historical_approval_never_becomes_current_from_its_receipt():
    raw=context();raw['review_state'].update(status='requires_review',review_current=False,preparation=None)
    with pytest.raises(ProofUnavailable):render(raw)


@pytest.mark.parametrize('change',['address','unit','zip','evidence','preparation'])
def test_proof_digest_binds_canonical_property_and_approval_evidence(change):
    raw=context();original=render(raw)
    if change in ('address','unit','zip'):
        key='address_std' if change=='address' else change
        raw['property'][key]={'address':'124 Fixture St','unit':'3','zip':'75001'}[change]
    elif change=='evidence':raw['review_state']['latest_review']['evidence_hash']='e'*64
    else:
        raw['review_state']['latest_review']['preparation_hash']='f'*64
        raw['review_state']['preparation']['preparation_hash']='f'*64
    changed=render(raw)
    assert changed['proof_digest']!=original['proof_digest']
    assert changed['source_digest']!=original['source_digest']


def test_new_review_gets_distinct_preview_identity():
    raw=context();first=render(raw)
    raw['review_state']['latest_review']['id']=uid(88)
    raw['review_state']['latest_review']['version']=2;raw['review_state']['version']=2
    assert render(raw)['tracking_id']!=first['tracking_id']


def test_missing_optional_unit_and_zip_remain_absent():
    raw=context();raw['property']['unit']=None
    assert 'Unit' not in render(raw)['text']
    assert 'None' not in render(raw)['text']
