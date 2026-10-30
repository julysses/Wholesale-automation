"""Postal import HTTP concurrency probes in the caller's disposable database."""
from concurrent.futures import ThreadPoolExecutor
import json
import time

import psycopg2

from rehearse_acquisition_upgrade import LEAD


def verify_postal_http(db,request,token,socket,admin,other,workspace):
    owner='81000000-0000-4000-8000-000000000777'
    relation='82000000-0000-4000-8000-000000000777'
    observation='83000000-0000-4000-8000-000000000777'
    raw='77 Synthetic Postal St, Unit 2B, Dallas TX 75001'
    db.query("UPDATE public.leads SET owner_first_name='Synthetic',owner_last_name='Owner',owner_mailing_address=%s WHERE id=%s",[raw,LEAD])
    db.query('SET ROLE authenticated')
    db.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps({'sub':admin,'session_id':admin,'role':'authenticated','aal':'aal2'})])
    try:
        db.query('SELECT public.bind_acquisition_lead(%s,%s,NULL)',[workspace,LEAD])
        db.query('SELECT public.create_acquisition_owner(%s,%s,%s)',[owner,workspace,LEAD])
        db.query("SELECT public.associate_acquisition_owner(%s,%s,%s,%s,'reported_owner','Synthetic postal HTTP provenance test')",[relation,workspace,owner,LEAD])
    finally:db.query('RESET ROLE')
    path='/rpc/import_acquisition_postal_observation'
    body={'p_id':observation,'p_workspace':workspace,'p_relationship':relation}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:request(path,token(),body),range(2)))
    if [status for status,_ in results]!=[200,200] or sorted(row['duplicate'] for _,row in results)!=[False,True]:
        raise AssertionError('Concurrent postal retries did not converge')
    for _,row in results:
        if row['raw_address']!=raw or row['verification_status']!='unverified' or row['execution_authorized']:
            raise AssertionError('Postal HTTP response lost provenance or granted authority')
    if db.query('SELECT count(*) AS n FROM public.acquisition_postal_observations')!=[{'n':1}]:
        raise AssertionError('Concurrent postal retries duplicated history')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_postal_observation'")!=[{'n':1}]:
        raise AssertionError('Concurrent postal retries duplicated audit')
    if request(path,token(other),body)[0]!=403:raise AssertionError('Postal HTTP cross-workspace import accepted')
    if request('/acquisition_postal_observations?select=id',token(other))!=(200,[]):
        raise AssertionError('Postal HTTP cross-workspace data leaked')
    # The request must actually wait on activation before session expiry is tested.
    blocker=psycopg2.connect(host=socket,dbname='acquisition_http',user='test_admin')
    try:
        with blocker.cursor() as cursor:cursor.execute('SELECT singleton FROM private.acquisition_activation FOR UPDATE')
        db.query("UPDATE auth.sessions SET not_after=clock_timestamp()+interval '2 seconds' WHERE id=%s",[admin])
        expiring={**body,'p_id':'83000000-0000-4000-8000-000000000778'}
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(request,path,token(),expiring)
            try:
                deadline=time.monotonic()+1.5
                while not db.query("SELECT count(*) AS n FROM pg_stat_activity WHERE datname='acquisition_http' AND usename='acquisition_http_authenticator' AND wait_event_type='Lock'")[0]['n']:
                    if pending.done() or time.monotonic()>deadline:raise AssertionError('Postal request never reached activation lock')
                    time.sleep(.02)
                while not db.query('SELECT not_after<=clock_timestamp() AS expired FROM auth.sessions WHERE id=%s',[admin])[0]['expired']:
                    if time.monotonic()>deadline+2:raise AssertionError('Session deadline not reached')
                    time.sleep(.02)
            finally:blocker.rollback()
            status,_=pending.result(timeout=6)
            if status!=403:raise AssertionError('Postal import accepted session expired during activation wait')
    finally:
        blocker.close()
        db.query('UPDATE auth.sessions SET not_after=NULL WHERE id=%s',[admin])
    if db.query('SELECT count(*) AS n FROM public.acquisition_postal_observations')!=[{'n':1}]:
        raise AssertionError('Expired postal import committed')
    return ['postal concurrent exact retry','postal HTTP tenant isolation','postal unverified source preserved','postal activation-wait session expiry denied']
