"""Disposable real-SQL analysis verification; every AI response is synthetic."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web.api import buyer_analysis as analysis
from web import auth
from web.app import app
from agents.buyer_intelligence_agent import BuyerClassification, BuyerIntelligenceAgent, InvalidBuyerClassification
OWNER='00000000-0000-4000-8000-000000000777'


def verify(db):
    service=Database(); service.query('SET ROLE service_role')
    def buyer():
        bid=str(uuid4())
        db.query("INSERT INTO buyers(id,first_name,last_name,active,tags,buyer_type_ibie,score_version) VALUES(%s,'Synthetic','Analysis',false,ARRAY['custom_note'],'builder',0)",[bid])
        return bid
    def start(bid=None,kind='score',reference=None):
        p={'p_id':reference or str(uuid4()),'p_operator':OWNER}
        analysis.rpc(service,'start_buyer_analysis',{**p,'p_kind':kind,'p_buyer':bid,'p_confirmed':kind=='classify'})
        return p
    def run(p):return analysis.run_step(service,p)
    def get(bid):return db.query('SELECT * FROM buyers WHERE id=%s',[bid])[0]
    bid=buyer()
    # Full SQL snapshot has no PostgREST 1000-row truncation.
    db.query("INSERT INTO buyer_transactions(id,buyer_id,property_address,purchase_date,purchase_price,cash_transaction) SELECT gen_random_uuid(),%s,'Synthetic address','2026-10-01',100000,true FROM generate_series(1,1003)",[bid])
    p=start(bid); assert analysis.status(service,p)['total']==1
    v=run(p); assert v['state']=='complete' and v['applied']==1
    row=get(bid); assert row['score_version']==1 and row['total_purchases_12mo']==1003
    assert 'custom_note' in row['tags']
    assert run(p)['applied']==1 and get(bid)['score_version']==1
    # A commit-ledger failure rolls the buyer patch back; saved evidence resumes later.
    bid=buyer();p=start(bid)
    db.query("CREATE FUNCTION public.test_analysis_rollback() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic commit failure'; END $$")
    db.query('CREATE TRIGGER test_analysis_rollback BEFORE INSERT ON private.buyer_analysis_commits FOR EACH ROW EXECUTE FUNCTION public.test_analysis_rollback()')
    try:run(p)
    except HTTPException as exc:assert exc.status_code==503
    else:raise AssertionError('Commit-ledger failure was not injected')
    assert get(bid)['score_version']==0
    db.query('DROP TRIGGER test_analysis_rollback ON private.buyer_analysis_commits')
    db.query('DROP FUNCTION public.test_analysis_rollback()')
    assert run(p)['applied']==1 and get(bid)['score_version']==1
    # Lost application response is recoverable; no second score increment.
    bid=buyer();p=start(bid);real=analysis.rpc
    def lose(db_,name,params):
        result=real(db_,name,params)
        if name=='apply_buyer_analysis':raise HTTPException(503,'Synthetic response loss')
        return result
    with patch.object(analysis,'rpc',side_effect=lose):
        try:run(p)
        except HTTPException:pass
        else:raise AssertionError('Response loss not injected')
    assert run(p)['applied']==1 and get(bid)['score_version']==1
    # A changed profile or transaction invalidates the retained snapshot, preserving edits.
    for history in [False,True]:
        bid=buyer();p=start(bid);claim={'p_id':p['p_id'],'p_operator':OWNER,'p_buyer':bid,'p_claim':str(uuid4())}
        real(service,'claim_buyer_analysis',claim)
        if history:db.query("INSERT INTO buyer_transactions(id,buyer_id,property_address) VALUES(gen_random_uuid(),%s,'Later synthetic history')",[bid])
        else:db.query("UPDATE buyers SET tags=ARRAY['later_operator_tag'] WHERE id=%s",[bid])
        assert run(p)['stale']==1 and get(bid)['score_version']==0
        if not history:assert get(bid)['tags']==['later_operator_tag']
    # Frozen membership, bounded continuation, result paging.
    previous_active=[r['id'] for r in db.query('SELECT id FROM buyers WHERE active IS TRUE')]
    db.query('UPDATE buyers SET active=false WHERE active IS TRUE')
    active=[buyer() for _ in range(23)]
    db.query('UPDATE buyers SET active=true WHERE id=ANY(%s::uuid[])',['{'+','.join(active)+'}']);p=start()
    late=buyer();db.query('UPDATE buyers SET active=true WHERE id=%s',[late])
    v=run(p);assert v['total']==23 and v['applied']==20 and v['can_run']
    assert len(analysis.status(service,p,20)['items'])==3
    assert run(p)['applied']==23 and get(late)['score_version']==0
    db.query('UPDATE buyers SET active=false WHERE id=ANY(%s::uuid[])',['{'+','.join(active+[late])+'}'])
    db.query('UPDATE buyers SET active=true WHERE id=ANY(%s::uuid[])',['{'+','.join(previous_active)+'}'])
    # Eight independent requests can contend; exactly one synthetic provider attempt.
    bid=buyer();p=start(bid,'classify'); calls=[]
    def classify(self,row,txs):
        calls.append(row['id'])
        return BuyerClassification(row['id'],'landlord',0.9,'Synthetic fixture',['institutional'],'fixture')
    def worker(_):
        conn=Database();conn.query('SET ROLE service_role')
        try:return analysis.run_step(conn,p)
        finally:conn.connection.close()
    with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-not-a-key'}),patch.object(BuyerIntelligenceAgent,'__init__',return_value=None),patch.object(BuyerIntelligenceAgent,'classify_buyer',classify):
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(worker,range(8)))
        assert len(calls)==1 and get(bid)['buyer_type_ibie']=='landlord'
        assert 'institutional' not in get(bid)['tags'] and 'custom_note' in get(bid)['tags']
        assert run(p)['applied']==1 and len(calls)==1
        # Invalid output leaves prior classification untouched.
        bad=buyer();invalid=start(bad,'classify')
        with patch.object(BuyerIntelligenceAgent,'classify_buyer',side_effect=InvalidBuyerClassification('fixture')):
            assert run(invalid)['failed']==1 and get(bad)['buyer_type_ibie']=='builder'
        # Timeout/unknown blocks both same and fresh paid requests, even after cancel.
        uncertain=buyer();held=start(uncertain,'classify')
        with patch.object(BuyerIntelligenceAgent,'classify_buyer',side_effect=TimeoutError('fixture')) as provider:
            assert run(held)['unknown']==1
            assert not run(held)['can_run'] and provider.call_count==1
            real(service,'cancel_buyer_analysis',held)
            assert run(start(uncertain,'classify'))['blocked']==1 and provider.call_count==1
        # Lost claim acknowledgment cannot trigger a paid retry.
        lost=buyer();held=start(lost,'classify')
        real(service,'claim_buyer_analysis',{**held,'p_buyer':lost,'p_claim':str(uuid4())})
        assert analysis.status(service,held)['held']==1 and not run(held)['can_run']
        real(service,'cancel_buyer_analysis',held)
        assert run(start(lost,'classify'))['applied']==1
        # Staged results recover without a second charge.
        saved=buyer();p=start(saved,'classify');before=len(calls)
        with patch.object(analysis,'rpc',side_effect=lose):
            try:run(p)
            except HTTPException:pass
        assert run(p)['applied']==1 and len(calls)==before+1
        # Lost authorization acknowledgment never grants a second paid attempt.
        lost=buyer();p=start(lost,'classify');member={**p,'p_buyer':lost,'p_claim':str(uuid4())}
        real(service,'claim_buyer_analysis',member)
        assert real(service,'authorize_buyer_classification',member)['authorized']
        assert not real(service,'authorize_buyer_classification',member)['authorized']
        before=len(calls);assert not run(p)['can_run'] and len(calls)==before
        real(service,'cancel_buyer_analysis',p)
        assert run(start(lost,'classify'))['blocked']==1
        # Lost retained-result acknowledgments recover the saved response without recharge.
        saved=buyer();p=start(saved,'classify');before=len(calls)
        def lose_stage(db_,name,params):
            value=real(db_,name,params)
            if name=='store_buyer_analysis_result':raise HTTPException(503,'Synthetic receipt loss')
            return value
        with patch.object(analysis,'rpc',side_effect=lose_stage):
            try:run(p)
            except HTTPException:pass
            else:raise AssertionError('Stage response loss was not injected')
        assert run(p)['applied']==1 and len(calls)==before+1
    # Deleted buyers retain review evidence; no resurrection.
    missing=buyer();p=start(missing)
    real(service,'claim_buyer_analysis',{**p,'p_buyer':missing,'p_claim':str(uuid4())})
    db.query('DELETE FROM buyers WHERE id=%s',[missing])
    assert run(p)['missing']==1
    assert not db.query('SELECT id FROM buyers WHERE id=%s',[missing])
    # Receipts are immutable, foreign operators fail, and current approval is checked.
    foreign=str(uuid4());db.query('INSERT INTO auth.users(id) VALUES(%s)',[foreign])
    db.query("INSERT INTO profiles(id,email,status,role) VALUES(%s,%s,'approved','user')",[foreign,foreign+'@example.test'])
    try:real(service,'buyer_analysis_status',{**p,'p_operator':foreign})
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError('Foreign operator read analysis')
    own={'p_id':str(uuid4()),'p_operator':foreign}
    real(service,'start_buyer_analysis',{**own,'p_kind':'score','p_buyer':buyer(),'p_confirmed':False})
    db.query("UPDATE profiles SET status='suspended' WHERE id=%s",[foreign])
    try:analysis.status(service,own)
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError('Revoked operator read analysis')
    try:db.query('DELETE FROM private.buyer_analysis_claims WHERE request_id=%s',[p['p_id']])
    except Exception as exc:assert 'immutable' in str(exc).lower()
    else:raise AssertionError('Retained analysis was deleted')
    # Stop before start is a durable tombstone.
    p={'p_id':str(uuid4()),'p_operator':OWNER};real(service,'cancel_buyer_analysis',p)
    assert analysis.status(service,start(buyer(),reference=p['p_id']))['state']=='stopped'
    # Browser roles cannot inspect retained inputs or invoke service RPCs.
    for role in ['anon','authenticated']:
        conn=Database();conn.query('SET ROLE '+role)
        try:
            for sql in ['SELECT * FROM private.buyer_analysis_claims',"SELECT public.buyer_analysis_status(%s,%s)"]:
                try:conn.query(sql,[p['p_id'],OWNER] if '%s' in sql else None)
                except Exception as exc:assert exc.pgcode=='42501'
                else:raise AssertionError('Browser accessed private analysis')
        finally:conn.connection.close()
    fake=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
    with patch.object(auth,'get_supabase_client',return_value=fake),patch.object(analysis,'get_supabase_client',return_value=service):
        client=TestClient(app);headers={'Authorization':'Bearer fixture'}
        assert client.get('/api/buyers/analysis/config').status_code==401
        created=client.post('/api/buyers/analysis/start',json={'request_id':str(uuid4()),'kind':'score','buyer_id':buyer()},headers=headers)
        assert created.status_code==200,created.text
        assert created.headers['cache-control']=='no-store'
        assert created.json()['processed']==0
        reference=created.json()['id']
        assert client.post(f'/api/buyers/analysis/{reference}/run',headers=headers).json()['applied']==1
        assert client.post('/api/buyers/score',json={},headers=headers).status_code==409
    service.connection.close()
    return {'real_sql':True,'provider':'synthetic only','full_history':1003,'concurrent_attempts':8,'provider_calls_per_request':1,'bounded_step':20,'stale_input_preserved':True,'paid_unknown_held':True,'private_receipts':True}

if __name__=='__main__':
    db=Database()
    try:print(json.dumps(verify(db),sort_keys=True))
    finally:db.connection.close()
