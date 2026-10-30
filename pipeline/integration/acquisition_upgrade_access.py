"""Actual SQL role probes on the upgraded catalog; all mutations roll back."""
import json

import psycopg2

from rehearse_acquisition_upgrade import ADMIN, LEAD

OTHER = '00000000-0000-4000-8000-000000000778'
CALLER = '00000000-0000-4000-8000-000000000779'
WORKSPACE = '10000000-0000-4000-8000-000000000777'
WORKSPACE_B = '10000000-0000-4000-8000-000000000778'


def run_access_probes(db):
    checks = []

    def actor(sql, params=(), user=ADMIN, role='authenticated', aal='aal2', session=True):
        if role not in ('authenticated', 'anon', 'service_role'):
            raise ValueError('Unexpected test role')
        db.query('SET LOCAL ROLE ' + role)
        claims = dict(sub=user, role=role, aal=aal)
        if session:
            claims['session_id'] = user
        db.query("SELECT set_config('request.jwt.claims',%s,true)", [json.dumps(claims)])
        try:
            return db.query(sql, params)
        finally:
            # A failed statement needs the caller's savepoint rollback first.
            if db.connection.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_INERROR:
                db.query('RESET ROLE')

    def reject(label, sql, params=(), code='42501', **kwargs):
        db.query('SAVEPOINT rejected_operation')
        try:
            actor(sql, params, **kwargs)
        except psycopg2.Error as error:
            if error.pgcode != code:
                raise AssertionError(f'{label}: unexpected SQLSTATE {error.pgcode}') from error
        else:
            raise AssertionError(label + ': forbidden operation succeeded')
        finally:
            db.query('ROLLBACK TO SAVEPOINT rejected_operation; RELEASE SAVEPOINT rejected_operation; RESET ROLE')
        checks.append(label)

    def visible(user, expected, **kwargs):
        actual = actor('SELECT id::text FROM public.workspaces ORDER BY id', user=user, **kwargs)
        if actual != [{'id': value} for value in expected]:
            raise AssertionError(f'Unexpected workspace visibility for {user}: {actual}')

    db.query('BEGIN')
    try:
        reject('activation blocks enrollment', 'SELECT public.create_acquisition_workspace(%s,%s)',
               [WORKSPACE, 'Synthetic access rehearsal'], code='55000')
        for role in ('authenticated', 'anon', 'service_role'):
            reject(role + ' cannot activate', 'UPDATE private.acquisition_activation SET enabled=true', role=role)
        # Synthetic approval exists only inside this rolled-back, offline transaction.
        db.query("UPDATE private.acquisition_activation SET enabled=true,approval_ref='synthetic offline access test',application_revision=repeat('a',40),verified_at=now()")
        for user, role in ((OTHER, 'admin'), (CALLER, 'user')):
            db.query('INSERT INTO auth.users(id) VALUES(%s)', [user])
            db.query('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)', [user,user])
            db.query("INSERT INTO public.profiles(id,email,role,status) VALUES(%s,%s,%s,'approved')", [user,user+'@example.test',role])
        for user, workspace in ((ADMIN, WORKSPACE), (OTHER, WORKSPACE_B)):
            actor('SELECT public.create_acquisition_workspace(%s,%s)', [workspace,'Synthetic access rehearsal'], user=user)
        visible(ADMIN, [WORKSPACE]); visible(OTHER, [WORKSPACE_B]); visible(CALLER, [])
        checks.append('two owners and nonmember isolated')
        actor('SELECT public.create_acquisition_workspace(%s,%s)', [WORKSPACE,'Synthetic access rehearsal'])
        if db.query('SELECT count(*) AS n FROM public.audit_logs WHERE workspace_id=%s', [WORKSPACE]) != [{'n':1}]:
            raise AssertionError('Workspace retry duplicated audit')
        checks.append('workspace creation retry idempotent')
        reject('other owner cannot take workspace', 'SELECT public.create_acquisition_workspace(%s,%s)', [WORKSPACE,'Synthetic access rehearsal'], user=OTHER)
        actor("SELECT public.set_acquisition_membership(%s,%s,'acquisition_caller','active')", [WORKSPACE,CALLER])
        visible(CALLER, [WORKSPACE]); visible(CALLER, [], aal='aal1')
        checks.append('caller MFA enforced')
        actor('SELECT public.bind_acquisition_lead(%s,%s,NULL)', [WORKSPACE,LEAD])
        if actor('SELECT public.list_acquisition_leads(%s) AS items', [WORKSPACE], user=CALLER) != [{'items':[]}]:
            raise AssertionError('Unassigned caller saw lead')
        actor('SELECT public.assign_acquisition_lead(%s,%s,%s)', [WORKSPACE,LEAD,CALLER])
        items=actor('SELECT public.list_acquisition_leads(%s) AS items', [WORKSPACE], user=CALLER)[0]['items']
        if len(items)!=1 or items[0]['lead_id']!=LEAD or 'owner_phone_1' in items[0]:
            raise AssertionError('Assigned queue missing lead or exposes raw contact')
        checks.append('assigned caller queue and contact minimization')
        for user, expected in ((ADMIN,1),(OTHER,0),(CALLER,0)):
            if actor('SELECT count(*) AS n FROM public.leads WHERE id=%s', [LEAD], user=user) != [{'n':expected}]:
                raise AssertionError('Legacy lead policy bypassed acquisition scope')
        checks.append('legacy lead policies preserve workspace and caller boundaries')

        reject('cross-workspace queue denied', 'SELECT public.list_acquisition_leads(%s)', [WORKSPACE], user=OTHER)
        for role in ('authenticated', 'anon', 'service_role'):
            reject(role+' raw workspace write denied', "UPDATE public.workspaces SET status='suspended' WHERE id=%s", [WORKSPACE], role=role)
        reject('caller cannot administer membership', "SELECT public.set_acquisition_membership(%s,%s,'owner','active')", [WORKSPACE,CALLER], user=CALLER)
        db.query("UPDATE auth.sessions SET not_after=now()-interval '1 second' WHERE id=%s", [CALLER])
        visible(CALLER, [])
        reject('expired session queue denied', 'SELECT public.list_acquisition_leads(%s)', [WORKSPACE], user=CALLER)
        db.query('UPDATE auth.sessions SET not_after=NULL WHERE id=%s', [CALLER])
        visible(CALLER, [WORKSPACE])
        db.query("UPDATE public.profiles SET status='suspended' WHERE id=%s", [CALLER])
        visible(CALLER, [])
        db.query("UPDATE public.profiles SET status='approved' WHERE id=%s", [CALLER])
        visible(CALLER, [WORKSPACE])
        checks.append('profile suspension immediate')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        reject('disabled gate prevents new enrollment', 'SELECT public.create_acquisition_workspace(gen_random_uuid(),%s)', ['Denied while held'], code='55000')
        actor("SELECT public.set_acquisition_membership(%s,%s,'acquisition_caller','revoked')", [WORKSPACE,CALLER])
        visible(CALLER, [])
        checks.append('membership revocation immediate')
    finally:
        db.query('ROLLBACK; RESET ROLE')
    if db.query('SELECT enabled FROM private.acquisition_activation') != [{'enabled':False}]:
        raise AssertionError('Access rehearsal left activation enabled')
    if db.query('SELECT count(*) AS n FROM public.workspaces') != [{'n':0}]:
        raise AssertionError('Access rehearsal left workspace data')
    return {'full_catalog_access_probes':'passed','checks':checks,'changes_rolled_back':True,
            'jwt_transport_verified':False}
