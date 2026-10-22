"""Connected CSV API, one-way AI claims and stale-result checks on real SQL."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web import auth
from web.api import csv_import
from web.app import app

OWNER='00000000-0000-4000-8000-000000000777'
OPTIONS={'score_on_import':True,'engine':'ai','list_name':'Synthetic connected CSV','filename':'synthetic.csv'}


def verify(db):
    service=Database(); service.query('SET ROLE service_role')
    api=TestClient(app)
    auth_client=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)

    def save(address, count=1):
        rows=[{'property_address':f'{address} {n} St','city':'Dallas','state':'TX'} for n in range(count)]
        receipt=service.rpc('import_csv_leads',{'p_id':str(uuid4()),'p_operator':OWNER,'p_rows':rows,'p_options':OPTIONS}).execute().data['receipt']
        return receipt

    def claim(receipt, token=None, connection=service):
        return connection.rpc('claim_csv_import_scoring',{'p_id':receipt['id'],'p_operator':OWNER,'p_claim':token or str(uuid4())}).execute().data

    def scores(value):
        return {row['id']:{**{k:3 for k in ['score_motivation','score_timeline','score_equity','score_condition','score_flexibility']},
            'status':'qualified_hot','precision_tier':1,'ai_qualification_summary':'Synthetic verified input summary'} for row in value['snapshots']}

    def finish(receipt, claimed, payload, connection=service):
        return connection.rpc('finish_csv_import_scoring',{'p_id':receipt['id'],'p_operator':OWNER,'p_claim':claimed['claim_id'],'p_scores':payload}).execute().data

    try:
        receipt=save('csv-claimed'); claimed=claim(receipt)
        assert claimed['claimed'] and claimed['state']=='submitting'
        assert not claim(receipt)['claimed']  # even an identical claim token never grants another dispatch
        assert not claim(receipt,claimed['claim_id'])['claimed']
        payload=scores(claimed); finished=finish(receipt,claimed,payload)
        assert finished['state']=='completed' and finished['result']=={'scored':1,'held':0}
        assert finish(receipt,claimed,payload)==finished
        assert claim(receipt)['result']['scored']==1 and not claim(receipt)['claimed']
        try:
            finish(receipt,claimed,{})
        except Exception as exc:
            assert getattr(exc,'pgcode',None)=='22023'
        else:
            raise AssertionError('Changed terminal result accepted')

        # A paid attempt with unknown outcome is permanently held, including a new import reference.
        unknown=save('csv-unknown'); unknown_claim=claim(unknown)
        assert finish(unknown,unknown_claim,None)['state']=='review'
        assert not claim(unknown)['claimed']
        repeated=service.rpc('import_csv_leads',{'p_id':str(uuid4()),'p_operator':OWNER,'p_rows':unknown['payload'],'p_options':OPTIONS}).execute().data['receipt']
        assert repeated['result']['scoring_eligible']==0 and not claim(repeated)['claimed']

        # Invalid / missing / foreign IDs and scores hold the entire attempt before writes.
        variants=['foreign','missing','boolean','range','tier','field']
        for variant in variants:
            invalid=save('csv-invalid-'+variant); reservation=claim(invalid); bad=scores(reservation)
            key=next(iter(bad))
            if variant=='foreign': bad[str(uuid4())]=bad.pop(key)
            elif variant=='missing': bad={}
            elif variant=='boolean': bad[key]['score_motivation']=True
            elif variant=='range': bad[key]['score_equity']=4
            elif variant=='tier': bad[key]['status']='under_contract'
            else: bad[key]['assigned_to']=OWNER
            result=finish(invalid,reservation,bad)
            assert result['state']=='review' and result['result']=={'scored':0,'held':1},(variant,result)
            assert db.query('SELECT score_motivation FROM leads WHERE id=%s',[key])[0]['score_motivation'] is None

        # Changes after claim must be retained; unchanged members may still be scored once.
        stale=save('csv-stale',2); stale_claim=claim(stale); stale_scores=scores(stale_claim)
        changed=stale_claim['snapshots'][0]['id']
        db.query("UPDATE leads SET dnc=true,status='under_contract',contact_attempts=7,seller_notes='human verified' WHERE id=%s",[changed])
        result=finish(stale,stale_claim,stale_scores)
        assert result['state']=='review' and result['result']=={'scored':1,'held':1}
        retained=db.query('SELECT dnc,status,contact_attempts,seller_notes,score_motivation FROM leads WHERE id=%s',[changed])[0]
        assert retained=={'dnc':True,'status':'under_contract','contact_attempts':7,'seller_notes':'human verified','score_motivation':None}
        completed=save('csv-completed-task'); completed_claim=claim(completed)
        db.query("UPDATE tasks SET status='completed',completed_at=now() WHERE lead_id=%s",[completed_claim['snapshots'][0]['id']])
        assert finish(completed,completed_claim,scores(completed_claim))['result']=={'scored':0,'held':1}

        # Real verified-actor API → import/claim/result SQL; the model boundary alone is mocked.
        model=Mock(side_effect=lambda leads,**kwargs:{lead['lead_id']:{**{k:3 for k in ['score_motivation','score_timeline','score_equity','score_condition','score_flexibility']},
            'status':'qualified_hot','precision_tier':1,'ai_qualification_summary':'Synthetic API scoring'} for lead in leads})
        normal_model=model.side_effect
        with patch.object(auth,'get_supabase_client',lambda:auth_client),patch.object(csv_import,'get_supabase_client',lambda:service),patch('web.api._score_imported_leads_with_claude',model):
            db.query("INSERT INTO leads(property_address,city,state,source,assigned_to) VALUES('123 API Atomic Street','Dallas','TX','old_list',%s)",[OWNER])
            body={'request_id':str(uuid4()),'engine':'ai','rows':[{'property_address':'123 API Atomic Street','city':'Dallas','sources':['tax'],'stack_count':2},
                {'property_address':'123 API Atomic St.','city':'Dallas','sources':['vacant'],'owner_phone_1':'(214) 555-0100'},
                {'property_address':'500 API Atomic Ave','city':'Dallas','source':'probate'}]}
            response=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=body)
            assert response.status_code==200,response.text
            result=response.json()
            assert result['consolidated_rows']==2 and result['imported']==1 and result['updated']==1 and result['scored']==2 and result['scoring_state']=='completed',result
            assert api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=body).json()['replayed']
            assert model.call_count==1 and model.call_args.kwargs=={'single_attempt':True}
            saved=db.query('SELECT id,source,owner_phone_1,assigned_to,score_motivation FROM leads WHERE property_address=%s',['123 API Atomic Street'])[0]
            assert saved['source']=='old_list | tax | vacant' and saved['owner_phone_1']=='2145550100' and saved['assigned_to']==OWNER and saved['score_motivation']==3
            assert db.query('SELECT count(*) n FROM tasks WHERE lead_id=%s',[saved['id']])[0]['n']==0
            assert db.query("SELECT count(*) n FROM tasks t JOIN leads l ON t.lead_id=l.id WHERE l.property_address='500 API Atomic Ave'")[0]['n']==1
            # Caller without UUID receives deterministic same-normalized-payload replay.
            legacy={'score_with_claude':False,'rows':[{'property_address':'124 Legacy Stable CSV St','city':'Dallas'}]}
            first=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=legacy)
            second=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=legacy)
            assert first.status_code==second.status_code==200 and second.json()['replayed']
            assert first.json()['request_id']==second.json()['request_id']
            # Timeout persists review; saved data remains a confirmed success, never dispatched again.
            model.side_effect=TimeoutError('synthetic provider response lost')
            timeout_body={'request_id':str(uuid4()),'engine':'ai','rows':[{'property_address':'125 API Unknown CSV St','city':'Dallas'}]}
            response=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=timeout_body)
            assert response.status_code==200 and response.json()['imported']==1 and response.json()['scoring_state']=='review' and response.json()['warning']
            assert api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=timeout_body).json()['scoring_state']=='review'
            assert model.call_count==2
            invalid_body={'rows':[{'property_address':'126 Negative CSV St','city':'Dallas','asking_price':'-$200'}]}
            assert api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=invalid_body).status_code==422
            assert not db.query("SELECT id FROM leads WHERE property_address='126 Negative CSV St'")

            # Simulate committed SQL followed by a lost acknowledgment at every RPC boundary.
            # The API retries only data/receipt reconciliation; never another paid dispatch.
            model.side_effect=normal_model
            for phase in ['import_csv_leads','claim_csv_import_scoring','finish_csv_import_scoring']:
                lost={'done':False}
                def unreliable_rpc(name,params):
                    operation=service.rpc(name,params)
                    def execute():
                        result=operation.execute()
                        if name==phase and not lost['done']:
                            lost['done']=True
                            raise TimeoutError('Synthetic SQL acknowledgment lost after commit')
                        return result
                    return SimpleNamespace(execute=execute)
                proxy=SimpleNamespace(rpc=unreliable_rpc)
                payload={'request_id':str(uuid4()),'engine':'ai','rows':[{'property_address':'127 Lost SQL '+phase+' St','city':'Dallas'}]}
                before=model.call_count
                with patch.object(csv_import,'get_supabase_client',lambda:proxy):
                    first=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=payload)
                    second=api.post('/api/ai/import-master-list',headers={'Authorization':'Bearer synthetic'},json=payload)
                assert first.status_code==(503 if phase=='import_csv_leads' else 200),first.text
                assert second.status_code==200 and second.json()['replayed'],second.text
                expected_attempts=0 if phase=='claim_csv_import_scoring' else 1
                assert model.call_count-before==expected_attempts,(phase,model.call_count-before)
                assert second.json()['scoring_state']==('submitting' if phase=='claim_csv_import_scoring' else 'completed'),second.text

        # Eight actual sessions contend for the same claim row: one gets dispatch authority.
        race=save('csv-claim-race'); clients=[Database() for _ in range(8)]; pool=ThreadPoolExecutor(max_workers=8)
        tag='csv_claim_'+uuid4().hex; locked=False
        try:
            for i,c in enumerate(clients):
                c.query('SET ROLE service_role');c.query("SELECT set_config('application_name',%s,false)",[tag+str(i)])
            db.query('BEGIN'); db.query('SELECT import_id FROM private.csv_import_scoring WHERE import_id=%s FOR UPDATE',[race['id']]); locked=True
            futures=[pool.submit(claim,race,connection=c) for c in clients]
            deadline=time.monotonic()+10; waiters=[]
            while time.monotonic()<deadline:
                waiters=db.query("SELECT pid FROM pg_stat_activity WHERE application_name LIKE %s AND wait_event_type='Lock'",[tag+'%'])
                if len(waiters)==8:break
                time.sleep(0.05)
            assert len({r['pid'] for r in waiters})==8,waiters
            db.query('COMMIT');locked=False
            claims=[f.result(timeout=15) for f in futures]
            winners=[c for c in claims if c['claimed']]; assert len(winners)==1,claims
            winner=winners[0]; values=scores(winner)
            finishes=[pool.submit(finish,race,winner,values,c) for c in clients]
            outcomes=[f.result(timeout=15) for f in finishes]
            assert all(x==outcomes[0] for x in outcomes) and outcomes[0]['result']=={'scored':1,'held':0}
        finally:
            if locked:db.query('ROLLBACK')
            pool.shutdown(wait=True)
            for c in clients:c.connection.close()
        print(json.dumps({'csv_connected_api_scoring':'passed','durable_dispatch_claim':'passed','exact_terminal_replay':'passed',
            'unknown_outcome':'review_no_retry','new_reference_does_not_repeat_ai':True,'invalid_result_variants':len(variants),
            'stale_snapshot':'held','completed_task':'held','connected_api':'real SQL; Auth/model stubbed',
            'same_reference_model_attempts':1,'timeout_model_attempts':1,'legacy_stable_reference':True,
            'lost_sql_acknowledgment_phases':3,'lost_claim_model_attempts':0,'concurrent_claim_sessions':8,'dispatch_winners':1,'concurrent_finish_replays':8,'provider_calls':0}),flush=True)
    finally:
        service.connection.close()


if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
