"""Contract-target signatures with synthetic keys; no real credentials or writes."""
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from tests.test_acquisition_evidence_attestation import receipt as mail_receipt, KEY as MAIL_KEY
from tests.test_acquisition_contract_documents import NOW, uid
from tools.acquisition_contract_attestation import ContractVerificationSigningKey, build_contract_scan_attestation
from tools.acquisition_evidence import EvidenceUnavailable

KEY = ContractVerificationSigningKey(uid(8), uid(2), b'k'*32, frozenset({'purchase_contract', 'title_report'}),
    MAIL_KEY.scanner_version, MAIL_KEY.scan_policy_version, NOW-timedelta(hours=1), NOW+timedelta(hours=1))


def receipt(**changes):
    result = mail_receipt()
    for field in ('campaign_id', 'evidence_ref', 'content_approved'):
        result.pop(field)
    result.update(workspace_id=str(uid(2)), contract_id=str(uid(3)), contract_version=2, artifact_id=str(uid(1)),
                  purpose='purchase_contract', verifier_version='acquisition-contract-document-bytes-v1',
                  registry_verifier_version='acquisition-contract-document-registry-v1', legal_review_approved=False,
                  checked_at=NOW.isoformat(), scan_checked_at=NOW.isoformat(), registry_checked_at=NOW.isoformat(),
                  retain_until=(NOW+timedelta(days=1)).isoformat())
    return result | changes


def sign(value=None, **options):
    return build_contract_scan_attestation(receipt() if value is None else value,
        **(dict(request_id=uid(4), actor_id=uid(5), session_id=uid(6), key=KEY, clock=lambda:NOW) | options))


def test_domain_version_purpose_and_exact_context_are_signed():
    result = sign()
    fields = ('p_id','p_workspace','p_contract','p_version','p_purpose','p_artifact','p_actor','p_session','p_key')
    message = 'acquisition-contract-document-attestation-v1\n'+'\n'.join(str(result[k]) for k in fields)+'\n'+result['p_observation']
    assert result['p_signature'] == hmac.new(b'k'*32, message.encode(), hashlib.sha256).hexdigest()
    assert result == sign() and type(result['p_version']) is int
    assert 'secret' not in repr(KEY) and 'secret' not in json.dumps(result)
    for change in ({'contract_id':str(uid(9))}, {'contract_version':3}, {'purpose':'title_report'}, {'artifact_id':str(uid(9))}, {'scan_status':'detected'}):
        assert sign(receipt(**change))['p_signature'] != result['p_signature']
    for name in ('request_id','actor_id','session_id'):
        assert sign(**{name:uid(9)})['p_signature'] != result['p_signature']


@pytest.mark.parametrize('change', [{'campaign_id':str(uid(9))}, {'contract_version':True}, {'contract_version':0},
    {'contract_version':2147483648}, {'purpose':'mail_content'}, {'purpose':'closing_statement'}, {'workspace_id':str(uid(9))},
    {'execution_authorized':True}, {'legal_review_approved':True}, {'preview_authorized':True}, {'scan_persisted':True},
    {'verification_persisted':True}, {'legal_review_approved':0}, {'scan_status':'clean'}, {'sha256':'A'*64},
    {'byte_size':True}, {'object_url':'https://private.test'}, {'checked_at':0}, {'checked_at':NOW.replace(tzinfo=None).isoformat()},
    {'checked_at':(NOW-timedelta(seconds=121)).isoformat()}, {'registry_checked_at':(NOW+timedelta(seconds=6)).isoformat()},
    {'scan_checked_at':(NOW-timedelta(seconds=1)).isoformat()}, {'retain_until':NOW.isoformat()}])
def test_invalid_or_approving_observations_are_not_signed(change):
    with pytest.raises(EvidenceUnavailable): sign(receipt(**change))


@pytest.mark.parametrize('change', [{'secret':b'x'*31}, {'secret':bytearray(b'x'*32)}, {'purposes':frozenset()},
    {'purposes':{'purchase_contract'}}, {'purposes':frozenset({'purchase_contract','mail_content'})},
    {'workspace_id':uid(9)}, {'valid_until':NOW}, {'valid_until':NOW+timedelta(days=2)},
    {'valid_from':NOW+timedelta(seconds=1)}, {'scanner_version':'wrong'}, {'scan_policy_version':'wrong'}])
def test_key_requires_explicit_contract_purposes_and_current_configuration(change):
    with pytest.raises(EvidenceUnavailable): sign(key=replace(KEY, **change))


def test_mail_keys_and_missing_fields_cannot_be_used_for_contracts():
    with pytest.raises(EvidenceUnavailable): sign(key=MAIL_KEY)
    for name in receipt():
        value = receipt(); value.pop(name)
        with pytest.raises(EvidenceUnavailable): sign(value)


def test_actual_internal_scan_output_can_be_signed_without_gaining_authority(monkeypatch):
    import asyncio
    from tests.test_acquisition_contract_document_scan import registered, POLICY
    from tests.test_acquisition_evidence_scan import daemon
    daemon(monkeypatch)
    execute, _ = registered()
    observed = asyncio.run(execute())
    signed = sign(observed, key=replace(KEY, scanner_version=POLICY.expected_version, scan_policy_version=POLICY.policy_version))
    assert signed['p_contract'] == observed['contract_id'] and signed['p_version'] == observed['contract_version']
    payload = json.loads(signed['p_observation'])
    assert payload['sha256'] == observed['sha256'] and payload['scan_status'] == 'no_detection'
    assert not {'execution_authorized','legal_review_approved','preview_authorized'} & signed.keys()


@pytest.mark.parametrize('options', [{'request_id':True}, {'actor_id':'user'}, {'session_id':None}, {'key':None}])
def test_identity_and_key_types_fail_closed(options):
    with pytest.raises(EvidenceUnavailable): sign(**options)
