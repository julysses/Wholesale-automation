"""Real PostgREST JWT/role checks over a private Unix socket, no hosted URLs."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

import psycopg2

from rehearse_acquisition_upgrade import ADMIN

OTHER='00000000-0000-4000-8000-000000000778'
WORKSPACE='10000000-0000-4000-8000-000000000777'
WORKSPACE_B='10000000-0000-4000-8000-000000000778'


def run_postgrest(db, binary, pg):
    folder=Path(db.connection.get_dsn_parameters()['host'])
    binary=Path(binary)
    if not binary.is_absolute() or not binary.is_file():
        raise RuntimeError('Explicit local PostgREST binary required')
    env={'PATH':'/usr/bin:/bin','HOME':str(folder),'TMPDIR':str(folder),'LANG':'C'}
    if os.uname().sysname=='Darwin':
        env['DYLD_LIBRARY_PATH']=subprocess.check_output([str(pg/'pg_config'),'--libdir'],text=True,env=env).strip()
    version=subprocess.check_output([str(binary),'--version'],text=True,env=env).strip()
    if version!='PostgREST 16.5':raise RuntimeError('Reviewed PostgREST 16.5 required')
    db.connection.close()
    control=psycopg2.connect(host=str(folder),dbname='postgres',user='test_admin')
    control.autocommit=True
    process=None;clone=None
    try:
        with control.cursor() as cursor:
            cursor.execute('CREATE DATABASE acquisition_http TEMPLATE acquisition_upgrade')
        from rehearse_acquisition_baseline import DisposableDatabase
        clone=object.__new__(DisposableDatabase)
        clone.connection=psycopg2.connect(host=str(folder),dbname='acquisition_http',user='test_admin')
        clone.connection.autocommit=True
        clone.query('CREATE ROLE acquisition_http_authenticator LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS; GRANT anon,authenticated TO acquisition_http_authenticator')
        clone.query('INSERT INTO auth.users(id) VALUES(%s); INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',[OTHER,OTHER,OTHER])
        clone.query("INSERT INTO public.profiles(id,email,role,status) VALUES(%s,'synthetic-http@example.test','admin','approved')",[OTHER])
        clone.query("UPDATE private.acquisition_activation SET enabled=true,approval_ref='synthetic local HTTP test',application_revision=repeat('a',40),verified_at=now()")
        for user,workspace in ((ADMIN,WORKSPACE),(OTHER,WORKSPACE_B)):
            clone.query('SET ROLE authenticated')
            clone.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps({'sub':user,'session_id':user,'aal':'aal2','role':'authenticated'})])
            clone.query('SELECT public.create_acquisition_workspace(%s,%s)',[workspace,'Synthetic HTTP workspace'])
            clone.query('RESET ROLE')
        secret=secrets.token_urlsafe(48)
        sock=folder/'http.sock'
        config=folder/'postgrest.conf'
        config.write_text('\n'.join([
            'db-uri = '+json.dumps('host='+str(folder)+' dbname=acquisition_http user=acquisition_http_authenticator'),
            'db-schemas = "public"','db-anon-role = "anon"','db-config = false','db-pool = 2',
            'jwt-secret = '+json.dumps(secret),'server-unix-socket = '+json.dumps(str(sock)),
            'server-unix-socket-mode = "600"','db-channel-enabled = false']))
        config.chmod(0o600)
        def token(user=ADMIN, key=secret, expiry=None):
            def part(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=')
            body=part({'alg':'HS256','typ':'JWT'})+b'.'+part({'sub':user,'session_id':user,'aal':'aal2','role':'authenticated','exp':expiry or int(time.time())+300})
            return (body+b'.'+base64.urlsafe_b64encode(hmac.new(key.encode(),body,hashlib.sha256).digest()).rstrip(b'=')).decode()
        def request(path, jwt=None, payload=None):
            if not path.startswith('/') or '://' in path:raise ValueError('Local API path required')
            args=['/usr/bin/curl','--silent','--show-error','--max-time','5','--noproxy','*','--unix-socket',str(sock),'-w','\n%{http_code}']
            if jwt:args+=['-H','Authorization: Bearer '+jwt]
            if payload is not None:args+=['-H','Content-Type: application/json','--data-binary','@-']
            result=subprocess.run(args+['http://localhost'+path],input=json.dumps(payload) if payload is not None else None,env=env,text=True,capture_output=True,timeout=8)
            if result.returncode:raise RuntimeError('Local PostgREST request failed')
            body,status=result.stdout.rsplit('\n',1)
            return int(status),json.loads(body)
        with (folder/'postgrest.log').open('w') as log:
            process=subprocess.Popen([str(binary),str(config)],env=env,stdout=log,stderr=log)
            deadline=time.monotonic()+15
            while True:
                if process.poll() is not None:raise RuntimeError('PostgREST stopped: '+(folder/'postgrest.log').read_text()[-1500:])
                if sock.exists():
                    try:
                        if request('/workspaces?select=id',token())[0]==200:break
                    except RuntimeError:pass
                if time.monotonic()>deadline:raise RuntimeError('PostgREST readiness timed out')
                time.sleep(.1)
            for user,workspace in ((ADMIN,WORKSPACE),(OTHER,WORKSPACE_B)):
                if request('/workspaces?select=id',token(user))!=(200,[{'id':workspace}]):
                    raise AssertionError('Signed user workspace isolation failed')
            for jwt in (token(key='wrong-synthetic-signing-key-of-sufficient-length'),token(expiry=int(time.time())-60)):
                if request('/workspaces?select=id',jwt)[0]!=401:raise AssertionError('Invalid JWT accepted')
            if request('/workspaces?select=id')[0]!=401:raise AssertionError('Anonymous workspace access accepted')
            from acquisition_postal_http import verify_postal_http
            postal_checks=verify_postal_http(clone,request,token,str(folder),ADMIN,OTHER,WORKSPACE)
            clone.query('DELETE FROM auth.sessions WHERE id=%s',[ADMIN])
            if request('/workspaces?select=id',token())!=(200,[]):raise AssertionError('Revoked session retains access')
            if request('/rpc/acquisition_offer_review_queue?p_workspace='+WORKSPACE,token())[0]!=403:
                raise AssertionError('Revoked session RPC accepted')
        return {'real_postgrest':'passed','version':version,'checks':['signed tenant isolation','wrong signature rejected','expired JWT rejected','anonymous denied','deleted session hidden','revoked RPC denied']+postal_checks,'hosted_auth_verified':False}
    finally:
        if process:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if clone:clone.connection.close()
        with control.cursor() as cursor:
            cursor.execute('DROP DATABASE IF EXISTS acquisition_http')
            cursor.execute('DROP ROLE IF EXISTS acquisition_http_authenticator')
        control.close()
        db.connection=psycopg2.connect(host=str(folder),dbname='acquisition_upgrade',user='test_admin')
        db.connection.autocommit=True
