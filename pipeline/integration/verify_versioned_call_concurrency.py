"""Actual call/SMS overlap on the restored and upgraded disposable schema."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
from uuid import uuid4

from tests.local_journey_db import Database


def verify(db):
    owner = '00000000-0000-4000-8000-000000000777'
    lead = str(uuid4())
    db.query("INSERT INTO leads(id,property_address,city,status,dnc,ai_calling_paused) VALUES(%s,'Synthetic concurrent call','Dallas','new',false,false)", [lead])

    def overlap(phone, mixed):
        token = 'call_overlap_' + uuid4().hex
        count = 8
        refs = [str(uuid4()) for _ in range(count)]
        clients = [Database() for _ in refs]
        for index, client in enumerate(clients):
            client.query('SET ROLE service_role')
            client.query("SELECT set_config('application_name',%s,false)", [token + str(index)])
        db.query("SELECT pg_advisory_lock(hashtextextended('seller-outreach:'||%s,0))", [phone])
        locked = True
        pool = ThreadPoolExecutor(max_workers=count)
        try:
            def attempt(index):
                client, reference = clients[index], refs[index]
                if mixed and index % 2:
                    result = client.rpc('claim_twilio_sms', {'p_id':reference,'p_lead':lead,'p_phone':phone,'p_body':'Synthetic test only'}).execute().data
                    return {'transport':'sms','reference':reference,**result}
                result = client.rpc('claim_retell_call_versioned', {'p_id':reference,'p_lead':lead,'p_phone':phone,'p_operator':owner,'p_agent':'agent_synthetic','p_version':7,'p_from':'+12145550990'}).execute().data
                return {'transport':'call','reference':reference,**result}
            futures = [pool.submit(attempt, index) for index in range(count)]
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                waiters = db.query("SELECT pid FROM pg_stat_activity WHERE application_name LIKE %s AND wait_event_type='Lock' AND wait_event='advisory'", [token+'%'])
                if len(waiters) == count:
                    break
                time.sleep(0.05)
            assert len({row['pid'] for row in waiters}) == count, waiters
            db.query("SELECT pg_advisory_unlock(hashtextextended('seller-outreach:'||%s,0))", [phone])
            locked = False
            outcomes = [future.result(timeout=10) for future in futures]
            winners = [row for row in outcomes if row.get('claimed')]
            assert len(winners) == 1, outcomes
            assert all(row.get('reason') == 'unresolved_attempt' for row in outcomes if not row.get('claimed')), outcomes
            total = db.query("SELECT (SELECT count(*) FROM retell_call_requests WHERE phone_number=%s)+(SELECT count(*) FROM sms_events WHERE phone_number=%s AND direction='outbound') n", [phone, phone])[0]['n']
            assert total == 1, total
            if not mixed:
                winner = winners[0]
                saved = db.query('SELECT * FROM retell_call_requests WHERE id=%s', [winner['reference']])[0]
                assert (saved['requested_agent_id'], saved['requested_agent_version'], saved['requested_from_number']) == ('agent_synthetic', 7, '+12145550990')
                replay = clients[0].rpc('claim_retell_call_versioned', {'p_id':winner['reference'],'p_lead':lead,'p_phone':phone,'p_operator':owner,'p_agent':'agent_synthetic','p_version':7,'p_from':'+12145550990'}).execute().data
                assert replay == {'claimed':False,'reason':'existing_reference'}, replay
                for column, value in [('requested_agent_id','changed_agent'),('requested_agent_version',8),('requested_from_number','+12145550991'),('phone_number','+12145550992')]:
                    try:
                        db.query('UPDATE retell_call_requests SET '+column+'=%s WHERE id=%s', [value, winner['reference']])
                    except Exception as exc:
                        assert getattr(exc, 'pgcode', None) == 'P0001' and 'identity is immutable' in str(exc), str(exc)
                    else:
                        raise AssertionError('Pinned identity mutation succeeded: '+column)
                assert db.query('SELECT * FROM retell_call_requests WHERE id=%s', [winner['reference']])[0] == saved
            return {'workers':count,'overlapping_backend_sessions':len(waiters),'claims':1,'mode':'call_vs_sms' if mixed else 'versioned_calls','provider_calls':0}
        finally:
            if locked:
                db.query("SELECT pg_advisory_unlock(hashtextextended('seller-outreach:'||%s,0))", [phone])
            pool.shutdown(wait=True)
            for client in clients:
                client.connection.close()

    results = [overlap('+12145550971', False), overlap('+12145550972', True)]
    print(json.dumps({'versioned_call_concurrency':'passed','scenarios':results,'immutable_fields_tested':4,'same_reference_replay':'refused','schema':'restored saved catalog plus eleven integration migrations','provider_calls':0}), flush=True)


if __name__ == '__main__':
    db = Database()
    try:
        verify(db)
    finally:
        db.connection.close()
