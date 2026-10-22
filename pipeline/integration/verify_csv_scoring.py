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
def counts(scored,held=0,remaining=0,in_flight=0):
    return {'scored':scored,'held':held,'remaining':remaining,'in_flight':in_flight}

OPTIONS={'score_on_import':True,'engine':'ai','list_name':'Synthetic connected CSV','filename':'synthetic.csv'}


def verify(db):
    service=Database(); service.query('SET ROLE service_role')
    api=TestClient(app)
    auth_client=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)

    def save(address, count=1):
        rows=[{'property_address':f'{address} {n} St','city':'Dallas','state':'TX','status':'new'} for n in range(count)]
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
        assert finished['state']=='completed' and finished['result']==counts(1)
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
            assert result['state']=='review' and result['result']==counts(0,1),(variant,result)
            assert db.query('SELECT score_motivation FROM leads WHERE id=%s',[key])[0]['score_motivation'] is None

        # Changes after claim must be retained; unchanged members may still be scored once.
        stale=save('csv-stale',2); stale_claim=claim(stale); stale_scores=scores(stale_claim)
        changed=stale_claim['snapshots'][0]['id']
        db.query("UPDATE leads SET dnc=true,status='under_contract',contact_attempts=7,seller_notes='human verified' WHERE id=%s",[changed])
        result=finish(stale,stale_claim,stale_scores)
        assert result['state']=='review' and result['result']==counts(1,1)
        retained=db.query('SELECT dnc,status,contact_attempts,seller_notes,score_motivation FROM leads WHERE id=%s',[changed])[0]
        assert retained=={'dnc':True,'status':'under_contract','contact_attempts':7,'seller_notes':'human verified','score_motivation':None}
        completed=save('csv-completed-task'); completed_claim=claim(completed)
        db.query("UPDATE tasks SET status='completed',completed_at=now() WHERE lead_id=%s",[completed_claim['snapshots'][0]['id']])
        assert finish(completed,completed_claim,scores(completed_claim))['result']==counts(0,1)

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
                if phase!='import_csv_leads': assert first.json()['scored'] is None,first.text
                assert second.status_code==200 and second.json()['replayed'],second.text
                expected_attempts=0 if phase=='claim_csv_import_scoring' else 1
                assert model.call_count-before==expected_attempts,(phase,model.call_count-before)
                assert second.json()['scoring_state']==('submitting' if phase=='claim_csv_import_scoring' else 'completed'),second.text

        # Large imports checkpoint every paid batch. GET is read-only and POST
        # is an explicit continuation; a process restart needs no in-memory state.
        with patch.object(auth,'get_supabase_client',lambda:auth_client),patch.object(csv_import,'get_supabase_client',lambda:service),patch('web.api._score_imported_leads_with_claude',model):
            model.side_effect=normal_model
            large=save('csv-large-complete',60)
            url='/api/ai/imports/'+large['id']+'/scoring'
            headers={'Authorization':'Bearer synthetic'}
            before=model.call_count
            initial=api.get(url,headers=headers)
            assert initial.status_code==200 and initial.json()['scoring_remaining']==60,initial.text
            assert model.call_count==before
            first=api.post(url,headers=headers)
            assert first.status_code==200 and first.json()['scored']==25 and first.json()['scoring_remaining']==35,first.text
            # Reconciliation of the original data request must not advance a new
            # paid batch after its first known completion. Only continuation may.
            replay_body={'request_id':large['id'],'engine':'ai','rows':large['payload'],
                'list_name':OPTIONS['list_name'],'filename':OPTIONS['filename']}
            replay=api.post('/api/ai/import-master-list',headers=headers,json=replay_body)
            assert replay.status_code==200 and replay.json()['replayed'] and replay.json()['scored']==25,replay.text
            assert model.call_count==before+1
            restarted=TestClient(app).get(url,headers=headers)
            assert restarted.json()['scored']==25 and restarted.json()['scoring_remaining']==35
            second=api.post(url,headers=headers); third=api.post(url,headers=headers)
            assert second.json()['scored']==50 and second.json()['scoring_remaining']==10,second.text
            assert third.json()['scored']==60 and third.json()['scoring_state']=='completed',third.text
            attempts=model.call_args_list[before:]
            assert [len(a.args[0]) for a in attempts]==[25,25,10]
            ids=[r['lead_id'] for a in attempts for r in a.args[0]]
            assert len(ids)==len(set(ids))==60
            assert api.post(url,headers=headers).json()['scored']==60 and model.call_count==before+3
            batch=db.query("SELECT id,claim_id,scores,response FROM private.csv_import_scoring_batches WHERE import_id=%s ORDER BY batch_index",[large['id']])[0]
            historical=service.rpc('finish_csv_import_scoring',{'p_id':large['id'],'p_operator':OWNER,'p_claim':batch['claim_id'],'p_scores':batch['scores']}).execute().data
            assert historical==batch['response'] and historical['result']==counts(25,remaining=35)
            assert api.get(url,headers=headers).json()['scored']==60
            for statement in ['UPDATE private.csv_import_scoring_batches SET result=result WHERE id=%s','DELETE FROM private.csv_import_scoring_batches WHERE id=%s']:
                try:db.query(statement,[batch['id']])
                except Exception as exc:assert getattr(exc,'pgcode',None)=='P0001'
                else:raise AssertionError('Completed batch evidence changed')

            # Known completed work survives an unknown second paid batch.
            partial=save('csv-large-unknown',60); url='/api/ai/imports/'+partial['id']+'/scoring'
            assert api.post(url,headers=headers).json()['scored']==25
            first_batch=db.query("SELECT to_jsonb(b) evidence FROM private.csv_import_scoring_batches b WHERE import_id=%s AND batch_index=0",[partial['id']])
            before=model.call_count; model.side_effect=TimeoutError('Unknown second batch')
            unknown=api.post(url,headers=headers)
            assert unknown.status_code==200 and unknown.json()['scoring_state']=='review',unknown.text
            assert unknown.json()['scored']==25 and unknown.json()['scoring_held']==25 and unknown.json()['scoring_remaining']==10
            assert api.post(url,headers=headers).json()['scoring_state']=='review'
            assert model.call_count==before+1
            assert db.query("SELECT to_jsonb(b) evidence FROM private.csv_import_scoring_batches b WHERE import_id=%s AND batch_index=0",[partial['id']])==first_batch

            # A known result with a lost acknowledgment still checkpoints only its
            # own batch. Refresh sees 50; the next explicit click handles the final 10.
            model.side_effect=normal_model
            lost_large=save('csv-large-lost-finish',60); url='/api/ai/imports/'+lost_large['id']+'/scoring'
            before=model.call_count
            assert api.post(url,headers=headers).json()['scored']==25
            lose={'done':False}
            def batch_rpc(name,params):
                operation=service.rpc(name,params)
                def execute():
                    result=operation.execute()
                    if name=='finish_csv_import_scoring' and not lose['done']:
                        lose['done']=True;raise TimeoutError('Lost second batch result acknowledgment')
                    return result
                return SimpleNamespace(execute=execute)
            with patch.object(csv_import,'get_supabase_client',lambda:SimpleNamespace(rpc=batch_rpc)):
                uncertain=api.post(url,headers=headers)
            assert uncertain.json()['scoring_state']=='unconfirmed',uncertain.text
            refreshed=api.get(url,headers=headers)
            assert refreshed.json()['scored']==50 and refreshed.json()['scoring_remaining']==10
            assert api.post(url,headers=headers).json()['scored']==60
            attempts=model.call_args_list[before:]
            ids=[r['lead_id'] for a in attempts for r in a.args[0]]
            assert [len(a.args[0]) for a in attempts]==[25,25,10] and len(set(ids))==60

            # Worked records before claim are held without paid dispatch. Other
            # known-unsubmitted batches remain available for explicit continuation.
            preworked=save('csv-large-preworked',26); url='/api/ai/imports/'+preworked['id']+'/scoring'
            for item in preworked['result']['rows'][:25]:db.query('UPDATE leads SET dnc=true WHERE id=%s',[item['lead_id']])
            before=model.call_count
            held=api.post(url,headers=headers)
            assert held.status_code==200 and held.json()['scored']==0 and held.json()['scoring_held']==25 and held.json()['scoring_remaining']==1,held.text
            assert model.call_count==before
            end=api.post(url,headers=headers)
            assert end.json()['scored']==1 and end.json()['scoring_state']=='review' and model.call_count==before+1,end.text

        # Another approved actor cannot inspect or continue this private import.
        foreign_actor=str(uuid4())
        db.query('INSERT INTO auth.users VALUES(%s)',[foreign_actor])
        db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'foreign-csv@example.test','user','approved')",[foreign_actor])
        foreign_auth=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=foreign_actor))),table=db.table)
        before=model.call_count
        with patch.object(auth,'get_supabase_client',lambda:foreign_auth),patch.object(csv_import,'get_supabase_client',lambda:service),patch('web.api._score_imported_leads_with_claude',model):
            assert api.get('/api/ai/imports/'+large['id']+'/scoring',headers={'Authorization':'Bearer synthetic'}).status_code==404
            assert api.post('/api/ai/imports/'+large['id']+'/scoring',headers={'Authorization':'Bearer synthetic'}).status_code==404
            assert model.call_count==before

        # Eight actual sessions contend for the same claim row: one gets dispatch authority.
        race=save('csv-claim-race',26); clients=[Database() for _ in range(8)]; pool=ThreadPoolExecutor(max_workers=8)
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
            assert all(x==outcomes[0] for x in outcomes) and outcomes[0]['result']==counts(25,remaining=1)
            final_claim=claim(race); assert len(final_claim['snapshots'])==1
            assert finish(race,final_claim,scores(final_claim))['result']==counts(26)
        finally:
            if locked:db.query('ROLLBACK')
            pool.shutdown(wait=True)
            for c in clients:c.connection.close()
        print(json.dumps({'csv_connected_api_scoring':'passed','durable_dispatch_claim':'passed','exact_terminal_replay':'passed',
            'unknown_outcome':'review_no_retry','new_reference_does_not_repeat_ai':True,'invalid_result_variants':len(variants),
            'stale_snapshot':'held','completed_task':'held','connected_api':'real SQL; Auth/model stubbed',
            'same_reference_model_attempts':1,'timeout_model_attempts':1,'legacy_stable_reference':True,
            'data_request_replay_advances_batches':False,'multi_batch_rows':60,'multi_batch_sizes':[25,25,10],'partial_unknown_retained_scored':25,'multi_batch_lost_finish':'resumed_without_repeat',
            'foreign_actor_progress_and_continue':'refused','preworked_batch_model_attempts':0,'terminal_batch_evidence':'immutable','read_only_progress':'no model calls','lost_sql_acknowledgment_phases':3,'lost_claim_model_attempts':0,'concurrent_claim_sessions':8,'dispatch_winners':1,'concurrent_finish_replays':8,'provider_calls':0}),flush=True)
    finally:
        service.connection.close()


if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
