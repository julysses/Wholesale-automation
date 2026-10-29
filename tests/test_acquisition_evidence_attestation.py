"""Trusted signing contract with synthetic keys; no provider or production secrets."""
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from tests.test_acquisition_evidence import ARTIFACT, CAMPAIGN, NOW, WORKSPACE, BODY
from tests.test_acquisition_evidence_scan import VERSION
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_attestation import VerificationSigningKey, build_scan_attestation

ACTOR=UUID('00000000-0000-4000-8000-000000000001')
REQUEST=UUID('99300000-0000-4000-8000-000000000002')
KEY=VerificationSigningKey(UUID('99300000-0000-4000-8000-000000000001'),WORKSPACE,b'k'*32,VERSION.decode(),
                           'synthetic-v1',NOW-timedelta(hours=1),NOW+timedelta(hours=1))


def receipt(**changes):
    return dict(status='scan_observed',workspace_id=str(WORKSPACE),campaign_id=str(CAMPAIGN),evidence_ref=str(ARTIFACT),
        purpose='mail_content',sha256=hashlib.sha256(BODY).hexdigest(),byte_size=len(BODY),media_type='text/plain',
        retention_policy_id=str(CAMPAIGN),retain_until=(NOW+timedelta(days=1)).isoformat(),checked_at=NOW.isoformat(),
        registry_checked_at=NOW.isoformat(),scan_checked_at=NOW.isoformat(),scanner='clamav-instream-v1',
        scanner_version=VERSION.decode(),scan_policy_version='synthetic-v1',scan_status='no_detection',
        verifier_version='acquisition-evidence-bytes-v1',registry_verifier_version='acquisition-evidence-registry-v1',
        verification_persisted=False,scan_persisted=False,preview_authorized=False,content_approved=False,execution_authorized=False)|changes


def sign(value=None, **changes):
    options=dict(request_id=REQUEST,actor_id=ACTOR,session_id=ACTOR,key=KEY,clock=lambda:NOW)|changes
    return build_scan_attestation(receipt() if value is None else value,**options)


def test_signature_binds_every_context_field_and_exact_payload_without_exposing_key():
    result=sign()
    ordered=[result[k] for k in ('p_id','p_workspace','p_campaign','p_artifact','p_actor','p_session','p_key')]
    message='acquisition-evidence-attestation-v1\n'+'\n'.join(ordered)+'\n'+result['p_observation']
    assert result['p_signature']==hmac.new(b'k'*32,message.encode(),hashlib.sha256).hexdigest()
    assert len(json.loads(result['p_observation']))==12
    assert json.loads(result['p_observation'])['scan_status']=='no_detection'
    assert result==sign()
    assert 'secret' not in repr(KEY) and "b'kkkk" not in repr(KEY)
    assert 'secret' not in json.dumps(result)
    for name in ('request_id','actor_id','session_id'):
        assert sign(**{name:ARTIFACT})['p_signature']!=result['p_signature']
    assert sign(receipt(scan_status='detected'))['p_signature']!=result['p_signature']


@pytest.mark.parametrize('changes',[{'content_approved':True},{'scan_persisted':True},{'verification_persisted':True},
    {'preview_authorized':True},{'execution_authorized':True},{'content_approved':0},{'scan_status':'clean'},
    {'sha256':'A'*64},{'byte_size':True},{'byte_size':0},{'byte_size':10485761},{'byte_size':'20'},
    {'object_url':'https://private.example/file'},{'workspace_id':str(CAMPAIGN)},
    {'scanner_version':'ClamAV 1.4.3/12346/Thu Oct 29 00:00:00 2026'},
    {'scan_policy_version':'other'},{'checked_at':'123'},{'checked_at':0},
    {'checked_at':NOW.replace(tzinfo=None).isoformat()},{'checked_at':(NOW-timedelta(seconds=121)).isoformat()},
    {'scan_checked_at':(NOW-timedelta(seconds=1)).isoformat()},
    {'registry_checked_at':(NOW-timedelta(seconds=6)).isoformat()},
    {'registry_checked_at':(NOW+timedelta(seconds=6)).isoformat()}, {'retain_until':NOW.isoformat()}])
def test_untrusted_inconsistent_or_stale_receipt_is_not_signed(changes):
    with pytest.raises(EvidenceUnavailable,match='^Trusted scan attestation is unavailable$'):sign(receipt(**changes))


@pytest.mark.parametrize('changes',[{'secret':b'x'*31},{'secret':bytearray(b'x'*32)},{'id':'not-uuid'},
    {'workspace_id':CAMPAIGN},{'valid_until':NOW},{'valid_until':NOW+timedelta(days=2)},
    {'valid_from':NOW+timedelta(seconds=1)},{'valid_from':NOW.replace(tzinfo=None)},
    {'scanner_version':'wrong'},{'scan_policy_version':'wrong'}])
def test_key_scope_expiry_and_configuration_must_match(changes):
    with pytest.raises(EvidenceUnavailable):sign(key=replace(KEY,**changes))


def test_missing_and_extra_fields_never_produce_signature():
    for key in receipt():
        value=receipt();del value[key]
        with pytest.raises(EvidenceUnavailable):sign(value)
    for kwargs in ({'key':None},{'actor_id':'user'},{'session_id':None},{'request_id':True}):
        with pytest.raises(EvidenceUnavailable):sign(**kwargs)
