"""Exercise reviewed SECURITY DEFINER entry points using real authenticated roles."""
import json
from uuid import uuid4

from tests.local_journey_db import Database


def verify(db):
    target = str(uuid4())
    db.query('INSERT INTO auth.users(id) VALUES(%s)', [target])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,%s,'user','pending')", [target,'target-'+target+'@example.test'])
    baseline = db.query('SELECT role,status,approved_by,denied_by FROM profiles WHERE id=%s', [target])
    notifications = db.query('SELECT count(*) n FROM app_notifications WHERE recipient_id=%s', [target])[0]['n']
    denied_cases = []
    for role, status in [('user','approved'),('user','pending'),('admin','pending'),('admin','denied'),('admin','suspended')]:
        actor = str(uuid4())
        db.query('INSERT INTO auth.users(id) VALUES(%s)', [actor])
        db.query('INSERT INTO profiles(id,email,role,status) VALUES(%s,%s,%s,%s)', [actor,actor+'@example.test',role,status])
        client = Database()
        try:
            client.query('SET ROLE authenticated')
            client.query("SELECT set_config('request.jwt.claim.sub',%s,false)", [actor])
            # User-editable JWT claims must not turn a non-admin profile into an admin.
            client.query("SELECT set_config('request.jwt.claims',%s,false)", [json.dumps({'sub':actor,'user_metadata':{'role':'admin','status':'approved'}})])
            assert client.query('SELECT public.is_approved() approved')[0]['approved'] is (status == 'approved')
            for function, params in [('admin_set_user_role',{'target_user_id':target,'new_role':'admin'}),('admin_set_user_status',{'target_user_id':target,'new_status':'approved','reason':'synthetic test'})]:
                try:
                    client.rpc(function, params).execute()
                except Exception as exc:
                    assert getattr(exc,'pgcode',None) == 'P0001' and 'approved admin role required' in str(exc), str(exc)
                else:
                    raise AssertionError('Unapproved administrator change succeeded')
            assert db.query('SELECT role,status,approved_by,denied_by FROM profiles WHERE id=%s', [target]) == baseline
            assert db.query('SELECT count(*) n FROM app_notifications WHERE recipient_id=%s', [target])[0]['n'] == notifications
            denied_cases.append({'role':role,'status':status,'forged_user_metadata':'rejected','denied_mutations':2})
        finally:
            client.connection.close()
    missing = Database()
    try:
        missing.query('SET ROLE authenticated')
        missing.query("SELECT set_config('request.jwt.claim.sub','',false)")
        assert missing.query('SELECT public.is_approved() approved')[0]['approved'] is False
        try:
            missing.rpc('admin_set_user_role',{'target_user_id':target,'new_role':'admin'}).execute()
        except Exception as exc:
            assert getattr(exc,'pgcode',None)=='P0001' and 'approved admin role required' in str(exc)
        else:
            raise AssertionError('Missing identity authorized a role change')
        missing.query('SET ROLE anon')
        for query in ['SELECT public.is_approved()', "SELECT public.admin_set_user_role('"+target+"'::uuid,'admin')"]:
            try:
                missing.query(query)
            except Exception as exc:
                assert getattr(exc,'pgcode',None)=='42501', str(exc)
            else:
                raise AssertionError('Anonymous access to protected function succeeded')
    finally:
        missing.connection.close()
    admin = Database()
    try:
        admin.query('SET ROLE authenticated')
        admin.query("SELECT set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000777',false)")
        admin.rpc('admin_set_user_role',{'target_user_id':target,'new_role':'admin'}).execute()
        admin.rpc('admin_set_user_status',{'target_user_id':target,'new_status':'approved','reason':'synthetic test'}).execute()
        actual = db.query('SELECT role,status,approved_by FROM profiles WHERE id=%s',[target])[0]
        assert actual == {'role':'admin','status':'approved','approved_by':'00000000-0000-4000-8000-000000000777'}, actual
        assert db.query("SELECT count(*) n FROM app_notifications WHERE recipient_id=%s AND type='access_approved'",[target])[0]['n'] == 1
    finally:
        admin.connection.close()
    print(json.dumps({'authorization_guards':'passed','denied_cases':denied_cases,'missing_identity':'denied','anonymous_rpc_access':'denied','approved_admin_mutations':'passed','production_changes':0,'provider_calls':0}),flush=True)


if __name__ == '__main__':
    db=Database()
    try:
        verify(db)
    finally:
        db.connection.close()
