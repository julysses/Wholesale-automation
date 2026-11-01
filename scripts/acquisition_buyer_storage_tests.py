"""Full-catalog isolated buyer storage boundaries; no providers or hosted data."""
import json
from pathlib import Path
from acquisition_buyer_catalog_inventory import main

USER='af150000-0000-4000-8000-000000000001'
WS='af150000-0000-4000-8000-000000000002'
WS2='af150000-0000-4000-8000-000000000003'
BUYER='af150000-0000-4000-8000-000000000004'
LEGACY='af150000-0000-4000-8000-000000000005'


def probe(db):
    checks=[]
    writer=db.query("SELECT pg_get_userbyid(proowner) AS name FROM pg_proc WHERE oid='private.protect_acquisition_buyer()'::regprocedure")[0]['name']
    assert writer in ('test_admin','postgres')
    def role_query(role,sql,params=(),fails=False):
        db.query('BEGIN')
        try:
            db.query('SET LOCAL ROLE '+role)
            db.query("SELECT set_config('request.jwt.claims',%s,true)",[json.dumps(dict(sub=USER,role=role,session_id=USER,aal='aal2'))])
            try:
                rows=db.query(sql,params)
            except Exception as exc:
                if fails:
                    if isinstance(fails,str):assert fails in str(exc),str(exc)
                    return
                raise
            if fails:raise AssertionError('Expected rejection: '+sql)
            return rows
        finally:db.query('ROLLBACK')
    db.query('INSERT INTO auth.users(id) VALUES(%s)',[USER])
    db.query('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',[USER,USER])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'buyer-owner@example.test','admin','approved')",[USER])
    db.query("UPDATE private.acquisition_activation SET enabled=true,approval_ref='synthetic isolated test',application_revision=repeat('a',40),verified_at=clock_timestamp()")
    for workspace in (WS,WS2):db.query("INSERT INTO workspaces(id,name,created_by) VALUES(%s,'Synthetic buyer workspace',%s)",[workspace,USER])
    db.query("INSERT INTO buyers(id,first_name,last_name,email,active) VALUES(%s,'Legacy','Buyer','legacy@example.test',true)",[LEGACY])
    original=db.query('SELECT to_jsonb(b) AS row FROM buyers b WHERE id=%s',[LEGACY])
    insert="INSERT INTO buyers(id,workspace_id,acquisition_revision,first_name,last_name,email,active,sms_opt_in,email_opt_in,pof_verified) VALUES(%s,%s,1,'Scoped','Buyer','scoped@example.test',true,false,false,false)"
    for role in ('anon','authenticated','service_role'):role_query(role,insert,[BUYER,WS],fails=True)
    db.query('SET ROLE '+writer)
    try:db.query(insert,[BUYER,WS])
    finally:db.query('RESET ROLE')
    checks.append('raw scoped insert denied; trusted fixture inserts canonical buyer')
    for role in ('anon','authenticated'):
        assert role_query(role,'SELECT id FROM buyers WHERE id=%s',[BUYER])==[]
    for role in ('authenticated','service_role'):
        assert role_query(role,'SELECT id FROM buyer_leaderboard WHERE id=%s',[BUYER])==[]
        assert role_query(role,'SELECT id FROM buyer_leaderboard WHERE id=%s',[LEGACY])==[{'id':LEGACY}]
        assert sum(r['buyer_count'] for r in role_query(role,'SELECT buyer_count FROM ibie_segment_summary'))==1
    checks.append('scoped buyer hidden from raw authenticated reads and legacy service views')
    for role in ('authenticated','service_role'):
        role_query(role,'UPDATE buyers SET workspace_id=%s WHERE id=%s',[WS,LEGACY],fails=True)
        changed=role_query(role,'UPDATE buyers SET acquisition_revision=2,first_name=\'Changed\' WHERE id=%s RETURNING id',[BUYER],fails=(role=='service_role'))
        deleted=role_query(role,'DELETE FROM buyers WHERE id=%s RETURNING id',[BUYER],fails=(role=='service_role'))
        if role=='authenticated':assert changed==[] and deleted==[]
        role_query(role,'TRUNCATE buyers CASCADE',fails=True)
    assert db.query('SELECT to_jsonb(b) AS row FROM buyers b WHERE id=%s',[LEGACY])==original
    assert db.query('SELECT acquisition_revision FROM buyers WHERE id=%s',[BUYER])==[{'acquisition_revision':1}]
    checks.append('historical scope immutable; scoped raw mutation/delete/truncate denied')
    # Every FK-bearing legacy surface rejects a scoped buyer before it can leak.
    for table in ('buyer_preferences','buyer_transactions','deal_matches','buyer_outreach_log','tasks','deals'):
        role_query('service_role',f'INSERT INTO {table}(buyer_id) VALUES(%s)',[BUYER],fails='Scoped buyers require a reviewed acquisition relationship')
    db.query('INSERT INTO buyer_preferences(buyer_id) VALUES(%s)',[LEGACY])
    checks.append('all six legacy buyer relationship surfaces reject scoped IDs; legacy preferences remain valid')
    role_query('service_role','UPDATE buyers SET email_opt_in=false WHERE id=%s',[BUYER])
    role_query('service_role','UPDATE buyers SET email_opt_in=true WHERE id=%s',[BUYER],fails=True)
    role_query('service_role','UPDATE buyers SET email_opt_in=false,first_name=\'Changed\' WHERE id=%s',[BUYER],fails=True)
    checks.append('service one-way opt-out preserved without unrelated edits or opt-in')
    role_query(writer,'UPDATE buyers SET workspace_id=%s,acquisition_revision=2 WHERE id=%s',[WS2,BUYER],fails='Buyer identity and workspace are immutable')
    role_query(writer,'UPDATE buyers SET first_name=\'Changed\' WHERE id=%s',[BUYER],fails='Buyer revision must advance exactly once')
    changed=role_query(writer,'UPDATE buyers SET acquisition_revision=2,first_name=\'Changed\' WHERE id=%s RETURNING acquisition_revision',[BUYER])
    assert changed==[{'acquisition_revision':2}]
    checks.append('trusted fixture cannot move workspaces or skip exact revision advancement')
    role_query('service_role',"UPDATE audit_logs SET action='changed' WHERE workspace_id=%s",[WS],fails=True)
    for role in ('anon','authenticated','service_role'):
        role_query(role,'SELECT private.protect_acquisition_buyer()',fails=True)
    assert len(db.query("SELECT id FROM audit_logs WHERE workspace_id=%s AND entity_type='acquisition_buyer'",[WS]))==1
    checks.append('scoped audit immutable and private entry points unavailable')
    result={'scope':'Disposable full-baseline plus116 schema; SQL storage boundaries only; no scoped application/API creation or buyer-selection acceptance yet',
            'checks':checks,'production_changed':False}
    Path('docs/acquisition-automation/evidence/2026-11-01-buyer-storage-focused-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


class BuyerStorageCases:
    def test_acquisition_buyer_storage_boundaries(self):
        import psycopg2
        from rehearse_acquisition_baseline import DisposableDatabase
        db=object.__new__(DisposableDatabase)
        db.connection=psycopg2.connect(host=self.socket,dbname=self.database_name,user='test_admin',connect_timeout=5)
        db.connection.autocommit=True
        try:probe(db)
        finally:db.connection.close()


if __name__=='__main__':main(probe)
