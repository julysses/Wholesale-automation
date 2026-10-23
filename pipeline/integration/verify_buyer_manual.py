"""Real SQL/API manual saves, retained cancellation and lost-response recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web import auth
from web.api import buyer_manual as manual
from web.app import app

OWNER = '00000000-0000-4000-8000-000000000777'


def verify(db):
    service = Database(); service.query('SET ROLE service_role')
    user = str(uuid4())
    db.query('INSERT INTO auth.users(id) VALUES(%s)', [user])
    db.query("INSERT INTO profiles(id,email,status,role) VALUES(%s,%s,'approved','user')", [user, user+'@example.test'])
    fake = SimpleNamespace(auth=SimpleNamespace(get_user=lambda token: SimpleNamespace(user=SimpleNamespace(id=OWNER if token == 'admin' else user))), table=db.table)
    client = TestClient(app); headers = {'Authorization': 'Bearer user'}
    def body(**fields):
        return {'request_id': str(uuid4()), 'buyer': {'first_name': 'Synthetic Manual', 'last_name': str(uuid4()),
                'phone': '', 'email': '', 'min_price': 0, 'max_price': 200000, **fields}}
    def create(value): return client.post('/api/buyers/manual', json=value, headers=headers)
    def receipt(value): return client.get('/api/buyers/manual/'+value['request_id'], headers=headers)
    def stop(value): return client.post('/api/buyers/manual/'+value['request_id']+'/cancel', headers=headers)
    try:
        with patch.object(auth, 'get_supabase_client', return_value=fake), patch.object(manual, 'get_supabase_client', return_value=service):
            original = body(phone='+12145550841', email='manual-fixture@example.test')
            assert client.post('/api/buyers/manual', json=original).status_code == 401
            assert create(body(sms_opt_in=True)).status_code == 422
            assert create(body(email_opt_in=True)).status_code == 422
            assert create(body(min_price=-1)).status_code == 422
            assert create(body(min_price=3, max_price=2)).status_code == 422
            saved = create(original)
            assert saved.status_code == 200, saved.text
            assert saved.headers['cache-control'] == 'no-store'
            value = saved.json(); assert value['saved'] and value['buyer_id'] == original['request_id']
            assert value['buyer']['sms_opt_in'] is False and value['buyer']['email_opt_in'] is False
            assert value['buyer']['min_price'] == 0
            # Exact retry recovers the historical creation; never overwrite later edits.
            db.query("UPDATE buyers SET notes='later operator edit',sms_opt_in=true WHERE id=%s", [original['request_id']])
            assert create(original).json()['buyer'] == value['buyer']
            assert db.query('SELECT notes,sms_opt_in FROM buyers WHERE id=%s', [original['request_id']])[0] == {'notes': 'later operator edit', 'sms_opt_in': True}
            changed = {**original, 'buyer': {**original['buyer'], 'company': 'changed request'}}
            assert create(changed).status_code == 409
            assert client.get('/api/buyers/manual/'+original['request_id'], headers={'Authorization':'Bearer admin'}).status_code == 403
            assert create(body(phone='(214) 555-0841')).status_code == 409
            assert create(body(email='MANUAL-FIXTURE@example.test')).status_code == 409
            assert stop(original).json()['state'] == 'saved'
            assert db.query('SELECT count(*) n FROM buyers WHERE id=%s', [original['request_id']])[0]['n'] == 1
            # Persisted cancellation serializes with a late original POST.
            canceled = body(); assert stop(canceled).json()['state'] == 'canceled'
            assert create(canceled).json()['state'] == 'canceled'
            assert not db.query('SELECT id FROM buyers WHERE id=%s', [canceled['request_id']])
            lost = body(); real = manual.execute
            def lose_result(name, params):
                result = real(name, params)
                if name == 'create_manual_buyer': raise RuntimeError('synthetic response loss after commit')
                return result
            with patch.object(manual, 'execute', side_effect=lose_result):
                try: create(lost)
                except RuntimeError: pass
                else: raise AssertionError('Injected response loss was not reached')
            assert receipt(lost).json()['saved'] and create(lost).json()['saved']
            # A ledger failure must roll back the buyer in the same transaction.
            db.query("CREATE FUNCTION public.test_manual_rollback() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic receipt failure'; END $$")
            db.query('CREATE TRIGGER test_manual_rollback BEFORE INSERT ON private.buyer_manual_receipts FOR EACH ROW EXECUTE FUNCTION public.test_manual_rollback()')
            rejected = body(); assert create(rejected).status_code == 503
            assert not db.query('SELECT id FROM buyers WHERE id=%s', [rejected['request_id']])
            db.query('DROP TRIGGER test_manual_rollback ON private.buyer_manual_receipts'); db.query('DROP FUNCTION public.test_manual_rollback()')
            assert create(rejected).json()['saved']
            # Same reference across independent DB sessions has one durable result.
            concurrent = body(); payload = manual.ManualBuyer(**concurrent['buyer']).model_dump(mode='json')
            def attempt(index):
                worker = Database(); worker.query('SET ROLE service_role')
                try:
                    if index == -1: return worker.rpc('cancel_manual_buyer', {'p_id':concurrent['request_id'],'p_operator':user}).execute().data
                    return worker.rpc('create_manual_buyer', {'p_id':concurrent['request_id'],'p_operator':user,'p_payload':payload}).execute().data
                finally: worker.connection.close()
            with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(attempt, range(8)))
            assert all(r['saved'] for r in results)
            assert db.query('SELECT count(*) n FROM buyers WHERE id=%s', [concurrent['request_id']])[0]['n'] == 1
            assert db.query('SELECT count(*) n FROM private.buyer_manual_receipts WHERE id=%s', [concurrent['request_id']])[0]['n'] == 1
            concurrent = body(); payload = manual.ManualBuyer(**concurrent['buyer']).model_dump(mode='json')
            with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(attempt, [-1,0,1,2,3,4,5,6]))
            state = receipt(concurrent).json()['state']
            assert all(r['state'] == state for r in results)
            assert db.query('SELECT count(*) n FROM buyers WHERE id=%s', [concurrent['request_id']])[0]['n'] == (1 if state == 'saved' else 0)
            # Retained receipts cannot recreate a buyer after deletion.
            db.query('DELETE FROM buyers WHERE id=%s', [original['request_id']])
            recovered = create(original).json()
            assert recovered['saved'] and recovered['current_exists'] is False and recovered['buyer'] == value['buyer']
            assert not db.query('SELECT id FROM buyers WHERE id=%s', [original['request_id']])
            db.query("UPDATE profiles SET status='pending' WHERE id=%s", [user])
            assert receipt(lost).status_code == 403
            try: service.rpc('manual_buyer_receipt', {'p_id':lost['request_id'],'p_operator':user}).execute()
            except Exception as exc: assert exc.pgcode == '42501'
            else: raise AssertionError('Revoked operator read a private receipt')
            db.query("UPDATE profiles SET status='approved' WHERE id=%s", [user])
            browser = Database(); browser.query('SET ROLE authenticated')
            try:
                for sql in ['SELECT * FROM private.buyer_manual_receipts',
                            "SELECT public.manual_buyer_receipt('"+lost['request_id']+"','"+user+"')"]:
                    try: browser.query(sql)
                    except Exception as exc: assert exc.pgcode == '42501'
                    else: raise AssertionError('Browser accessed server receipt authority')
            finally: browser.connection.close()
            try: db.query('UPDATE private.buyer_manual_receipts SET operator_id=%s WHERE id=%s', [OWNER,lost['request_id']])
            except Exception as exc: assert 'immutable' in str(exc).lower()
            else: raise AssertionError('Receipt changed')
            defaults = db.query("SELECT column_name,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='buyers' AND column_name IN ('email_opt_in','sms_opt_in')")
            assert len(defaults)==2 and all(row['column_default']=='false' for row in defaults)
            assert not db.query('SELECT * FROM net.test_requests')
            print(json.dumps({'manual_buyer':'passed','concurrent_creates':8,'lost_response':'recovered without duplicate',
                'cancellation':'durable; late save blocked or committed save recovered','deletion':'receipt retained; no resurrection',
                'consent':'new defaults false; existing records preserved','role_immutability_rollback':'passed','provider_calls':0}), flush=True)
    finally: service.connection.close()


if __name__ == '__main__':
    db = Database()
    try: verify(db)
    finally: db.connection.close()
