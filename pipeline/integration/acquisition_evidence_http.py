"""Real local PostgREST evidence lifecycle with synthetic signed observations only."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone


def verify_evidence_http(db, request, token, admin, other, workspace):
    campaign = '91000000-0000-4000-8000-000000000777'
    policy = '99200000-0000-4000-8000-000000000777'
    artifact = '99200000-0000-4000-8000-000000000778'
    # Only the disposable database owner provisions this synthetic reviewed policy.
    db.query("""INSERT INTO private.acquisition_evidence_policies
        (id,workspace_id,purpose,version,retention_seconds,valid_from,valid_until,approval_ref,reviewed_by,reviewed_at)
        VALUES(%s,%s,'mail_content',1,86400,'2026-01-01','2099-01-01',%s,%s,'2026-01-01')""",
        [policy, workspace, policy, admin])
    status, _ = request('/rpc/create_acquisition_campaign', token(), {
        'p_id': campaign, 'p_workspace': workspace, 'p_name': 'Synthetic evidence HTTP',
        'p_channel': 'direct_mail', 'p_budget_cents': 50000, 'p_currency': 'USD'})
    if status != 200:
        raise AssertionError('Evidence HTTP campaign setup failed')
    status, registration = request('/rpc/register_acquisition_evidence', token(), {
        'p_id': artifact, 'p_workspace': workspace, 'p_campaign': campaign,
        'p_purpose': 'mail_content', 'p_sha256': 'a' * 64, 'p_byte_size': 123,
        'p_media_type': 'application/pdf', 'p_policy': policy,
        'p_note': 'Synthetic local HTTP evidence provenance.'})
    if status != 200:
        raise AssertionError('Evidence HTTP registration failed')
    path = '/rpc/acquisition_evidence_scan_state'
    body = {'p_workspace': workspace, 'p_campaign': campaign, 'p_artifact': artifact}

    def check(expected, quarantined=False, observation=None):
        status, row = request(path, token(), body)
        fields = {'workspace_id', 'campaign_id', 'artifact_id', 'status', 'quarantined',
                  'observation_id', 'checked_at', 'preview_authorized', 'content_approved', 'execution_authorized'}
        if status != 200 or set(row) != fields:
            raise AssertionError('Evidence HTTP scan response shape changed')
        if (row['workspace_id'], row['campaign_id'], row['artifact_id']) != (workspace, campaign, artifact):
            raise AssertionError('Evidence HTTP scan scope changed')
        if row['status'] != expected or row['quarantined'] is not quarantined or row['observation_id'] != observation:
            raise AssertionError('Evidence HTTP lifecycle state incorrect')
        if any(row[field] is not False for field in ('preview_authorized', 'content_approved', 'execution_authorized')):
            raise AssertionError('Evidence HTTP scan granted authority')

    check('not_scanned')
    if request(path, token(other), body)[0] != 403:
        raise AssertionError('Evidence HTTP cross-workspace read accepted')
    if request(path, None, body)[0] != 401:
        raise AssertionError('Evidence HTTP anonymous read accepted')
    if request(path, token(), {**body, 'p_campaign': artifact})[0] != 403:
        raise AssertionError('Evidence HTTP mismatched campaign accepted')
    # The daemon is simulated. Only the private disposable configuration receives this key.
    key_id = '99300000-0000-4000-8000-000000000777'
    secret = secrets.token_bytes(32)
    scanner_version = 'ClamAV 1.4.3/12345/Thu Oct 29 00:00:00 2026'
    db.query("""INSERT INTO private.acquisition_evidence_verification_keys
        (id,workspace_id,secret,scanner_version,scan_policy_version,valid_from,valid_until,reviewed_by,approval_ref)
        VALUES(%s,%s,%s,%s,'synthetic-http-v1',clock_timestamp()-interval '1 hour',
               clock_timestamp()+interval '1 hour',%s,%s)""", [key_id, workspace, secret, scanner_version, admin, key_id])

    def signed(identity, scan_status):
        now = datetime.now(timezone.utc).isoformat()
        observation = json.dumps({'sha256': 'a' * 64, 'byte_size': 123, 'media_type': 'application/pdf',
            'retain_until': registration['retain_until'], 'retention_policy_id': policy,
            'checked_at': now, 'scan_checked_at': now, 'registry_checked_at': now,
            'scanner': 'clamav-instream-v1', 'scanner_version': scanner_version,
            'scan_policy_version': 'synthetic-http-v1', 'scan_status': scan_status}, sort_keys=True, separators=(',', ':'))
        context = [identity, workspace, campaign, artifact, admin, admin, key_id]
        message = 'acquisition-evidence-attestation-v1\n' + '\n'.join(context) + '\n' + observation
        return {**body, 'p_id': identity, 'p_actor': admin, 'p_session': admin, 'p_key': key_id,
                'p_observation': observation, 'p_signature': hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()}

    record_path = '/rpc/record_acquisition_evidence_verification'
    clean_id = '99300000-0000-4000-8000-000000000778'
    clean = signed(clean_id, 'no_detection')
    if request(record_path, token(), {**clean, 'p_signature': '0' * 64})[0] != 403:
        raise AssertionError('Evidence HTTP invalid signature accepted')
    for duplicate in (False, True):
        status, receipt = request(record_path, token(), clean)
        if status != 200 or receipt.get('duplicate') is not duplicate or receipt.get('verification_id') != clean_id:
            raise AssertionError('Evidence HTTP exact signed retry did not reconcile')
        if any(receipt.get(field) is not False for field in ('preview_authorized', 'content_approved', 'execution_authorized')):
            raise AssertionError('Evidence signed receipt granted approval')
    check('no_detection_observed', observation=clean_id)
    from acquisition_content_http import verify_content_http
    after_revocation = verify_content_http(db, request, token, other, workspace, campaign, artifact, clean_id)
    db.query('UPDATE private.acquisition_evidence_verification_keys SET revoked_at=clock_timestamp() WHERE id=%s', [key_id])
    check('requires_review')
    after_revocation()
    # A different reviewed synthetic key is used for subsequent observations; never un-revoke a key.
    key_id = '99300000-0000-4000-8000-000000000779'
    secret = secrets.token_bytes(32)
    db.query("""INSERT INTO private.acquisition_evidence_verification_keys
        (id,workspace_id,secret,scanner_version,scan_policy_version,valid_from,valid_until,reviewed_by,approval_ref)
        VALUES(%s,%s,%s,%s,'synthetic-http-v1',clock_timestamp()-interval '1 hour',
               clock_timestamp()+interval '1 hour',%s,%s)""", [key_id, workspace, secret, scanner_version, admin, key_id])
    for identity, scan_status in (('99300000-0000-4000-8000-000000000780', 'detected'),
                                  ('99300000-0000-4000-8000-000000000781', 'no_detection')):
        if request(record_path, token(), signed(identity, scan_status))[0] != 200:
            raise AssertionError('Evidence HTTP signed observation failed')
        check('quarantined', quarantined=True)
    status, _ = request('/rpc/revoke_acquisition_evidence', token(), {
        'p_id': '99200000-0000-4000-8000-000000000779', **body,
        'p_reason': 'Synthetic local HTTP evidence withdrawal.'})
    if status != 200:
        raise AssertionError('Evidence HTTP withdrawal failed')
    check('revoked', quarantined=True)
    if db.query('SELECT count(*) AS n FROM public.acquisition_evidence_verifications')[0]['n'] != 3:
        raise AssertionError('Evidence HTTP retry/read altered immutable observation count')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_evidence_verification'")[0]['n'] != 3:
        raise AssertionError('Evidence HTTP observation audit count mismatch')
    return ['evidence real RPC pending-to-withdrawn lifecycle', 'evidence HTTP tenant and anonymous isolation',
            'evidence HTTP campaign binding', 'evidence HTTP read never grants approval or creates scans',
            'signed evidence HTTP exact retry and audit convergence', 'evidence HTTP invalid signature rejected',
            'evidence HTTP signer revocation invalidates clean state', 'evidence HTTP later clean observation preserves detection hold',
            'content HTTP candidate scope and deadline', 'content HTTP approval role and expiry denial',
            'content HTTP exact bound approval and retry convergence',
            'content HTTP signer revocation invalidates candidate and approval',
            'content HTTP historical retry and withdrawal preserve immutable binding']
