"""Real SQL/API edit/delete receipts; synthetic records, no provider access."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web.api import buyer_mutations as changes
from web import auth
from web.app import app
OWNER='00000000-0000-4000-8000-000000000777'


def verify(db):
    service=Database();service.query('SET ROLE service_role')
    fake=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
    client=TestClient(app);headers={'Authorization':'Bearer fixture'}
    counter=8500
    def recipient():
        nonlocal counter
        while True:
            counter+=1;phone=f'214555{counter}'
            if not db.query('SELECT id FROM buyers WHERE private.buyer_phone(phone)=private.buyer_phone(%s)',[phone]):return phone
    def buyer():
        bid=str(uuid4());db.query("INSERT INTO buyers(id,first_name,last_name,phone,email,sms_opt_in,email_opt_in,tags) VALUES(%s,'Synthetic','Mutation',%s,%s,true,true,ARRAY['manual'])",[bid,recipient(),'mutation-'+bid+'@example.test']);return get(bid)
    def get(bid):
        rows=db.query('SELECT to_jsonb(b) value FROM buyers b WHERE id=%s',[bid]);return rows[0]['value'] if rows else None
    def body(row,kind='update',**updates):
        return {'request_id':str(uuid4()),'buyer_id':row['id'],'kind':kind,'expected':row,
                'updates':changes.BuyerEdit(**{k:row[k] for k in changes.BuyerEdit.model_fields if row.get(k) is not None},**updates).model_dump(mode='json') if kind=='update' else None}
    def send(value):return client.post('/api/buyers/mutations',json=value,headers=headers)
    def read(value):return client.get('/api/buyers/mutations/'+value['request_id'],headers=headers)
    def stop(value):return client.post('/api/buyers/mutations/'+value['request_id']+'/cancel',headers=headers)
    with patch.object(auth,'get_supabase_client',return_value=fake),patch.object(changes,'get_supabase_client',return_value=service):
        row=buyer();value=body(row);value['updates']['notes']='Confirmed edit'
        assert client.post('/api/buyers/mutations',json=value).status_code==401
        wrong={**value,'updates':{**value['updates'],'sms_opt_in':True}};assert send(wrong).status_code==422
        first=send(value);assert first.status_code==200,first.text
        assert first.json()['state']=='updated' and first.headers['cache-control']=='no-store',first.text
        saved=first.json()['buyer'];assert saved['sms_opt_in'] and saved['email_opt_in'] and saved['tags']==['manual']
        db.query("UPDATE buyers SET notes='Later edit' WHERE id=%s",[row['id']])
        assert send(value).json()['buyer']==saved and get(row['id'])['notes']=='Later edit'
        altered={**value,'updates':{**value['updates'],'notes':'Altered original'}};assert send(altered).status_code==409
        stale=body(row);assert send(stale).json()['state']=='stale' and get(row['id'])['notes']=='Later edit'
        contact=body(get(row['id']));contact['updates'].update(phone=recipient(),email='after-'+str(uuid4())+'@example.test')
        assert send(contact).json()['state']=='updated'
        after=get(row['id']);assert not after['sms_opt_in'] and not after['email_opt_in'] and after['tags']==['manual']
        # Exact phone/email formatting changes preserve existing consent, never infer new consent.
        row=buyer();value=body(row);value['updates'].update(phone=f"({row['phone'][:3]}) {row['phone'][3:6]}-{row['phone'][6:]}",email=row['email'].upper())
        # First buyer was moved to another recipient, so the identity remains distinct.
        assert send(value).json()['state']=='updated';assert get(row['id'])['sms_opt_in']
        # Deletion and receipt are one transaction; history cascades, evidence remains.
        row=buyer();value=body(row,'delete')
        db.query("INSERT INTO buyer_transactions(id,buyer_id,property_address) SELECT gen_random_uuid(),%s,'Synthetic' FROM generate_series(1,1003)",[row['id']])
        deleted=send(value);assert deleted.status_code==200,deleted.text
        assert deleted.json()['state']=='deleted' and deleted.json()['transaction_count']==1003
        assert not get(row['id']) and not db.query('SELECT id FROM buyer_transactions WHERE buyer_id=%s',[row['id']])
        assert send(value).json()==deleted.json() and stop(value).json()['state']=='deleted'
        missing=body(row,'delete');assert send(missing).json()['state']=='missing'
        # A late original mutation cannot escape a durable cancellation.
        row=buyer();value=body(row,'delete');assert stop(value).json()['state']=='canceled'
        assert send(value).json()['state']=='canceled' and get(row['id'])
        # Receipt insert failure rolls a deletion and child cascades back.
        row=buyer();value=body(row,'delete')
        db.query("CREATE FUNCTION public.test_buyer_mutation_rollback() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic receipt failure'; END $$")
        db.query('CREATE TRIGGER test_buyer_mutation_rollback BEFORE INSERT ON private.buyer_mutation_receipts FOR EACH ROW EXECUTE FUNCTION public.test_buyer_mutation_rollback()')
        assert send(value).status_code==503 and get(row['id'])
        db.query('DROP TRIGGER test_buyer_mutation_rollback ON private.buyer_mutation_receipts');db.query('DROP FUNCTION public.test_buyer_mutation_rollback()')
        # Eight independent sessions share one committed deletion receipt.
        def worker(_):
            conn=Database();conn.query('SET ROLE service_role')
            try:return conn.rpc('mutate_buyer',{'p_id':value['request_id'],'p_operator':OWNER,'p_kind':'delete','p_buyer':row['id'],'p_expected':row,'p_patch':{}}).execute().data
            finally:conn.connection.close()
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(worker,range(8)))
        assert all(r['state']=='deleted' for r in results)
        assert db.query('SELECT count(*) n FROM private.buyer_mutation_receipts WHERE id=%s',[value['request_id']])[0]['n']==1
        # Lost response after commit recovers a retained result without a second change.
        row=buyer();value=body(row,'delete');real=changes.execute
        def lose(name,params):
            result=real(name,params)
            if name=='mutate_buyer':raise TimeoutError('Synthetic response loss')
            return result
        with patch.object(changes,'execute',side_effect=lose):
            try:send(value)
            except TimeoutError:pass
            else:raise AssertionError('Response loss was not injected')
        assert read(value).json()['state']=='deleted' and send(value).json()['state']=='deleted'
        assert not get(row['id'])
        foreign=str(uuid4());db.query('INSERT INTO auth.users(id) VALUES(%s)',[foreign])
        db.query("INSERT INTO profiles(id,email,status,role) VALUES(%s,%s,'approved','user')",[foreign,foreign+'@example.test'])
        try:service.rpc('buyer_mutation_receipt',{'p_id':value['request_id'],'p_operator':foreign}).execute()
        except Exception as exc:assert exc.pgcode=='42501'
        else:raise AssertionError('Foreign operator read another receipt')
        own=str(uuid4());service.rpc('cancel_buyer_mutation',{'p_id':own,'p_operator':foreign}).execute()
        db.query("UPDATE profiles SET status='suspended' WHERE id=%s",[foreign])
        try:service.rpc('buyer_mutation_receipt',{'p_id':own,'p_operator':foreign}).execute()
        except Exception as exc:assert exc.pgcode=='42501'
        else:raise AssertionError('Revoked operator read a receipt')
        try:db.query('DELETE FROM private.buyer_mutation_receipts WHERE id=%s',[value['request_id']])
        except Exception as exc:assert 'immutable' in str(exc).lower()
        else:raise AssertionError('Receipt deleted')
        for role in ['anon','authenticated']:
            conn=Database();conn.query('SET ROLE '+role)
            try:
                try:conn.rpc('buyer_mutation_receipt',{'p_id':value['request_id'],'p_operator':OWNER}).execute()
                except Exception as exc:assert exc.pgcode=='42501'
                else:raise AssertionError('Browser role read private receipt')
            finally:conn.connection.close()
    service.connection.close()
    return {'buyer_mutations':'passed','independent_sessions':8,'deleted_history_rows':1003,'ledger_rollback':True,'stale_record_preserved':True,'contact_change_revokes_consent':True,'lost_response':'retained receipt','provider_calls':0}

if __name__=='__main__':
    db=Database()
    try:print(json.dumps(verify(db),sort_keys=True))
    finally:db.connection.close()
