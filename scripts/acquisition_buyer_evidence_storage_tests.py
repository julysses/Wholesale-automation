"""Actual isolated buyer evidence ownership, privacy and legacy Storage containment."""
import json
from pathlib import Path
from acquisition_buyer_catalog_inventory import main
from acquisition_buyer_profile_tests import probe as profile_probe, USER, WS, WS2, PROFILE, LEGACY


def uid(n): return f'af161000-0000-4000-8000-{n:012d}'


def probe(db):
    profile_probe(db)
    db.query('UPDATE private.acquisition_activation SET enabled=true')
    db.query("UPDATE workspace_memberships SET status='active' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    def query(sql,params=(),role='authenticated',aal='aal2',fails=None,actor=USER):
        db.query('SET ROLE '+role)
        db.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps(dict(sub=actor,role=role,session_id=actor,aal=aal))])
        try:
            try: result=db.query(sql,params)
            except Exception as error:
                if fails:
                    assert error.pgcode==fails,(error.pgcode,str(error))
                    return
                raise
            if fails: raise AssertionError('Expected denial: '+sql)
            return result
        finally:
            db.query('RESET ROLE');db.query("SELECT set_config('request.jwt.claims','{}',false)")
    def rejected(sql,params,code):
        try:db.query(sql,params)
        except Exception as error:
            assert error.pgcode==code,(error.pgcode,str(error))
            if code=='P0001':assert 'Contact provenance is append only' in str(error)
        else:raise AssertionError('Invalid evidence accepted')
    assert db.query("SELECT count(*) AS n FROM private.acquisition_evidence_policies WHERE purpose LIKE 'buyer_%'")[0]['n']==0
    for identity,purpose in ((uid(1),'buyer_funds'),(uid(2),'mail_content')):
        db.query("""INSERT INTO private.acquisition_evidence_policies(id,workspace_id,purpose,version,retention_seconds,valid_from,valid_until,
            approval_ref,reviewed_by,reviewed_at) VALUES(%s,%s,%s,1,3600,clock_timestamp()-interval '1 minute',clock_timestamp()+interval '1 hour',
            %s,%s,clock_timestamp()-interval '2 minutes')""",[identity,WS,purpose,uid(3),USER])
    query("SELECT public.create_acquisition_campaign(%s,%s,'Synthetic mail control','direct_mail',0,'USD')",[uid(4),WS])
    insert="""INSERT INTO acquisition_evidence_artifacts(id,workspace_id,campaign_id,contract_id,contract_version,buyer_id,buyer_revision,
        purpose,expected_sha256,expected_byte_size,media_type,retention_policy_id,retain_until,provenance_note,created_by,actor_membership_updated_at,request_hash)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,repeat('a',64),10,'application/pdf',%s,clock_timestamp()+interval '30 minutes',
        'Synthetic evidence fixture, not verified buyer funds',%s,clock_timestamp(),repeat('b',64))"""
    fields=[uid(5),WS,None,None,None,PROFILE,3,'buyer_funds',uid(1),USER]
    for index,value,code in ((1,WS2,'23503'),(2,uid(4),'23514'),(3,uid(6),'23514'),(5,LEGACY,'23503'),(6,None,'23514'),(6,4,'23503'),(7,'mail_content','23514')):
        invalid=fields.copy();invalid[0]=uid(10+index);invalid[index]=value;rejected(insert,invalid,code)
    db.query(insert,fields)
    db.query(insert,[uid(7),WS,uid(4),None,None,None,None,'mail_content',uid(2),USER])
    revoke="""INSERT INTO acquisition_evidence_revocations(id,workspace_id,campaign_id,contract_id,contract_version,buyer_id,buyer_revision,
        artifact_id,reason,actor_id,actor_membership_updated_at,request_hash)
        VALUES(%s,%s,%s,NULL,NULL,%s,%s,%s,'Synthetic retained revocation reason',%s,clock_timestamp(),repeat('c',64))"""
    rejected(revoke,[uid(8),WS,uid(4),PROFILE,3,uid(5),USER],'23514')
    rejected(revoke,[uid(8),WS,None,PROFILE,2,uid(5),USER],'23503')
    db.query(revoke,[uid(8),WS,None,PROFILE,3,uid(5),USER])
    # A second, unrevoked artifact proves Storage denies buyer ownership itself,
    # rather than incidentally denying a revoked/expired/policy-less object.
    second=fields.copy();second[0]=uid(9);db.query(insert,second)
    buyer_path=WS+'/'+uid(9)+'/'+'a'*64
    mail_path=WS+'/'+uid(7)+'/'+'a'*64
    db.query("INSERT INTO storage.objects(bucket_id,name) VALUES('acquisition-evidence',%s),('acquisition-evidence',%s)",[buyer_path,mail_path])
    db.query("SET storage.operation='object.get_authenticated'")
    assert query('SELECT private.acquisition_evidence_object_access(%s,false) AS allowed',[mail_path])==[{'allowed':True}]
    assert query('SELECT private.acquisition_evidence_object_access(%s,false) AS allowed',[buyer_path])==[{'allowed':False}]
    assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)])==[{'id':uid(9)}]
    assert query('SELECT id FROM acquisition_evidence_revocations WHERE id=%s',[uid(8)])==[{'id':uid(8)}]
    assert query('SELECT name FROM storage.objects WHERE name=%s',[buyer_path])==[]
    assert query('SELECT name FROM storage.objects WHERE name=%s',[mail_path])==[{'name':mail_path}]
    assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)],aal='aal1')==[]
    db.query('INSERT INTO auth.users(id) VALUES(%s)',[uid(40)])
    db.query('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',[uid(40),uid(40)])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'other-buyer-review@example.test','admin','approved')",[uid(40)])
    db.query("INSERT INTO workspace_memberships(workspace_id,user_id,role) VALUES(%s,%s,'owner')",[WS2,uid(40)])
    assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)],actor=uid(40))==[]
    assert query('SELECT id FROM acquisition_evidence_revocations WHERE id=%s',[uid(8)],actor=uid(40))==[]
    assert query('SELECT private.acquisition_evidence_object_access(%s,false) AS allowed',[buyer_path],actor=uid(40))==[{'allowed':False}]
    db.query("UPDATE profiles SET role='user' WHERE id=%s",[USER])
    for role in ('operator','acquisition_caller','agency_manager'):
        db.query('UPDATE workspace_memberships SET role=%s WHERE workspace_id=%s AND user_id=%s',[role,WS,USER])
        assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)])==[]
        assert query('SELECT id FROM acquisition_evidence_revocations WHERE id=%s',[uid(8)])==[]
        assert query('SELECT private.acquisition_evidence_object_access(%s,false) AS allowed',[buyer_path])==[{'allowed':False}]
        if role=='operator':
            assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(7)])==[{'id':uid(7)}]
            assert query('SELECT private.acquisition_evidence_object_access(%s,false) AS allowed',[mail_path])==[{'allowed':True}]
    db.query("UPDATE workspace_memberships SET role='owner' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    db.query("UPDATE profiles SET role='admin' WHERE id=%s",[USER])
    for role in ('anon','service_role'):
        query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)],role=role,fails='42501')
        query('SELECT id FROM acquisition_evidence_revocations WHERE id=%s',[uid(8)],role=role,fails='42501')
    query("SELECT public.register_acquisition_evidence(%s,%s,%s,'buyer_funds',repeat('a',64),10,'application/pdf',%s,'Synthetic buyer registration denied')",[uid(30),WS,uid(4),uid(1)],fails='22023')
    db.query("SET storage.operation='object.upload'")
    assert query('SELECT private.acquisition_evidence_object_access(%s,true) AS allowed',[buyer_path])==[{'allowed':False}]
    for table,identity in (('acquisition_evidence_artifacts',uid(9)),('acquisition_evidence_revocations',uid(8))):
        rejected('DELETE FROM '+table+' WHERE id=%s',[identity],'P0001')
        query('UPDATE '+table+' SET id=id WHERE id=%s',[identity],fails='42501')
    db.query("UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id=%s",[USER])
    assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)])==[]
    db.query('UPDATE auth.sessions SET not_after=NULL WHERE id=%s',[USER])
    db.query("UPDATE workspace_memberships SET status='revoked' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    assert query('SELECT id FROM acquisition_evidence_artifacts WHERE id=%s',[uid(9)])==[]
    result={'scope':'Disposable full119 schema; buyer evidence storage/metadata and existing Storage path denial only, no buyer upload/review authority',
        'checks':['exact buyer revision FK and mutually exclusive ownership','cross-workspace/nonexistent revision/purpose rejected',
        'exact immutable revocation binding','owner metadata vs operator/caller/agency denial','MFA and membership revocation deny metadata',
        'anonymous/service raw metadata denial','existing mail metadata and private download preserved',
        'buyer private download/upload denied even with current policy and creator identity','legacy registration rejects buyer purpose','no live buyer policy provisioned'],
        'production_changed':False}
    Path('docs/acquisition-automation/evidence/2026-11-01-buyer-evidence-storage-focused-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


class BuyerEvidenceStorageCases:
    def test_acquisition_buyer_evidence_storage(self):
        import psycopg2
        from rehearse_acquisition_baseline import DisposableDatabase
        db = object.__new__(DisposableDatabase)
        db.connection = psycopg2.connect(host=self.socket, dbname=self.database_name, user='test_admin', connect_timeout=5)
        db.connection.autocommit = True
        try:
            probe(db)
        finally:
            db.connection.close()


if __name__ == '__main__':
    main(probe)
