"""Real local PostgREST evidence read lifecycle; no scanner or hosted services."""


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
    status, _ = request('/rpc/register_acquisition_evidence', token(), {
        'p_id': artifact, 'p_workspace': workspace, 'p_campaign': campaign,
        'p_purpose': 'mail_content', 'p_sha256': 'a' * 64, 'p_byte_size': 123,
        'p_media_type': 'application/pdf', 'p_policy': policy,
        'p_note': 'Synthetic local HTTP evidence provenance.'})
    if status != 200:
        raise AssertionError('Evidence HTTP registration failed')
    path = '/rpc/acquisition_evidence_scan_state'
    body = {'p_workspace': workspace, 'p_campaign': campaign, 'p_artifact': artifact}

    def check(expected):
        status, row = request(path, token(), body)
        fields = {'workspace_id', 'campaign_id', 'artifact_id', 'status', 'quarantined',
                  'observation_id', 'checked_at', 'preview_authorized', 'content_approved', 'execution_authorized'}
        if status != 200 or set(row) != fields:
            raise AssertionError('Evidence HTTP scan response shape changed')
        if (row['workspace_id'], row['campaign_id'], row['artifact_id']) != (workspace, campaign, artifact):
            raise AssertionError('Evidence HTTP scan scope changed')
        if row['status'] != expected or row['quarantined'] is not False or row['observation_id'] is not None:
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
    status, _ = request('/rpc/revoke_acquisition_evidence', token(), {
        'p_id': '99200000-0000-4000-8000-000000000779', **body,
        'p_reason': 'Synthetic local HTTP evidence withdrawal.'})
    if status != 200:
        raise AssertionError('Evidence HTTP withdrawal failed')
    check('revoked')
    if db.query('SELECT count(*) AS n FROM public.acquisition_evidence_verifications')[0]['n'] != 0:
        raise AssertionError('Read-only evidence checks created scan observations')
    return ['evidence real RPC pending-to-withdrawn lifecycle', 'evidence HTTP tenant and anonymous isolation',
            'evidence HTTP campaign binding', 'evidence HTTP read never grants approval or creates scans']
