"""Mounted disposition decisions against real local JWT/PostgREST authority."""
from fastapi.testclient import TestClient


def verify_disposition_review_http(db,app,drops,headers,token,workspace,contract,admin,other,title_body):
    prefix=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2'
    path=prefix+'/disposition-review'
    title,plan,policy,review,hold,withdraw=[f'ae110000-0000-4000-8000-{n:012d}' for n in range(1,7)]
    original=db.query('SELECT to_jsonb(d) AS row FROM public.deals d WHERE id=%s',[contract])
    root=db.query("SELECT r.artifact_id::text,r.source_version,r.sha256,r.policy_id::text FROM public.acquisition_contract_reviews r JOIN public.acquisition_contract_transitions t ON t.execution_review_id=r.id WHERE t.workspace_id=%s AND t.contract_id=%s AND t.contract_version=2 AND t.recorded_status='executed'",[workspace,contract])[0]
    # Synthetic administrative policy fixture only; no application provisioning path.
    db.query("INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id',%s::text,'kind','disposition_findings'))).* FROM private.acquisition_contract_review_policies p WHERE id=%s",[policy,root['policy_id']])
    db.query("INSERT INTO private.acquisition_disposition_policy_scopes(policy_id,workspace_id,reviewer_id,exit_type,legal_source_id,reviewed_by,approval_ref,valid_from,valid_until) VALUES(%s,%s,%s,'wholesale_assignment',%s,%s,%s,clock_timestamp()-interval '1 minute',clock_timestamp()+interval '1 hour')",[policy,workspace,admin,root['artifact_id'],admin,policy])
    citation=dict(artifact_id=root['artifact_id'],artifact_version=root['source_version'],sha256=root['sha256'],locator='Synthetic reviewed original contract clause 14')
    def finding():return dict(finding='satisfactory',note='Synthetic human assessment of original contract and legal requirements.',required_action=None,sources=[citation])
    findings=dict(exit_type='wholesale_assignment',**{name:finding() for name in ('contractual_interest','closing_structure','remaining_obligations')},
        assignment={name:finding() for name in ('assignment_provisions','legal_basis','seller_disclosure_requirements','assignee_disclosure_requirements')})
    body=dict(id=review,expected_version=2,expected_sequence=0,status='approved',plan_id=plan,original_review_id=None,policy_id=policy,
        expires_at=title_body['expires_at'],personally_reviewed=True,note='Synthetic original disposition review for controlled gateway verification.',findings=findings)
    with TestClient(app) as client:
        prepared=client.post(prefix+'/title-review',json=title_body|dict(id=title,expected_sequence=6),headers=headers)
        if prepared.status_code!=200:raise AssertionError('Disposition fixture could not renew original title: '+str(prepared.status_code))
        proposed=client.post(prefix+'/disposition-plan',json=dict(id=plan,expected_version=2,expected_sequence=3,status='proposed',exit_type='wholesale_assignment',original_plan_id=None,note='Synthetic assignment proposal requiring independent disposition review.'),headers=headers)
        if proposed.status_code!=200:raise AssertionError('Disposition fixture could not propose original assignment')
        state=client.get(path,headers=headers)
        if state.status_code!=200 or state.json()['status']!='not_reviewed':raise AssertionError('Mounted disposition initial state unavailable')
        drops['rpc/record_disposition_review']=True
        lost=client.post(path,json=body,headers=headers);retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or 'x-acquisition-disposition-review-rejected' in lost.headers or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError('Disposition committed-response recovery failed: '+str(retry.status_code))
        if retry.json()['approval_current'] or retry.json()['execution_authorized']:raise AssertionError('Disposition receipt granted current authority')
        current=client.get(path,headers=headers)
        if current.status_code!=200 or not current.json()['approval_current'] or current.headers.get('cache-control')!='no-store':raise AssertionError('Disposition current state unavailable')
        conflict=client.post(path,json=body|dict(note='Changed findings request cannot replace original history.'),headers=headers)
        if conflict.status_code!=409 or conflict.headers.get('x-acquisition-disposition-review-rejected')!='true':raise AssertionError('Disposition conflict was not definite')
        for denied in ({},{'Authorization':'Bearer '+token(other)},{'Authorization':'Bearer '+token(role='service_role')}):
            for response in (client.get(path,headers=denied),client.post(path,json=body,headers=denied)):
                if response.status_code not in (401,403):raise AssertionError('Disposition workspace/session boundary failed')
        if client.post(path.replace('/versions/2/','/versions/1/'),json=body,headers=headers).status_code!=409:raise AssertionError('Disposition write moved versions')
        held=body|dict(id=hold,expected_sequence=1,status='requires_resolution',expires_at=None)
        drops['rpc/record_disposition_review']=True
        lost=client.post(path,json=held,headers=headers);retry=client.post(path,json=held,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:raise AssertionError('Disposition hold recovery failed')
        if client.get(path,headers=headers).json()['status']!='requires_resolution':raise AssertionError('Disposition hold retained approval')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        db.query('UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp() WHERE policy_id=%s',[policy])
        try:
            if not client.post(path,json=body,headers=headers).json()['duplicate']:raise AssertionError('Paused disposition history disappeared')
            fresh=client.post(path,json=held|dict(id=withdraw,expected_sequence=2),headers=headers)
            if fresh.status_code!=409:raise AssertionError('Paused disposition accepted a new review')
            cancelled=held|dict(id=withdraw,expected_sequence=2,status='withdrawn',original_review_id=hold,personally_reviewed=False,findings=None)
            drops['rpc/record_disposition_review']=True
            lost=client.post(path,json=cancelled,headers=headers);retry=client.post(path,json=cancelled,headers=headers)
            if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:raise AssertionError('Original disposition withdrawal recovery failed')
            if client.get(path,headers=headers).json()['status']!='withdrawn':raise AssertionError('Disposition withdrawal not current')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
        history=path+'/history'
        page=client.get(history,params={'limit':2},headers=headers)
        if page.status_code!=200:raise AssertionError('Mounted disposition history unavailable')
        data=page.json()
        if [r['id'] for r in data['items']]!=[withdraw,hold] or data['next_before']!=2 or data['approval_current'] or not data['history_only']:
            raise AssertionError('Disposition history order or historical boundary changed')
        following=client.get(history,params={'limit':2,'before':data['next_before']},headers=headers)
        if following.status_code!=200 or [r['id'] for r in following.json()['items']]!=[review] or following.json()['next_before'] is not None:
            raise AssertionError('Disposition history pagination repeated or lost an original')
        for target,status in ((review,'approved'),(hold,'requires_resolution'),(withdraw,'withdrawn')):
            detail=client.get(history+'/'+target,headers=headers)
            if detail.status_code!=200:raise AssertionError('Disposition original detail unavailable')
            data=detail.json();row=data['record']
            if data['approval_current'] or data['execution_authorized'] or row['status']!=status or row['disposition_plan_id']!=plan or row['disposition_title_review_id']!=title:
                raise AssertionError('Disposition detail lost original roots or implied authority')
            if status!='withdrawn' and (row['disposition_findings']!=findings or row['artifact_id']!=root['artifact_id'] or row['source_version']!=root['source_version']):
                raise AssertionError('Disposition detail changed original findings')
            if status=='withdrawn' and (row['disposition_original_review_id']!=hold or row['disposition_findings'] is not None):
                raise AssertionError('Disposition withdrawal replaced original findings')
            if any(k in row for k in ('session_id','request_hash','disposition_policy_snapshot')):raise AssertionError('History exposed private authority metadata')
        for denied in ({},{'Authorization':'Bearer '+token(other)},{'Authorization':'Bearer '+token(role='service_role')}):
            for route in (history,history+'/'+review):
                if client.get(route,headers=denied).status_code not in (401,403):raise AssertionError('Disposition history escaped workspace/role boundary')
        if client.get(history.replace('/versions/2/','/versions/1/')+'/'+review,headers=headers).status_code!=404:raise AssertionError('Disposition history escaped original version')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            if client.get(history,headers=headers).status_code!=200:raise AssertionError('Paused disposition history unavailable')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
        prior_session=db.query('SELECT not_after FROM auth.sessions WHERE id=%s',[admin])[0]['not_after']
        db.query("UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 minute' WHERE id=%s",[admin])
        try:
            if client.get(history,headers=headers).status_code!=403 or client.get(history+'/'+review,headers=headers).status_code!=403:raise AssertionError('Revoked session retained disposition history')
        finally:db.query('UPDATE auth.sessions SET not_after=%s WHERE id=%s',[prior_session,admin])
    if db.query('SELECT to_jsonb(d) AS row FROM public.deals d WHERE id=%s',[contract])!=original:raise AssertionError('Disposition review changed canonical contract')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id IN (%s,%s,%s)",[review,hold,withdraw])!=[{'n':3}]:raise AssertionError('Disposition review duplicated or omitted audit')
