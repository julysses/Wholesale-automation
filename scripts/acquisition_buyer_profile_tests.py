"""Actual authenticated buyer version RPCs against a disposable complete catalog."""
import json
from pathlib import Path
from acquisition_buyer_catalog_inventory import main
from acquisition_buyer_storage_tests import probe as storage_probe, USER,WS,WS2,BUYER,LEGACY
from schemas.acquisition_buyers import AcquisitionBuyerRequest,AcquisitionBuyerReceipt
from uuid import UUID

PROFILE='af151000-0000-4000-8000-000000000001'
REQUEST='af151000-0000-4000-8000-000000000002'
UPDATE='af151000-0000-4000-8000-000000000003'


def probe(db):
    storage_probe(db)
    db.query("INSERT INTO workspace_memberships(workspace_id,user_id,role) VALUES(%s,%s,'owner')",[WS,USER])
    details=dict(first_name='Example',last_name='Buyer',company=None,email='buyer@example.test',phone='+12145550100',
                 target_zips=['75001'],property_types=['SFR'],strategies=['fix_flip'],min_price_cents=None,
                 max_price_cents=30000000,max_repairs_cents=0,close_speed_days=None,active=True,
                 source_note='Buyer provided these preferences for internal review.')
    request=AcquisitionBuyerRequest(id=REQUEST,buyer_id=PROFILE,expected_revision=0,details=details)
    def call(identity=REQUEST,buyer=PROFILE,revision=0,body=None,workspace=WS,role='authenticated',aal='aal2',fails=None):
        db.query('SET ROLE '+role)
        try:
            db.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps(dict(sub=USER,role=role,session_id=USER,aal=aal))])
            try:rows=db.query('SELECT public.record_acquisition_buyer(%s,%s,%s,%s,%s::jsonb) AS receipt',
                              [identity,workspace,buyer,revision,json.dumps(details if body is None else body)])
            except Exception as exc:
                if fails:
                    if isinstance(fails,str):assert fails in str(exc),str(exc)
                    return
                raise
            if fails:raise AssertionError('Expected buyer save rejection')
            return rows[0]['receipt']
        finally:
            db.query('RESET ROLE');db.query("SELECT set_config('request.jwt.claims','{}',false)")
    for role in ('anon','service_role'):call(role=role,fails=True)
    call(aal='aal1',fails='Buyer workspace authority required')
    call(workspace=WS2,fails='Buyer workspace authority required')
    for field in ('pof_verified','sms_opt_in','workspace_id'):call(body=details|{field:True},fails='Exact bounded buyer details required')
    call(buyer=LEGACY,fails='Buyer unavailable in this workspace')
    call(buyer=BUYER,revision=1,fails='Buyer profile history unavailable')
    saved=AcquisitionBuyerReceipt.model_validate(call())
    assert saved.confirms(request,UUID(WS)) and not saved.duplicate
    assert AcquisitionBuyerReceipt.model_validate(call()).duplicate
    assert db.query('SELECT min_price,max_price,max_repairs,acquisition_revision FROM buyers WHERE id=%s',[PROFILE])==[
        dict(min_price=None,max_price=300000,max_repairs=0,acquisition_revision=1)]
    call(body=details|{'company':'Changed'},fails='Buyer request conflict')
    call(identity=UPDATE,revision=0,fails='Buyer revision changed')
    new_details=details|{'company':'Updated company','max_price_cents':None}
    changed=call(identity=UPDATE,revision=1,body=new_details)
    assert changed['revision']==2 and not changed['duplicate'] and changed['details']==new_details
    historical=call()
    assert historical['revision']==1 and historical['details']==details and historical['duplicate']
    # Separate connections exercise the real advisory/row locks, not a mock.
    import psycopg2
    import time
    from concurrent.futures import ThreadPoolExecutor
    from rehearse_acquisition_baseline import DisposableDatabase
    dsn=db.connection.get_dsn_parameters()
    def connection(label):
        value=object.__new__(DisposableDatabase)
        value.connection=psycopg2.connect(host=dsn['host'],dbname=dsn['dbname'],user='test_admin',application_name=label)
        value.connection.autocommit=True
        return value
    def threaded_save(identity,buyer,revision,label):
        other=connection(label)
        try:
            other.query("SET statement_timeout='8s'")
            other.query('SET ROLE authenticated')
            other.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps(dict(sub=USER,role='authenticated',session_id=USER,aal='aal2'))])
            return other.query('SELECT public.record_acquisition_buyer(%s,%s,%s,%s,%s::jsonb) AS receipt',
                               [identity,WS,buyer,revision,json.dumps(details)])[0]['receipt']
        finally:other.connection.close()
    parallel_id='af151000-0000-4000-8000-000000000004'
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(threaded_save,parallel_id,PROFILE,2,'buyer-profile-parallel-'+str(n)) for n in range(2)]
        outcomes=[job.result(timeout=10) for job in jobs]
    assert sorted(r['duplicate'] for r in outcomes)==[False,True]
    assert all(r['revision']==3 for r in outcomes)
    for index,mode in enumerate(('membership','session','activation'),10):
        waiting_buyer=f'af151000-0000-4000-8000-{index:012d}'
        holder=connection('buyer-profile-holder')
        holder.query('BEGIN')
        holder.query("SELECT pg_advisory_xact_lock(hashtextextended('buyer-ref:'||%s,0))",[waiting_buyer])
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                job=pool.submit(threaded_save,waiting_buyer,waiting_buyer,0,'buyer-profile-wait')
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if db.query("SELECT pid FROM pg_stat_activity WHERE application_name='buyer-profile-wait' AND wait_event='advisory'"):break
                    time.sleep(.02)
                else:raise AssertionError('Buyer write did not reach the held advisory lock')
                if mode=='membership':db.query("UPDATE workspace_memberships SET status='revoked' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
                elif mode=='session':db.query("UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id=%s",[USER])
                else:db.query('UPDATE private.acquisition_activation SET enabled=false')
                holder.query('COMMIT')
                try:job.result(timeout=10)
                except psycopg2.Error as exc:assert exc.pgcode in ('42501','55000'),str(exc)
                else:raise AssertionError('Changed authority was ignored after lock wait')
        finally:
            holder.query('ROLLBACK');holder.connection.close()
            db.query('UPDATE private.acquisition_activation SET enabled=true')
            db.query("UPDATE workspace_memberships SET status='active' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
            db.query('UPDATE auth.sessions SET not_after=NULL WHERE id=%s',[USER])
        assert not db.query('SELECT id FROM buyers WHERE id=%s',[waiting_buyer])
    db.query('UPDATE private.acquisition_activation SET enabled=false')
    assert call()['duplicate']
    call(identity='af151000-0000-4000-8000-000000000005',revision=3,fails='Acquisition paused')
    db.query("UPDATE workspace_memberships SET status='revoked' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    call(fails='Buyer workspace authority required')
    assert db.query('SELECT count(*) AS n FROM private.acquisition_buyer_versions WHERE buyer_id=%s',[PROFILE])==[{'n':3}]
    assert db.query("SELECT count(*) AS n FROM audit_logs WHERE entity_id=%s AND entity_type='acquisition_buyer'",[PROFILE])==[{'n':3}]
    try:db.query('DELETE FROM private.acquisition_buyer_versions WHERE buyer_id=%s',[PROFILE])
    except Exception as exc:assert 'Buyer versions are immutable' in str(exc)
    else:raise AssertionError('Buyer history deletion allowed')
    result={'scope':'Disposable full117 schema, actual authenticated RPC roles and typed receipts; actual simultaneous retry and revocation-during-lock checks; no mounted API/UI acceptance yet',
            'checks':['owner MFA and workspace authorization','anonymous/service denial','invalid authority injection rejected','no legacy adoption or missing-history adoption',
                      'canonical unknown economics preserved','exact create and update revisions','exact replay returns historical receipt','changed retry/stale revision rejected',
                      'paused recovery without new save','revoked membership denies recovery','one audit/version per save and immutable history','simultaneous exact retry creates one revision','membership/session/activation changes during lock wait deny save'],
            'production_changed':False}
    Path('docs/acquisition-automation/evidence/2026-11-01-buyer-profile-focused-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main(probe)
