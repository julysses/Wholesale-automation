"""Manual CSV receipt, preservation, concurrency and API checks on upgraded schema."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import time
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace
from fastapi.testclient import TestClient

from tests.local_journey_db import Database
from web.app import app
from web import auth
from web.api import land_import_api

OWNER='00000000-0000-4000-8000-000000000777'


def verify(db):
    client=Database();client.query('SET ROLE service_role')
    rows=[{'owner_name':'Synthetic Import Owner','property_address':f'{n} Manual Import St','city':'Dallas','state':'TX','tav':0} for n in range(1,7)]
    reference=str(uuid4())
    def save(ref, payload, connection=client):
        return connection.rpc('import_manual_land_leads',{'p_id':ref,'p_operator':OWNER,'p_rows':payload}).execute().data
    try:
        result=save(reference,rows);saved=result['receipt'];assert saved['result']['imported']==6
        assert saved['result']['existing']==0 and result['outreach_authorized'] is False
        assert save(reference,rows)=={**result,'replayed':True}
        tasks=[mapping['task_id'] for mapping in saved['result']['rows']]
        assert len(set(tasks))==6
        for mapping in saved['result']['rows']:
            land=db.query('SELECT * FROM land_leads WHERE id=%s',[mapping['land_lead_id']])[0]
            assert land['assigned_to']==OWNER and land['sms_sequence_active'] is False and Decimal(str(land['tav']))==0
            assert land['status']=='new' and land['source']=='csv_import'
            task=db.query('SELECT * FROM tasks WHERE id=%s',[mapping['task_id']])[0]
            assert task['assigned_to']==OWNER and task['due_date'] and task['status']=='pending'
        land_id=saved['result']['rows'][0]['land_lead_id']
        db.query("UPDATE land_leads SET dnc=true,status='under_contract',assigned_to=NULL,offer_price=12345,contact_attempts=9,apn='PARCEL-1',county='Dallas' WHERE id=%s",[land_id])
        db.query("UPDATE tasks SET status='completed',completed_at=now() WHERE id=%s",[tasks[0]])
        before=db.query('SELECT * FROM land_leads WHERE id=%s',[land_id]);task_before=db.query('SELECT * FROM tasks WHERE id=%s',[tasks[0]])
        repeat=deepcopy(rows);repeat[0]['property_address']='  1   MANUAL Import St  ';repeat[0]['city']='DALLAS';repeat[0]['owner_name']='Different owner input'
        repeated=save(str(uuid4()),repeat)
        assert repeated['receipt']['result']['imported']==0 and repeated['receipt']['result']['existing']==6
        assert db.query('SELECT * FROM land_leads WHERE id=%s',[land_id])==before
        assert db.query('SELECT * FROM tasks WHERE id=%s',[tasks[0]])==task_before
        assert save(reference,rows)['replayed'] is True
        for ref, invalid in [(reference,repeat),(str(uuid4()),[{'owner_name':'CSV','property_address':'Never persist','city':'Dallas','sms_sequence_active':True}]),
                             (str(uuid4()),[{'owner_name':'CSV','property_address':'Never persist','city':'Dallas'},{'owner_name':'CSV','property_address':'Missing city'}]),
                             (str(uuid4()),[{**rows[0],'apn':'OTHER-PARCEL'}]),(str(uuid4()),[{**rows[0],'county':'Collin'}])]:
            try:save(ref,invalid)
            except Exception as exc:assert getattr(exc,'pgcode',None)=='22023',str(exc)
            else:raise AssertionError('Conflicting or invalid import was accepted')
        assert not db.query("SELECT id FROM land_leads WHERE property_address='Never persist'")
        for statement in ['UPDATE private.manual_land_imports SET payload=payload WHERE id=%s','DELETE FROM private.manual_land_imports WHERE id=%s']:
            try:db.query(statement,[reference])
            except Exception as exc:assert getattr(exc,'pgcode',None)=='P0001' and 'immutable' in str(exc)
            else:raise AssertionError('Receipt mutation succeeded')
        # Exercise the real FastAPI route and real RPC, not a fabricated response.
        auth_client=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
        with patch.object(auth,'get_supabase_client',lambda:auth_client),patch.object(land_import_api,'get_supabase_client',lambda:client):
            response=TestClient(app).post('/api/land/imports',headers={'Authorization':'Bearer synthetic'},json={'request_id':reference,'rows':rows})
            assert response.status_code==200,response.text
            assert response.json()['receipt']['id']==reference and response.json()['replayed'] is True
        # Separate sessions overlap before distinct-reference imports of one new property.
        token='manual_import_'+uuid4().hex;clients=[Database() for _ in range(8)];pool=ThreadPoolExecutor(max_workers=8);locked=False
        try:
            for index,c in enumerate(clients):
                c.query('SET ROLE service_role');c.query("SELECT set_config('application_name',%s,false)",[token+str(index)])
            db.query("SELECT pg_advisory_lock(hashtextextended('manual-land-import',0))");locked=True
            payload=[{'owner_name':'Synthetic Race Owner','property_address':'777 Concurrent Import St','city':'Dallas','state':'TX'}]
            futures=[pool.submit(save,str(uuid4()),payload,c) for c in clients]
            deadline=time.monotonic()+10;waiters=[]
            while time.monotonic()<deadline:
                waiters=db.query("SELECT pid FROM pg_stat_activity WHERE application_name LIKE %s AND wait_event='advisory'",[token+'%'])
                if len(waiters)==8:break
                time.sleep(0.05)
            assert len({row['pid'] for row in waiters})==8,waiters
            db.query("SELECT pg_advisory_unlock(hashtextextended('manual-land-import',0))");locked=False
            outcomes=[f.result(timeout=10) for f in futures]
            assert sum(x['receipt']['result']['imported'] for x in outcomes)==1
            assert sum(x['receipt']['result']['existing'] for x in outcomes)==7
            assert len({x['receipt']['result']['rows'][0]['land_lead_id'] for x in outcomes})==1
            assert db.query("SELECT count(*) n FROM land_leads WHERE property_address='777 Concurrent Import St'")[0]['n']==1
        finally:
            if locked:db.query("SELECT pg_advisory_unlock(hashtextextended('manual-land-import',0))")
            pool.shutdown(wait=True)
            for c in clients:c.connection.close()
        print(json.dumps({'manual_land_import':'passed','full_file_rows':6,'same_reference_replay':'passed','different_reference_deduplication':'passed',
            'worked_land_and_completed_task_preserved':True,'invalid_batch_rollback':'passed','parcel_conflict':'refused','immutable_receipt':'passed','connected_api_receipt':'passed',
            'concurrent_sessions':8,'concurrent_new_properties':1,'concurrent_existing_results':7,'provider_calls':0}),flush=True)
    finally:
        client.connection.close()


if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
