"""Mounted original-document link writes over real local PostgREST and RLS."""
from fastapi.testclient import TestClient


def verify_links_http(db, app, drops, headers, foreign, workspace, contract, artifact, verification, digest):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/document-links'
    body={'id':'af930000-0000-4000-8000-000000000001','source_version':1,'artifact_id':artifact,
          'verification_id':verification,'sha256':digest,'note':'Synthetic earlier original supports version two without copied bytes or approval.'}
    original=db.query('SELECT row_to_json(a)::text AS original FROM public.acquisition_evidence_artifacts a WHERE id=%s',[artifact])
    drops['rpc/link_contract_document']=True
    with TestClient(app) as client:
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Mounted link commit-loss recovery failed: {lost.status_code} {retry.status_code}')
        if lost.headers.get('X-Acquisition-Link-Rejected') or retry.headers.get('cache-control')!='no-store' or retry.json()['review_approved'] or retry.json()['execution_authorized']:
            raise AssertionError('Link receipt implied approval or unsafe retry state')
        current=client.get(path.replace('/document-links','/references/')+artifact,headers=headers)
        if current.status_code!=200 or current.json()['reference_type']!='linked' or current.json()['source_version']!=1 or current.json()['link_id']!=body['id']:
            raise AssertionError('Linked reference lost original source identity')
        changed=client.post(path,json=body|{'note':'Changed source reference request must conflict, not replace history.'},headers=headers)
        if changed.status_code!=409 or changed.headers.get('X-Acquisition-Link-Rejected')!='true':
            raise AssertionError('Changed link retry was not definitively rejected')
        for identity in (foreign,{}):
            if client.post(path,json=body,headers=identity).status_code not in (401,403):
                raise AssertionError('Link API crossed workspace/session boundary')
        if client.post(path.replace('/versions/2/','/versions/3/'),json=body,headers=headers).status_code!=403:
            raise AssertionError('Link API accepted a nonexistent target version')
    if db.query('SELECT row_to_json(a)::text AS original FROM public.acquisition_evidence_artifacts a WHERE id=%s',[artifact])!=original:
        raise AssertionError('Link mutated original document metadata')
    if db.query('SELECT count(*) AS n FROM public.acquisition_contract_document_links WHERE id=%s',[body['id']])!=[{'n':1}]:
        raise AssertionError('Link retry duplicated original-source reference')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document_link' AND entity_id=%s",[body['id']])!=[{'n':1}]:
        raise AssertionError('Link retry duplicated immutable audit')
    return path,body


def verify_link_withdrawal_http(db,app,drops,headers,foreign,path,body):
    withdrawal={'id':'af930000-0000-4000-8000-000000000002','reason':'Synthetic withdrawal after the source verification loses current authority.'}
    target=path+'/'+body['id']+'/withdrawals'
    drops['rpc/revoke_contract_document_link']=True
    db.query('UPDATE private.acquisition_activation SET enabled=false WHERE singleton')
    try:
        with TestClient(app) as client:
            historical=client.post(path,json=body,headers=headers)
            if historical.status_code!=200 or not historical.json()['duplicate'] or historical.json()['review_approved']:
                raise AssertionError('Paused original link retry lost historical receipt')
            lost=client.post(target,json=withdrawal,headers=headers)
            retry=client.post(target,json=withdrawal,headers=headers)
            if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['execution_authorized']:
                raise AssertionError('Link withdrawal exact recovery unavailable while paused')
            state=client.get(path.replace('/document-links','/references/')+body['artifact_id'],headers=headers)
            if state.status_code!=200 or state.json()['status']!='reference_withdrawn' or state.json()['verification_id'] is not None:
                raise AssertionError('Withdrawn link retained current evidence authority')
            for identity in (foreign,{}):
                if client.post(target,json=withdrawal,headers=identity).status_code not in (401,403):
                    raise AssertionError('Link withdrawal crossed workspace/session boundary')
            conflict=client.post(target,json=withdrawal|{'reason':'Different reason must not overwrite this prior withdrawal.'},headers=headers)
            if conflict.status_code!=409 or conflict.headers.get('X-Acquisition-Link-Rejected')!='true':
                raise AssertionError('Link withdrawal conflict was not rejected')
    finally:
        db.query('UPDATE private.acquisition_activation SET enabled=true WHERE singleton')
    if db.query('SELECT count(*) AS n FROM public.acquisition_contract_document_link_revocations WHERE id=%s',[withdrawal['id']])!=[{'n':1}]:
        raise AssertionError('Link withdrawal retry duplicated revocation')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document_link' AND entity_id=%s",[body['id']])!=[{'n':2}]:
        raise AssertionError('Link and withdrawal audit history changed')
