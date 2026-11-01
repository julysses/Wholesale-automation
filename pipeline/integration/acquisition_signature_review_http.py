"""Signature review API against actual local PostgREST, including lost commit replies."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

POLICY='af940000-0000-4000-8000-000000000001'
BASIS='af940000-0000-4000-8000-000000000002'
RELEASE='af940000-0000-4000-8000-000000000003'
WITHDRAW='af940000-0000-4000-8000-000000000004'
TERMS='af940000-0000-4000-8000-000000000005'


def verify_signature_http(db,app,drops,headers,foreign,workspace,contract,terms_body,review_body):
    root=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}'
    terms=terms_body['terms'] | {'earnest_money_cents':0,
        'note':'Synthetic known earnest-money term prepared before a separate signature release review.'}
    source=next(s for s in terms['sources'] if s['term']=='purchase_price')
    terms['sources']=[*terms['sources'],source|{'term':'earnest_money'}]
    basis=review_body|{'id':BASIS,'note':'Synthetic review of exact version three before distinct signature release.'}
    with TestClient(app) as client:
        saved=client.post(root+'/terms',json={'id':TERMS,'expected_version':2,'terms':terms},headers=headers)
        if saved.status_code!=200 or saved.json()['version']!=3:
            raise AssertionError('Signature preparation terms unavailable')
        reviewed=client.post(root+'/versions/3/reviews/contract_review',json=basis,headers=headers)
        if reviewed.status_code!=200:
            raise AssertionError('Signature preparation contract review unavailable')
    # Synthetic, explicitly local policy fixture, never an application provisioning path.
    db.query("""INSERT INTO private.acquisition_signature_policies(id,workspace_id,contract_id,contract_version,
        reviewer_id,basis_policy_id,artifact_id,source_version,sha256,template_approval_ref,approved_by,
        valid_from,valid_until,max_review_seconds)
        SELECT %s,workspace_id,contract_id,contract_version,actor_id,policy_id,artifact_id,source_version,sha256,
        %s,actor_id,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',600
        FROM public.acquisition_contract_reviews WHERE id=%s""",[POLICY,TERMS,BASIS])
    path=root+'/versions/3/signature-review'
    body=dict(id=RELEASE,expected_sequence=0,status='approved',basis_review_id=BASIS,policy_id=POLICY,
        expires_at=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),personally_reviewed=True,
        note='Synthetic signature release review only; no contract sent or signed.')
    with TestClient(app) as client:
        choices=client.get(path+'/candidate',headers=headers)
        if choices.status_code!=200 or choices.headers.get('cache-control')!='no-store' or choices.json()['status']!='ready_for_human_review':
            raise AssertionError('Mounted signature choices unavailable')
        choice=choices.json()['candidate']
        if choice['basis_review_id']!=BASIS or choice['artifact_id']!=basis['artifact_id'] or choice['source_version']!=1 or choice['policy_id']!=POLICY:
            raise AssertionError('Mounted signature choices lost original source or basis')
        body.update(basis_review_id=choice['basis_review_id'],policy_id=choice['policy_id'],expected_sequence=choice['expected_sequence'])
        initial=client.get(path,headers=headers)
        if initial.status_code!=200 or initial.json()['status']!='not_reviewed':
            raise AssertionError('Signature initial state unavailable')
        drops['rpc/record_signature_review']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Signature actual commit-loss recovery failed: {lost.status_code} {retry.status_code}')
        if lost.headers.get('X-Acquisition-Signature-Rejected') or retry.json()['approval_current'] or retry.json()['execution_authorized']:
            raise AssertionError('Signature historical receipt grants authority')
        current=client.get(path,headers=headers)
        if current.status_code!=200 or not current.json()['approval_current'] or current.json()['basis_review_id']!=BASIS:
            raise AssertionError('Signature current exact basis unavailable')
        for identity in (foreign,{}):
            if client.get(path+'/candidate',headers=identity).status_code not in (401,403):
                raise AssertionError('Signature choices crossed workspace/session')
            for method in ('get','post'):
                response=getattr(client,method)(path,headers=identity,**({'json':body} if method=='post' else {}))
                if response.status_code not in (401,403):raise AssertionError('Signature workspace/session bypass')
        changed=client.post(path,json=body|{'note':'Changed release request must not replace the original committed decision.'},headers=headers)
        if changed.status_code!=409 or changed.headers.get('X-Acquisition-Signature-Rejected')!='true':
            raise AssertionError('Signature conflicting request did not reject definitively')
        if client.post(path.replace('/versions/3/','/versions/4/'),json=body,headers=headers).status_code!=403:
            raise AssertionError('Signature nonexistent target accepted')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_signature_review' AND entity_id=%s",[RELEASE])!=[{'n':1}]:
        raise AssertionError('Signature retry duplicated audit')
    if db.query('SELECT acquisition_status,stage FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'draft','stage':'offer_made'}]:
        raise AssertionError('Signature review changed legal lifecycle')
    return path,body


def verify_signature_revocation_http(db,app,drops,headers,path,body):
    db.query('UPDATE private.acquisition_activation SET enabled=false WHERE singleton')
    try:
        with TestClient(app) as client:
            current=client.get(path,headers=headers)
            if current.status_code!=200 or current.json()['approval_current'] or current.json()['status']!='requires_review':
                raise AssertionError('Signature approval survived revoked source or pause')
            choices=client.get(path+'/candidate',headers=headers)
            if choices.status_code!=200 or choices.json()['status']!='paused' or choices.json()['candidate'] is not None or choices.json()['withdrawal']['basis_review_id']!=BASIS or choices.json()['withdrawal']['review_id']!=RELEASE:
                raise AssertionError('Signature choices lost independent original withdrawal during hold')
            if not client.post(path,json=body,headers=headers).json()['duplicate']:
                raise AssertionError('Signature historical retry lost after pause')
            withdrawal=body|dict(id=WITHDRAW,expected_sequence=1,status='withdrawn',expires_at=None,personally_reviewed=False)
            drops['rpc/record_signature_review']=True
            lost=client.post(path,json=withdrawal,headers=headers)
            retry=client.post(path,json=withdrawal,headers=headers)
            if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['status']!='withdrawn':
                raise AssertionError('Signature withdrawal commit-loss recovery failed')
            if client.get(path,headers=headers).json()['status']!='withdrawn':
                raise AssertionError('Signature withdrawal missing from state')
    finally:db.query('UPDATE private.acquisition_activation SET enabled=true WHERE singleton')
    if db.query('SELECT count(*) AS n FROM public.acquisition_signature_reviews WHERE id IN (%s,%s)',[RELEASE,WITHDRAW])!=[{'n':2}]:
        raise AssertionError('Signature decisions duplicated')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_signature_review' AND entity_id=%s",[WITHDRAW])!=[{'n':1}]:
        raise AssertionError('Signature withdrawal audit duplicated')
