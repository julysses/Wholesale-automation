"""Real PostgreSQL proof for the main CSV transaction; synthetic rows only.

The application still uses its old route until durable AI claims and correlated
API responses are wired. This verifies the database foundation, not go-live.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import time
from uuid import uuid4

from tests.local_journey_db import Database
from web.api import _lead_import_key

OWNER = '00000000-0000-4000-8000-000000000777'
OPTIONS = {'score_on_import': False, 'engine': 'rules', 'list_name': 'Synthetic CSV', 'filename': 'synthetic.csv'}
MIGRATION = '20261022170346_integration_csv_lead_intake.sql'


def verify(db):
    client = Database()
    client.query('SET ROLE service_role')
    operator = str(uuid4())
    db.query('INSERT INTO auth.users VALUES(%s)', [operator])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'csv-operator@example.test','user','approved')", [operator])

    def save(rows, ref=None, options=None, connection=client, actor=operator):
        return connection.rpc('import_csv_leads', {'p_id': ref or str(uuid4()), 'p_operator': actor,
            'p_rows': rows, 'p_options': options if options is not None else OPTIONS}).execute().data

    def refused(rows, ref=None, options=None, actor=operator):
        try:
            save(rows, ref, options, actor=actor)
        except Exception as exc:
            assert getattr(exc, 'pgcode', None) == '22023', str(exc)
        else:
            raise AssertionError('Invalid or conflicting import accepted')

    try:
        # SQL identity must preserve the existing application matching contract.
        suffixes = ['Street', 'Avenue', 'Drive', 'Lane', 'Road', 'Court', 'Boulevard', 'Place', 'Circle',
            'Trail', 'Parkway', 'Highway', 'Terrace', 'Square', 'Loop']
        cases = [{'property_address': f'123 North Main {suffix}. # 7', 'city': '  Dallas\t ', 'state': ' tx '}
            for suffix in suffixes]
        cases += [{'property_address': address, 'city': city, 'state': 'TX'} for address, city in [
            ('123 South Main St', 'Dallas'), ('123 North Main St', 'Dallas'), ('12-14 Main St', 'Dallas'),
            ('123 Main Street', 'Fort  Worth'), ('123 Main St', 'Dallas'), ('123 Main St', 'Plano'),
            ('123 Main St.', '\t Dallas \n'), ('123 Main St Unit 1', 'Dallas'), ('123 Main St Unit 2', 'Dallas')]]
        for row in cases:
            result = db.query('SELECT private.csv_lead_key(%s,%s,%s) key', [row['property_address'], row['city'], row['state']])[0]['key']
            assert result == _lead_import_key(row), (row, result, _lead_import_key(row))
        assert _lead_import_key(cases[15]) != _lead_import_key(cases[16])

        rows = [{'property_address': f'{n} Atomic CSV Street', 'city': 'Dallas', 'state': 'TX',
            'owner_first_name': 'Synthetic', 'asking_price': 0, 'source': 'tax'} for n in range(1, 7)]
        ref = str(uuid4())
        result = save(rows, ref)
        receipt = result['receipt']; outcome = receipt['result']
        assert outcome['imported'] == 6 and outcome['existing'] == 0 and outcome['scored'] == 0
        assert outcome['scoring_state'] == 'disabled' and result['outreach_authorized'] is False
        assert receipt['operator_id'] == operator and outcome['intake_owner_id'] == OWNER
        for mapping in outcome['rows']:
            lead = db.query('SELECT * FROM leads WHERE id=%s', [mapping['lead_id']])[0]
            task = db.query('SELECT * FROM tasks WHERE id=%s', [mapping['task_id']])[0]
            assert lead['assigned_to'] == OWNER != operator and Decimal(str(lead['asking_price'])) == 0
            assert lead['ai_calling_paused'] and not lead['sms_sequence_active'] and not lead['email_sequence_active']
            assert task['lead_id'] == lead['id'] and task['assigned_to'] == OWNER
            assert task['type'] == 'follow_up' and task['status'] == 'pending' and task['due_date']
        assert save(rows, ref) == {**result, 'replayed': True}
        assert db.query('SELECT count(*) n FROM lead_lists WHERE id=%s', [outcome['list_id']])[0]['n'] == 1
        assert db.query('SELECT count(*) n FROM tasks WHERE lead_id IN (SELECT jsonb_array_elements_text(%s::jsonb)::uuid)', [[m['lead_id'] for m in outcome['rows']]])[0]['n'] == 6
        changed = deepcopy(rows); changed[0]['source'] = 'vacant'
        refused(changed, ref)
        refused(rows, ref, {**OPTIONS, 'engine': 'ai'})
        refused(rows, ref, actor=OWNER)

        # Fill blanks, union provenance, retain all existing workflow/suppression.
        lead_id = outcome['rows'][0]['lead_id']; task_id = outcome['rows'][0]['task_id']
        db.query("UPDATE leads SET dnc=true,status='under_contract',assigned_to=NULL,contact_attempts=9,score_motivation=3,motivation_tag='operator evidence',seller_notes='verified notes',internal_notes='keep history',sms_sequence_active=false,email_sequence_active=false WHERE id=%s", [lead_id])
        db.query("UPDATE tasks SET status='completed',completed_at=now() WHERE id=%s", [task_id])
        prior = db.query('SELECT * FROM leads WHERE id=%s', [lead_id])[0]
        prior_task = db.query('SELECT * FROM tasks WHERE id=%s', [task_id])
        merged = save([{'property_address': '  1 Atomic CSV St. ', 'city': 'DALLAS', 'state': 'TX',
            'owner_email': 'new-evidence@example.test', 'source': 'vacant | tax', 'status': 'new',
            'motivation_tag': 'replace forbidden', 'seller_notes': 'replace forbidden', 'internal_notes': 'stack_count=2'}])
        current = db.query('SELECT * FROM leads WHERE id=%s', [lead_id])[0]
        assert merged['receipt']['result']['owner_review'] == 1
        assert merged['receipt']['result']['imported'] == 0 and merged['receipt']['result']['existing'] == 1
        assert current['owner_email'] == 'new-evidence@example.test' and current['source'] == 'tax | vacant'
        assert current['internal_notes'] == 'keep history\nstack_count=2'
        for key in set(prior) - {'updated_at', 'owner_email', 'source', 'internal_notes'}:
            assert current[key] == prior[key], (key, current[key], prior[key])
        assert db.query('SELECT * FROM tasks WHERE id=%s', [task_id]) == prior_task
        unchanged = db.query('SELECT * FROM leads WHERE id=%s', [lead_id])
        save([{'property_address': '1 Atomic CSV St', 'city': 'Dallas', 'state': 'TX', 'source': 'tax | vacant', 'internal_notes': 'stack_count=2'}])
        assert db.query('SELECT * FROM leads WHERE id=%s', [lead_id]) == unchanged
        # No new source/note evidence must not truncate long historical provenance
        # or turn empty historical fields into NULL and bump updated_at.
        untouched_id = str(uuid4())
        db.query("INSERT INTO leads(id,property_address,city,state,source,internal_notes) VALUES(%s,'999 Historical Source CSV St','Dallas','TX',%s,'')", [untouched_id, 'historical-'*40])
        untouched = db.query('SELECT * FROM leads WHERE id=%s',[untouched_id])
        save([{'property_address':'999 Historical Source CSV Street','city':'Dallas','state':'TX'}])
        assert db.query('SELECT * FROM leads WHERE id=%s',[untouched_id]) == untouched
        # Default scoring must not rewrite worked leads or completed tasks.
        scored = save([rows[0], {'property_address': '900 Free Rules CSV St', 'city': 'Dallas', 'state': 'TX', 'source': 'tax | vacant'}], options={**OPTIONS, 'score_on_import': True})
        assert scored['receipt']['result']['scored'] == 1
        worked = db.query('SELECT * FROM leads WHERE id=%s', [lead_id])[0]
        for key in ['status','dnc','assigned_to','contact_attempts','score_motivation','motivation_tag','seller_notes','internal_notes']:
            assert worked[key] == current[key], key
        rules_lead = scored['receipt']['result']['rows'][1]['lead_id']
        assert db.query('SELECT score_motivation,ai_calling_paused FROM leads WHERE id=%s', [rules_lead])[0] == {'score_motivation':3,'ai_calling_paused':True}

        # AI intent is durable but no provider dispatch is implemented by this RPC.
        ai_rows = [{'property_address':'901 Pending AI CSV St','city':'Dallas','state':'TX'}]
        ai = save(ai_rows, options={**OPTIONS,'score_on_import':True,'engine':'ai'})
        ai_receipt = ai['receipt']
        assert ai_receipt['result']['scoring_state'] == 'pending' and ai_receipt['result']['scored'] == 0
        pending = db.query('SELECT state,to_jsonb(lead_ids) lead_ids FROM private.csv_import_scoring WHERE import_id=%s', [ai_receipt['id']])[0]
        assert pending['state'] == 'pending' and len(pending['lead_ids']) == 1, pending
        competing = save(ai_rows, options={**OPTIONS,'score_on_import':True,'engine':'ai'})
        assert db.query('SELECT to_jsonb(lead_ids) lead_ids FROM private.csv_import_scoring WHERE import_id=%s', [competing['receipt']['id']])[0]['lead_ids'] == []
        assert save(ai_rows, ai_receipt['id'], {**OPTIONS,'score_on_import':True,'engine':'ai'})['replayed']

        # All-or-nothing errors, including list/task creation and numeric failures.
        counts = db.query('SELECT (SELECT count(*) FROM leads) leads,(SELECT count(*) FROM tasks) tasks,(SELECT count(*) FROM lead_lists) lists,(SELECT count(*) FROM private.csv_lead_imports) receipts')
        valid = {'property_address':'Never persist CSV','city':'Dallas','state':'TX'}
        for invalid in [{'property_address':'Missing city'}, {**valid,'assigned_to':OWNER},
            {**valid,'sms_sequence_active':True}, {**valid,'asking_price':-1}, {**valid,'bedrooms':1.5},
            {**valid,'property_type':True}, {**valid,'state':'BAD'}]:
            refused([valid, invalid])
        assert db.query('SELECT (SELECT count(*) FROM leads) leads,(SELECT count(*) FROM tasks) tasks,(SELECT count(*) FROM lead_lists) lists,(SELECT count(*) FROM private.csv_lead_imports) receipts') == counts
        for options in [{**OPTIONS,'engine':'unknown'},{**OPTIONS,'score_on_import':'true'},{**OPTIONS,'sms_live':True}]:
            refused([valid], options=options)
        db.query("DELETE FROM app_settings WHERE key='lead_owner_user_id'")
        refused([valid])
        assert save(rows, ref)['replayed']  # historical receipt survives owner config change
        db.query("INSERT INTO app_settings(key,value) VALUES('lead_owner_user_id',%s)", [operator])
        db.query("UPDATE profiles SET status='pending' WHERE id=%s", [operator])
        refused([valid], actor=OWNER)
        refused([valid])
        db.query("UPDATE profiles SET status='approved' WHERE id=%s", [operator])
        db.query("UPDATE app_settings SET value=%s WHERE key='lead_owner_user_id'", [OWNER])
        assert not db.query("SELECT id FROM leads WHERE property_address='Never persist CSV'")
        for sql in ['UPDATE private.csv_lead_imports SET payload=payload WHERE id=%s', 'DELETE FROM private.csv_lead_imports WHERE id=%s']:
            try:
                db.query(sql, [ref])
            except Exception as exc:
                assert getattr(exc,'pgcode',None) == 'P0001' and 'immutable' in str(exc)
            else:
                raise AssertionError('Immutable receipt changed')

        # Existing records beyond a REST page cap are resolved by an indexed SQL lookup.
        db.query("INSERT INTO leads(property_address,city,state) SELECT n||' Existing Bulk CSV St','Dallas','TX' FROM generate_series(1,1002) n")
        beyond = save([{'property_address':'1002 Existing Bulk CSV Street','city':'Dallas','state':'TX'}])
        assert beyond['receipt']['result']['existing'] == 1 and beyond['receipt']['result']['imported'] == 0
        bulk = save([{'property_address':f'{n} New Bulk CSV St','city':'Dallas','state':'TX'} for n in range(501)])
        assert bulk['receipt']['result']['imported'] == 501
        assert len({m['task_id'] for m in bulk['receipt']['result']['rows']}) == 501
        # Same street in distinct cities and cardinal directions remains distinct.
        distinct = save([{'property_address':a,'city':c,'state':'TX'} for a,c in [
            ('800 North Safe CSV St','Dallas'),('800 South Safe CSV St','Dallas'),('800 North Safe CSV St','Plano')]])
        assert distinct['receipt']['result']['imported'] == 3
        db.query("INSERT INTO leads(property_address,city,state) VALUES('5 Ambiguous CSV Street','Dallas','TX'),('5 Ambiguous CSV St.','Dallas','TX')")
        refused([valid, {'property_address':'5 Ambiguous CSV St','city':'Dallas','state':'TX'}])
        assert not db.query("SELECT id FROM leads WHERE property_address='Never persist CSV'")

        # Browser writers can maintain the index; business RPC/private receipts remain denied.
        browser = Database()
        try:
            browser.query('SET ROLE authenticated')
            browser.query("SELECT set_config('request.jwt.claim.sub',%s,false)",[OWNER])
            browser.query("SELECT set_config('request.jwt.claim.role','authenticated',false)")
            browser.query("INSERT INTO leads(property_address,city,state,assigned_to) VALUES('Browser Index CSV','Dallas','TX',%s)",[OWNER])
            try:
                save([valid], connection=browser)
            except Exception as exc:
                assert getattr(exc,'pgcode',None) == '42501', str(exc)
            else:
                raise AssertionError('Browser invoked server-only import')
            try:
                browser.query('SELECT * FROM private.csv_lead_imports')
            except Exception as exc:
                assert getattr(exc,'pgcode',None) == '42501'
            else:
                raise AssertionError('Browser read private receipts')
        finally:
            browser.connection.close()

        # Eight independently observed sessions overlap on different references.
        token = 'csv_race_' + uuid4().hex
        clients = [Database() for _ in range(8)]
        pool = ThreadPoolExecutor(max_workers=8); locked = False
        try:
            for n,c in enumerate(clients):
                c.query('SET ROLE service_role')
                c.query("SELECT set_config('application_name',%s,false)",[token+str(n)])
            db.query("SELECT pg_advisory_lock(hashtextextended('manual-lead-import',0))"); locked = True
            payload = [{'property_address':'777 Concurrent Main CSV St','city':'Dallas','state':'TX'}]
            futures = [pool.submit(save,payload,connection=c) for c in clients]
            deadline = time.monotonic()+10; waiters = []
            while time.monotonic()<deadline:
                waiters = db.query("SELECT pid FROM pg_stat_activity WHERE application_name LIKE %s AND wait_event='advisory'",[token+'%'])
                if len(waiters)==8:
                    break
                time.sleep(0.05)
            assert len({r['pid'] for r in waiters})==8, waiters
            db.query("SELECT pg_advisory_unlock(hashtextextended('manual-lead-import',0))"); locked = False
            outcomes = [f.result(timeout=15)['receipt']['result'] for f in futures]
            assert sum(x['imported'] for x in outcomes)==1 and sum(x['existing'] for x in outcomes)==7
            ids = {x['rows'][0]['lead_id'] for x in outcomes}; assert len(ids)==1
            assert db.query('SELECT count(*) n FROM tasks WHERE lead_id=%s',[next(iter(ids))])[0]['n']==1
        finally:
            if locked:
                db.query("SELECT pg_advisory_unlock(hashtextextended('manual-lead-import',0))")
            pool.shutdown(wait=True)
            for c in clients:
                c.connection.close()
        print(json.dumps({'csv_lead_transaction':'passed','application_route':'not_yet_connected',
            'normalization_cases':len(cases),'owned_due_tasks':6,'bulk_owned_tasks':501,
            'existing_lookup_beyond_1000':True,'worked_fields_and_completed_task_preserved':True,
            'same_reference_replay':'passed','ambiguous_identity':'refused','invalid_batch_rollback':'passed',
            'owner_fail_closed':'passed','rules_scored':1,'ai_pending_intent_only':True,
            'browser_index_write':'passed','server_only_rpc':'passed','immutable_receipt':'passed',
            'concurrent_sessions':8,'concurrent_new_properties':1,'concurrent_existing_results':7,'concurrent_tasks':1,
            'provider_calls':0}),flush=True)
    finally:
        client.connection.close()


if __name__ == '__main__':
    db = Database()
    try:
        verify(db)
    finally:
        db.connection.close()
