"""Title RPC through real local PostgREST, with synthetic signed evidence only."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import UUID
from tools.acquisition_contract_attestation import build_contract_scan_attestation


def verify_title_review_http(db,rpc,request,token,workspace,contract,document,admin,other,key,observed,review_policy,expiry,app,drops,headers):
    scan,policy,review,hold,withdrawal=[f'ae980000-0000-4000-8000-{n:012d}' for n in range(1,6)]
    db.query("INSERT INTO private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose,reviewed_by,approval_ref,valid_from,valid_until) VALUES(%s,%s,'title_report',%s,%s,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour')",[workspace,str(key.id),admin,document])
    state=rpc('contract_document_state',dict(p_workspace=workspace,p_contract=contract,p_version=2,p_artifact=document))
    evidence=observed|{name:state[name] for name in ('workspace_id','contract_id','contract_version','artifact_id','purpose','media_type','retain_until','retention_policy_id','checked_at')}
    evidence.update(sha256='b'*64,byte_size=123,scan_checked_at=state['checked_at'],registry_checked_at=state['checked_at'])
    signed=build_contract_scan_attestation(evidence,request_id=UUID(scan),actor_id=UUID(admin),session_id=UUID(admin),key=replace(key,purposes=frozenset({'title_report'})),clock=lambda:datetime.now(timezone.utc))
    rpc('record_contract_document_verification',signed)
    db.query("INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id',%s::text,'kind','title_findings','purpose','title_report','title_report_max_age_days',1,'title_report_timezone','UTC'))).* FROM private.acquisition_contract_review_policies p WHERE id=%s",[policy,review_policy])
    source=dict(artifact_id=document,artifact_version=2,sha256='b'*64,locator='Synthetic title report, schedule A')
    findings=dict(report_as_of=dict(precision='date',calendar_date=datetime.now(timezone.utc).date().isoformat(),instant=None),report_as_of_source=source,report_note='Synthetic report cutoff preserved as a calendar date.',
        **{name:dict(finding='satisfactory',note='Synthetic human-reviewed original title finding.',required_action=None,sources=[source]) for name in ('ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession')})
    body=dict(p_id=review,p_workspace=workspace,p_contract=contract,p_version=2,p_expected_sequence=0,p_status='approved',p_artifact=document,p_verification=scan,p_policy=policy,p_expires=expiry,p_personally_reviewed=True,p_note='Synthetic title findings reviewed with original evidence and execution.',p_findings=findings)
    rpc('record_title_review',body)  # Discard a committed reply, then recover exact request.
    recovered=rpc('record_title_review',body)
    if not recovered['duplicate'] or recovered['approval_current'] or recovered['execution_authorized']:raise AssertionError('Title gateway recovery implied authority')
    context=dict(p_workspace=workspace,p_contract=contract,p_version=2)
    if not rpc('title_review_state',context)['approval_current']:raise AssertionError('Title gateway did not retain current exact review')
    for who in (token(other),token(role='service_role')):
        for name,payload in (('record_title_review',body),('title_review_state',context)):
            status,_=request('/rpc/'+name,who,payload)
            if status not in (401,403):raise AssertionError('Title gateway scope or role bypass')
    status,_=request('/rpc/record_title_review',token(),body|dict(p_note='Different request text cannot replace an original title review.'))
    if status!=409:raise AssertionError('Title gateway request conflict accepted')
    hold_body=body|dict(p_id=hold,p_expected_sequence=1,p_status='requires_resolution',p_expires=None)
    rpc('record_title_review',hold_body)
    if rpc('title_review_state',context)['status']!='requires_resolution':raise AssertionError('Title hold failed to supersede approval')
    db.query('UPDATE private.acquisition_activation SET enabled=false')
    try:
        if not rpc('record_title_review',body)['duplicate']:raise AssertionError('Paused title receipt disappeared')
        withdrawal_body=hold_body|dict(p_id=withdrawal,p_expected_sequence=2,p_status='withdrawn',p_personally_reviewed=False,p_findings=None)
        rpc('record_title_review',withdrawal_body)
        if not rpc('record_title_review',withdrawal_body)['duplicate'] or rpc('title_review_state',context)['status']!='withdrawn':raise AssertionError('Original title withdrawal failed')
    finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id IN (%s,%s,%s)",[review,hold,withdrawal])!=[{'n':3}]:raise AssertionError('Title gateway duplicated immutable decisions')

    from fastapi.testclient import TestClient
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/title-review'
    api_review,api_hold,api_withdrawal=[f'ae980000-0000-4000-8000-{n:012d}' for n in range(6,9)]
    api_body=dict(id=api_review,expected_version=2,expected_sequence=3,status='approved',artifact_id=document,
        verification_id=scan,policy_id=policy,expires_at=expiry,personally_reviewed=True,
        note='Synthetic mounted title findings, with exact committed-response recovery.',findings=findings)
    with TestClient(app) as client:
        choice=client.get(path+'/candidate',params={'artifact_id':document},headers=headers)
        if choice.status_code!=200 or choice.json()['status']!='ready_for_human_review' or choice.json()['candidate']['expected_sequence']!=3 or choice.json()['candidate']['report_policy']['timezone']!='UTC':raise AssertionError('Mounted title choices missing current original policy')
        if client.get(path+'/candidate',params={'artifact_id':document},headers={'Authorization':'Bearer '+token(other)}).status_code!=403:raise AssertionError('Mounted title choices leaked across workspaces')
        drops['rpc/record_title_review']=True
        lost=client.post(path,json=api_body,headers=headers)
        retry=client.post(path,json=api_body,headers=headers)
        if lost.status_code!=503 or 'x-acquisition-title-review-rejected' in lost.headers or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError('Mounted title committed-response recovery failed')
        current=client.get(path,headers=headers)
        if current.status_code!=200 or not current.json()['approval_current'] or current.headers.get('cache-control')!='no-store':raise AssertionError('Mounted title current state missing')
        for route in (path,path.replace('/versions/2/','/versions/1/')):
            response=client.post(route,json=api_body,headers={'Authorization':'Bearer '+token(other)})
            if response.status_code not in (401,403,409):raise AssertionError('Mounted foreign title write accepted')
        for denied_headers in ({'Authorization':'Bearer '+token(other)},{}):
            if client.get(path,headers=denied_headers).status_code not in (401,403):raise AssertionError('Mounted title read escaped authentication or workspace scope')
            if client.post(path,json=api_body,headers=denied_headers).status_code not in (401,403):raise AssertionError('Mounted title write escaped authentication or workspace scope')
        conflict=client.post(path,json=api_body|dict(note='Different title request text cannot replace original evidence.'),headers=headers)
        if conflict.status_code!=409 or conflict.headers.get('x-acquisition-title-review-rejected')!='true':raise AssertionError('Mounted title conflict was not definite')
        held=api_body|dict(id=api_hold,expected_sequence=4,status='requires_resolution',expires_at=None)
        drops['rpc/record_title_review']=True
        if client.post(path,json=held,headers=headers).status_code!=503 or not client.post(path,json=held,headers=headers).json()['duplicate']:raise AssertionError('Mounted title hold recovery failed')
        if client.get(path,headers=headers).json()['status']!='requires_resolution':raise AssertionError('Mounted hold retained approval')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            if not client.post(path,json=api_body,headers=headers).json()['duplicate']:raise AssertionError('Mounted historical title receipt lost after pause')
            choice=client.get(path+'/candidate',headers=headers)
            if choice.status_code!=200 or choice.json()['status']!='paused' or choice.json()['candidate'] is not None or choice.json()['resolution'] is not None or choice.json()['withdrawal']['review_id']!=api_hold or choice.json()['withdrawal']['original_status']!='requires_resolution':raise AssertionError('Mounted original title withdrawal depends on selected report')
            withdrawn=held|dict(id=api_withdrawal,expected_sequence=5,status='withdrawn',personally_reviewed=False,findings=None)
            drops['rpc/record_title_review']=True
            lost=client.post(path,json=withdrawn,headers=headers);retry=client.post(path,json=withdrawn,headers=headers)
            if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or client.get(path,headers=headers).json()['status']!='withdrawn':raise AssertionError('Mounted original withdrawal recovery failed')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
        # Exercise the mounted read paths against actual RLS-protected rows.
        history_path=path+'/history'
        first=client.get(history_path,params={'limit':2},headers=headers)
        if first.status_code!=200 or first.headers.get('cache-control')!='no-store':raise AssertionError('Mounted title history unavailable')
        page=first.json()
        if [row['sequence'] for row in page['items']]!=[6,5] or page['next_before']!=5 or not page['history_only'] or page['approval_current'] or page['execution_authorized']:raise AssertionError('Mounted title history ordering or authority invalid')
        seen=[row['id'] for row in page['items']]
        cursor=page['next_before']
        while cursor is not None:
            following=client.get(history_path,params={'limit':2,'before':cursor},headers=headers)
            if following.status_code!=200:raise AssertionError('Mounted title history pagination unavailable')
            page=following.json();seen.extend(row['id'] for row in page['items']);cursor=page['next_before']
        if len(seen)!=6 or len(set(seen))!=6 or set(seen)!={review,hold,withdrawal,api_review,api_hold,api_withdrawal}:raise AssertionError('Mounted title history lost or repeated original decisions')
        for target,status,original in ((api_review,'approved',None),(api_hold,'requires_resolution',None),(api_withdrawal,'withdrawn',api_hold)):
            detail=client.get(history_path+'/'+target,headers=headers)
            if detail.status_code!=200:raise AssertionError('Mounted title history detail unavailable: '+str(detail.status_code))
            body=detail.json();row=body['record']
            if body['approval_current'] or body['execution_authorized'] or row['id']!=target or row['status']!=status or row['title_original_review_id']!=original:raise AssertionError('Mounted original title detail scope or authority changed')
            if status!='withdrawn' and (row['title_findings']!=findings or row['title_sources'][0]['artifact_id']!=document or row['source_version']!=2):raise AssertionError('Mounted history changed original findings or citations')
            if any(name in row for name in ('session_id','request_hash','title_policy_snapshot')):raise AssertionError('Mounted history exposed internal authority metadata')
        for denied_headers in ({'Authorization':'Bearer '+token(other)},{},{'Authorization':'Bearer '+token(role='service_role')}):
            for route in (history_path,history_path+'/'+api_review):
                denied=client.get(route,headers=denied_headers)
                if denied.status_code not in (401,403) or 'x-acquisition-title-review-rejected' in denied.headers:raise AssertionError('Mounted title history escaped workspace/session scope')
        for route in (history_path,history_path+'/'+api_review):
            denied=client.get(route.replace('/versions/2/','/versions/1/'),headers=headers)
            if route.endswith(api_review):
                if denied.status_code!=404:raise AssertionError('Mounted title detail escaped original version')
            elif denied.status_code!=200 or denied.json()['items']:raise AssertionError('Mounted title history mixed versions')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            if client.get(history_path,headers=headers).status_code!=200:raise AssertionError('Paused historical title evidence disappeared')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
        prior_session=db.query('SELECT not_after FROM auth.sessions WHERE id=%s',[admin])[0]['not_after']
        db.query("UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 minute' WHERE id=%s",[admin])
        try:
            if client.get(history_path,headers=headers).status_code!=403 or client.get(history_path+'/'+api_review,headers=headers).status_code!=403:raise AssertionError('Revoked session retained mounted title history')
        finally:db.query('UPDATE auth.sessions SET not_after=%s WHERE id=%s',[prior_session,admin])
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id IN (%s,%s,%s)",[api_review,api_hold,api_withdrawal])!=[{'n':3}]:raise AssertionError('Mounted title replay duplicated audit')

    from acquisition_disposition_plan_http import verify_disposition_plan_http
    verify_disposition_plan_http(db,app,drops,headers,token,workspace,contract,other)

    from acquisition_disposition_review_http import verify_disposition_review_http
    verify_disposition_review_http(db,app,drops,headers,token,workspace,contract,admin,other,api_body)
