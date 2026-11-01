"""Actual API capture of pending-signature evidence, without execution claims."""
from fastapi.testclient import TestClient
DOCUMENT='af960000-0000-4000-8000-000000000001'
ATTEMPT='af960000-0000-4000-8000-000000000002'


def verify_pending_document_http(db,app,drops,headers,foreign,workspace,contract,policy,rpc):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/3/documents'
    body=dict(id=DOCUMENT,purpose='purchase_contract',expected_sha256='c'*64,expected_byte_size=123,
              media_type='application/pdf',retention_policy_id=policy,
              provenance_note='Synthetic returned purchase document captured for independent execution review.')
    before=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        for identity in (foreign,{}):
            if client.post(path,json=body,headers=identity).status_code not in (401,403):
                raise AssertionError('Pending document registration crossed workspace/session')
        drops['rpc/register_contract_document']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Pending document response-loss recovery failed: {lost.status_code} {retry.status_code}')
        if retry.json()['bytes_verified'] or retry.json()['execution_authorized']:
            raise AssertionError('Pending registration implied verification or execution')
        page=client.get(path,params={'purpose':'purchase_contract'},headers=headers)
        if page.status_code!=200 or not any(row['artifact_id']==DOCUMENT and row['status']=='pending_verification' and not row['legal_review_approved'] for row in page.json()['items']):
            raise AssertionError('New pending document missing from unverified history')
        wrong=client.post(path.replace('/versions/3/','/versions/2/'),json=body|{'id':ATTEMPT},headers=headers)
        if wrong.status_code!=409:raise AssertionError('Pending document accepted stale terms version')
    db.query("UPDATE private.acquisition_evidence_upload_slots SET started_at=started_at-interval '121 seconds',expires_at=expires_at-interval '121 seconds'")
    admitted=rpc('admit_contract_document_upload',dict(p_attempt=ATTEMPT,p_workspace=workspace,p_contract=contract,p_version=3,p_artifact=DOCUMENT,p_purpose='purchase_contract'))
    if not admitted['admitted'] or admitted['execution_authorized']:
        raise AssertionError('Pending document admission did not preserve nonexecuting capture')
    if before!=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):
        raise AssertionError('Document capture rewrote reviewed terms')
    if db.query('SELECT acquisition_status,acquisition_version,stage FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'pending_signature','acquisition_version':3,'stage':'offer_made'}]:
        raise AssertionError('Pending document capture changed contract lifecycle')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id=%s",[DOCUMENT])!=[{'n':1}]:
        raise AssertionError('Pending document retry duplicated audit')
