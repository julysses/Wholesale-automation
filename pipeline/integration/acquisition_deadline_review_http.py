"""Deadline API against real local PostgREST with separately prepared synthetic contract."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
from fastapi.testclient import TestClient
from tools.acquisition_contract_attestation import build_contract_scan_attestation


def identity(n):return f'af990000-0000-4000-8000-{n:012d}'


def verify_deadline_http(db,app,drops,headers,foreign,workspace,admin,rpc,retention_policy,key,observed,review_policy):
    contract,document,scan,terms_id,basis,signature_policy,signature,transition,policy,review,withdrawal=[identity(n) for n in range(1,12)]
    lead,prop,owner,relationship,analysis,offer,approval=[identity(n) for n in range(20,27)]
    db.query("INSERT INTO public.leads(id,property_address,city,owner_first_name,owner_last_name) VALUES(%s,'902 Deadline Fixture','Dallas','Synthetic','Seller')",[lead])
    db.query("INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES(%s,'TX','Dallas','synthetic-deadline-http',%s)",[prop,lead])
    scope={'p_workspace':workspace}
    rpc('bind_acquisition_lead',scope|{'p_lead':lead,'p_property':prop})
    rpc('create_acquisition_owner',scope|{'p_id':owner,'p_lead':lead})
    rpc('associate_acquisition_owner',scope|{'p_id':relationship,'p_owner':owner,'p_lead':lead,
        'p_relationship':'reported_owner','p_note':'Synthetic reported ownership only, not a title finding'})
    rpc('reserve_acquisition_analysis',scope|{'p_id':analysis,'p_lead':lead,
        'p_inputs':{'cases':{case:{'strategy':'fix_and_flip'} for case in ('base','downside','upside')}}})
    snapshot=rpc('read_acquisition_calculation',scope|{'p_id':analysis},service=True)
    outputs={'status':'calculated','calculation_version':'acquisition-underwriting-v1','strategy':'fix_and_flip',
        'cases':{case:{'status':'calculated','mao':'150000.00','proposed_offer_range':{'low':'120000.00','high':'150000.00'}}
                 for case in ('base','downside','upside')},'binding_offer':False,'human_approval_required':True}
    rpc('complete_acquisition_calculation',scope|{'p_id':analysis,'p_input_hash':snapshot['input_hash'],'p_outputs':outputs},service=True)
    rpc('propose_acquisition_offer',scope|{'p_id':offer,'p_analysis':analysis,'p_case':'base','p_amount':140000,'p_note':'Synthetic reviewable amount only'})
    rpc('review_acquisition_offer',scope|{'p_id':approval,'p_offer':offer,'p_expected_sequence':1,'p_status':'amount_approved',
        'p_note':'Synthetic internal review only','p_review_notes':{name:'Synthetic unresolved review, not verified facts'
        for name in ('title','liens','occupancy','valuation','repairs','financing','downside')}})
    rpc('create_acquisition_contract_draft',dict(p_id=contract,p_workspace=workspace,p_offer=offer,p_offer_sequence=2,
        p_relationship=relationship,p_name='Synthetic separate date-only agreement for deadline recovery'))
    rpc('register_contract_document',dict(p_id=document,p_workspace=workspace,p_contract=contract,p_version=1,
        p_purpose='purchase_contract',p_sha256='d'*64,p_byte_size=123,p_media_type='application/pdf',p_policy=retention_policy,
        p_note='Synthetic calendar-only agreement; never a signed or live seller contract.'))
    state=rpc('contract_document_state',dict(p_workspace=workspace,p_contract=contract,p_version=1,p_artifact=document))
    evidence=observed|{name:state[name] for name in ('workspace_id','contract_id','contract_version','artifact_id','purpose','media_type','retain_until','retention_policy_id','checked_at')}
    evidence.update(sha256='d'*64,byte_size=123,scan_checked_at=state['checked_at'],registry_checked_at=state['checked_at'])
    signed=build_contract_scan_attestation(evidence,request_id=UUID(scan),actor_id=UUID(admin),session_id=UUID(admin),key=key,clock=lambda:datetime.now(timezone.utc))
    rpc('record_contract_document_verification',signed)
    terms=dict(purchase_price_cents=14000000,earnest_money_cents=0,assignment_allowed=False,
        assignment_provisions='Synthetic written consent requirement.',effective={'precision':'date','calendar_date':'2026-11-01'},
        inspection_deadline={'precision':'unknown'},closing_deadline={'precision':'date','calendar_date':'2026-11-20'},
        sources=[dict(term=name,artifact_id=document,artifact_version=1,sha256='d'*64,locator='Synthetic original clause')
                 for name in ('purchase_price','earnest_money','assignment','effective','closing_deadline')],
        note='Synthetic original calendar dates remain unchanged during reviewed interpretation.')
    rpc('save_contract_terms',dict(p_id=terms_id,p_workspace=workspace,p_contract=contract,p_expected_version=1,p_terms=terms))
    expiry=(datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat()
    rpc('record_contract_review',dict(p_id=basis,p_workspace=workspace,p_contract=contract,p_version=2,p_kind='contract_review',
        p_expected_sequence=0,p_status='approved',p_artifact=document,p_verification=scan,p_policy=review_policy,
        p_expires=expiry,p_personally_reviewed=True,p_note='Synthetic reviewed contract source for signature preparation only.'))
    # Explicit local fixture policy provisioning; no production or application policy writer.
    db.query("""INSERT INTO private.acquisition_signature_policies(id,workspace_id,contract_id,contract_version,
        reviewer_id,basis_policy_id,artifact_id,source_version,sha256,template_approval_ref,approved_by,valid_from,valid_until,max_review_seconds)
        SELECT %s,workspace_id,contract_id,contract_version,actor_id,policy_id,artifact_id,source_version,sha256,
        %s,actor_id,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',600
        FROM public.acquisition_contract_reviews WHERE id=%s""",[signature_policy,terms_id,basis])
    rpc('record_signature_review',dict(p_id=signature,p_workspace=workspace,p_contract=contract,p_version=2,p_expected_sequence=0,
        p_status='approved',p_basis=basis,p_policy=signature_policy,p_expires=expiry,p_personally_reviewed=True,
        p_note='Synthetic explicit signature release without signing or sending.'))
    rpc('record_contract_transition',dict(p_id=transition,p_workspace=workspace,p_contract=contract,p_expected_version=2,
        p_expected_sequence=0,p_expected_status='draft',p_target_status='pending_signature',
        p_reason='Synthetic explicit awaiting-signature status without a binding transaction.'))
    db.query("""INSERT INTO private.acquisition_contract_review_policies(id,workspace_id,kind,purpose,reviewer_id,
        max_review_seconds,valid_from,valid_until,reviewed_by,approval_ref)
        SELECT %s,workspace_id,'deadline_resolution','purchase_contract',reviewer_id,max_review_seconds,
        valid_from,valid_until,reviewed_by,approval_ref FROM private.acquisition_contract_review_policies WHERE id=%s""",[policy,review_policy])
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/deadline-reviews'
    body=dict(id=review,expected_version=2,expected_sequence=0,status='approved',artifact_id=document,verification_id=scan,
        policy_id=policy,expires_at=expiry,personally_reviewed=True,note='Synthetic personal review of the original date and cited explicit time.',
        term='closing_deadline',original_review_id=None,resolution=dict(term='closing_deadline',calendar_date='2026-11-20',
            local_time='17:00:00',time_zone='America/Chicago',resolved_instant='2026-11-20T17:00:00-06:00',
            basis='explicit_document_time',rationale='Synthetic source explicitly states this time for the preserved calendar date.',
            source=dict(term='closing_deadline',artifact_id=document,artifact_version=1,sha256='d'*64,locator='Synthetic closing clause')))
    history=db.query('SELECT version,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        for auth in (foreign,{}):
            if client.post(path,json=body,headers=auth).status_code not in (401,403):
                raise AssertionError('Deadline review crossed workspace or session')
        drops['rpc/record_deadline_resolution_review']=True
        lost=client.post(path,json=body,headers=headers);retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Deadline committed-response recovery failed: {lost.status_code} {retry.status_code} {retry.text}')
        if lost.headers.get('X-Acquisition-Deadline-Review-Rejected') or retry.json()['interpretation_review_id']!=review or retry.json()['approval_current'] or retry.json()['execution_authorized']:
            raise AssertionError('Deadline historical receipt lost identity or claimed authority')
        conflict=client.post(path,json=body|{'note':'Changed original request must not replace the persisted interpretation.'},headers=headers)
        if conflict.status_code!=409 or conflict.headers.get('X-Acquisition-Deadline-Review-Rejected')!='true':
            raise AssertionError('Deadline conflicting retry was not definitively rejected')
        db.query('UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id=%s',[policy])
        if not client.post(path,json=body,headers=headers).json()['duplicate']:
            raise AssertionError('Deadline historical recovery disappeared after policy revocation')
        removed=body|dict(id=withdrawal,expected_sequence=1,status='withdrawn',original_review_id=review,resolution=None,personally_reviewed=False,expires_at=None)
        drops['rpc/record_deadline_resolution_review']=True
        lost=client.post(path,json=removed,headers=headers);retry=client.post(path,json=removed,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['interpretation_review_id']!=review:
            raise AssertionError('Deadline withdrawal lost its original identity during exact recovery')
    if history!=db.query('SELECT version,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):
        raise AssertionError('Deadline API rewrote signed calendar precision or history')
    if db.query('SELECT acquisition_status,acquisition_version FROM public.deals WHERE id=%s',[contract])!=[dict(acquisition_status='pending_signature',acquisition_version=2)]:
        raise AssertionError('Deadline API advanced contract lifecycle')
    for request_id in (review,withdrawal):
        if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id=%s",[request_id])!=[{'n':1}]:
            raise AssertionError('Deadline API recovery duplicated immutable audit')
