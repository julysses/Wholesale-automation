"""Real SQL/API buyer import: atomic persistence, acknowledgment recovery and no consent."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web import auth
from web.app import app
from web.api import buyers_api as api
from tools.buyer_csv_parser import parse_buyer_csv

OWNER='00000000-0000-4000-8000-000000000777'
HEADER='Grantee,Property Address,City,State,APN,Sale Date,Sale Price,Phone,Email\n'


def verify(db):
    service=Database();service.query('SET ROLE service_role')
    client=TestClient(app)
    auth_client=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
    content=HEADER+'Synthetic Import LLC,100 Synthetic St,Dallas,TX,SYN100,2026-10-01,100000,2145550111,synthetic@example.test\n'
    content+='Synthetic Import LLC,101 Synthetic St,Dallas,TX,,2026-10-02,110000,2145550111,synthetic@example.test\n'
    reference=str(uuid4())
    def submit(text=content,ref=reference,options=None):
        return client.post('/api/buyers/import',headers={'Authorization':'Bearer synthetic'},
            files={'file':('synthetic.csv',text.encode(),'text/csv')},data={**({'request_id':ref} if ref else {}),**(options or {})})
    try:
        with patch.object(auth,'get_supabase_client',return_value=auth_client),patch.object(api,'_get_supabase',return_value=service),patch.object(api,'_run_scoring',side_effect=AssertionError('Unexpected background scoring')):
            result=submit();assert result.status_code==200,result.text
            saved=result.json();assert saved['status']=='complete' and saved['buyers_created']==1 and saved['transactions_created']==2
            buyer=saved['buyer_ids'][0]
            row=db.query('SELECT active,sms_opt_in,email_opt_in FROM buyers WHERE id=%s',[buyer])[0]
            assert row=={'active':True,'sms_opt_in':False,'email_opt_in':False},row
            assert submit().json()=={**saved,'replayed':True}
            assert submit(content+'Synthetic Other LLC,102 Test St,Dallas,TX,SYN102,2026-10-03,100000,,\n').status_code==409
            assert db.query('SELECT count(*) n FROM buyers WHERE entity_name=%s',['Synthetic Other LLC'])[0]['n']==0

            # New reference: exact transactions are recognized, not inserted twice;
            # existing work/availability/consent/custom tags must not be overwritten.
            db.query("UPDATE buyers SET active=false,buys_land=true,buys_infill=true,land_buyer_type='builder',notes='retain',ibie_score=91,tags=ARRAY['manual'],sms_opt_in=false,email_opt_in=true WHERE id=%s",[buyer])
            before=db.query('SELECT * FROM buyers WHERE id=%s',[buyer])[0]
            repeated=submit(ref=str(uuid4()));assert repeated.status_code==200,repeated.text
            assert repeated.json()['transactions_existing']==2 and repeated.json()['transactions_created']==0
            assert db.query('SELECT * FROM buyers WHERE id=%s',[buyer])[0]==before

            db.query('UPDATE buyers SET phone=NULL,email=NULL,sms_opt_in=true,email_opt_in=true WHERE id=%s',[buyer])
            guarded=submit(ref=str(uuid4()));assert guarded.status_code==200,guarded.text
            assert db.query('SELECT phone,email,sms_opt_in,email_opt_in FROM buyers WHERE id=%s',[buyer])[0]=={
                'phone':None,'email':None,'sms_opt_in':True,'email_opt_in':True}

            # One valid group followed by a conflicting parcel event rolls back all
            # records/log/receipt changes, including the earlier newly created buyer.
            conflict=HEADER+'Synthetic Rollback LLC,103 New St,Dallas,TX,SYN103,2026-10-03,90000,,\n'
            conflict+='Synthetic Import LLC,100 Synthetic St,Dallas,TX,SYN100,2026-10-04,200000,,\n'
            bad_ref=str(uuid4());rejected=submit(conflict,bad_ref);assert rejected.status_code==409,rejected.text
            assert not db.query('SELECT id FROM buyers WHERE entity_name=%s',['Synthetic Rollback LLC'])
            assert not db.query('SELECT id FROM buyer_import_log WHERE id=%s',[bad_ref])
            assert not db.query('SELECT id FROM private.buyer_csv_imports WHERE id=%s',[bad_ref])

            # Commit then lose the transport response. Exact retry recovers the
            # original result without another buyer, purchase or background task.
            loss_ref=str(uuid4());lost=content.replace('Synthetic Import LLC','Synthetic Lost LLC').replace('2145550111','2145550112').replace('synthetic@example.test','lost@example.test')
            original=service.rpc
            def lose(name,params):
                call=original(name,params)
                def execute():
                    call.execute()
                    raise TimeoutError('Synthetic lost response after commit')
                return SimpleNamespace(execute=execute)
            with patch.object(service,'rpc',side_effect=lose):
                assert submit(lost,loss_ref).status_code==503
            recovered=submit(lost,loss_ref);assert recovered.status_code==200,recovered.text
            assert recovered.json()['replayed'] is True and recovered.json()['buyers_created']==1
            assert db.query('SELECT count(*) n FROM buyers WHERE entity_name=%s',['Synthetic Lost LLC'])[0]['n']==1
            assert db.query('SELECT count(*) n FROM buyer_transactions WHERE buyer_id=%s',[recovered.json()['buyer_ids'][0]])[0]['n']==2

            shared=lost.replace('Synthetic Lost LLC','Synthetic Different LLC')
            assert submit(shared,str(uuid4())).status_code==409
            assert not db.query('SELECT id FROM buyers WHERE entity_name=%s',['Synthetic Different LLC'])
            person=HEADER+'Synthetic Person,104 Personal St,Dallas,TX,,2026-10-01,100000,,\n'
            assert submit(person,str(uuid4())).status_code==200
            assert submit(person,str(uuid4())).status_code==409
            duplicate_line='Synthetic Duplicate LLC,105 Duplicate St,Dallas,TX,SYN105,2026-10-01,100000,,\n'
            duplicate=submit(HEADER+duplicate_line+duplicate_line,str(uuid4()))
            assert duplicate.status_code==200,duplicate.text
            assert duplicate.json()['transactions_created']==1 and duplicate.json()['transactions_existing']==1
            assert db.query('SELECT properties_owned FROM buyers WHERE id=%s',[duplicate.json()['buyer_ids'][0]])[0]['properties_owned']==1

            malformed=HEADER+',104 Missing Buyer St,Dallas,TX,SYN104,2026-10-01,100000,,\n'
            assert submit(malformed,str(uuid4())).status_code==422
            assert submit(ref=str(uuid4()),options={'min_price':'nan'}).status_code==422

            bulk=HEADER+''.join(f'Synthetic Bulk LLC,{n} Bulk St,Dallas,TX,BULK{n},2026-10-01,100000,,\n' for n in range(1003))
            bulk_result=submit(bulk,str(uuid4()));assert bulk_result.status_code==200,bulk_result.text
            assert bulk_result.json()['transactions_created']==1003
            assert db.query('SELECT count(*) n FROM buyer_transactions WHERE buyer_id=%s',[bulk_result.json()['buyer_ids'][0]])[0]['n']==1003
            oversized_rows=HEADER+''.join(f'Synthetic Too Large LLC,{n} Large St,Dallas,TX,LARGE{n},2026-10-01,100000,,\n' for n in range(5001))
            assert submit(oversized_rows,str(uuid4())).status_code==413
            assert not db.query('SELECT id FROM buyers WHERE entity_name=%s',['Synthetic Too Large LLC'])

            # Legacy clients without an explicit reference still get stable identity.
            first=submit(ref=None);second=submit(ref=None)
            assert first.status_code==second.status_code==200
            assert first.json()['import_id']==second.json()['import_id'] and second.json()['replayed']

            foreign=str(uuid4());db.query('INSERT INTO auth.users VALUES(%s)',[foreign])
            db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'foreign-buyer@example.test','user','approved')",[foreign])
            foreign_auth=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=foreign))),table=db.table)
            with patch.object(auth,'get_supabase_client',return_value=foreign_auth):
                assert submit().status_code==409

        # Actual competing database sessions import the same new entity under
        # distinct references. Exactly one buyer and its purchase history survive.
        concurrent=content.replace('Synthetic Import LLC','Synthetic Concurrent LLC').replace('2145550111','2145550113').replace('synthetic@example.test','concurrent@example.test')
        parsed=parse_buyer_csv(__import__('io').StringIO(concurrent),filename='synthetic.csv')
        options={'filename':'synthetic.csv','market':'','cash_only':False,'entities_only':False,'min_price':0.0,'max_price':0.0,
            'rows_total':2,'rows_skipped':0}
        sessions=[Database() for _ in range(4)]
        try:
            for connection in sessions:connection.query('SET ROLE service_role')
            barrier=Barrier(4)
            def attempt(connection):
                barrier.wait(timeout=10)
                return connection.rpc('import_buyer_csv',{'p_id':str(uuid4()),'p_operator':OWNER,
                    'p_fingerprint':'a'*64,'p_groups':parsed.groups,'p_options':options}).execute().data
            with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(attempt,sessions))
            assert sum(r['result']['buyers_created'] for r in results)==1
            assert sum(r['result']['transactions_created'] for r in results)==2
        finally:
            for connection in sessions:connection.connection.close()
        print(json.dumps({'buyer_import':'passed','atomic_rollback':'passed','lost_commit_ack':'recovered_without_duplicate',
            'source_contact_consent':'false','blank_consented_contact':'not_rebound','same_name_contactless_buyer':'review','duplicate_source_purchase':'not_score_inflated','existing_buyer_controls':'preserved','same_reference':'immutable',
            'foreign_operator':'refused','all_file_purchase_rows':1003,'oversized_rows':'rejected_before_write','concurrent_sessions':4,'created_buyers':1,'created_purchases':2,'provider_calls':0}),flush=True)
    finally:service.connection.close()


if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
