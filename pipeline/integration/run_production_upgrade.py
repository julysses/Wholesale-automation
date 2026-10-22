"""Rehearse the allowlisted integration upgrade and protected intake journeys locally."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
pg=Path(os.environ.get('PG_BIN','/opt/homebrew/opt/postgresql@17/bin'))
node=shutil.which('node')
if not node or not all((pg/x).is_file() for x in ('initdb','pg_ctl','createdb')):
    raise SystemExit('Node and PostgreSQL binaries are required')
with tempfile.TemporaryDirectory(prefix='wholesale-sms-') as folder:
    path=Path(folder);data=path/'data';password=path/'password'
    password.write_text('local-only-test-admin');password.chmod(0o600)
    def run(args,**kwargs):return subprocess.run([str(x) for x in args],check=True,**kwargs)
    run([pg/'initdb','-D',data,'-U','test_admin','--pwfile',password,'--auth-host=scram-sha-256','--auth-local=trust','--no-locale','--encoding=UTF8'],stdout=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (data/'postgresql.conf').open('a') as config:
        config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories='{folder}'\n")
    started=False
    try:
        run([pg/'pg_ctl','-D',data,'-l',path/'server.log','-w','start'],stdout=subprocess.DEVNULL);started=True
        env={**os.environ,'PGPASSWORD':'local-only-test-admin'}
        run([pg/'createdb','-h','127.0.0.1','-p',port,'-U','test_admin','wholesale_sms_test'],env=env)
        env['SMS_TEST_ADMIN_URL']=f'postgresql://test_admin:local-only-test-admin@127.0.0.1:{port}/wholesale_sms_test'
        run([root/'.venv/bin/python','pipeline/integration/production_schema.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/rehearse_facebook_migration.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/rehearse_full_upgrade.py'],cwd=root,env=env,timeout=90)
        env['PYTHONPATH']=str(root/'scripts/offline-tests')+os.pathsep+str(root)
        run([root/'.venv/bin/python','-m','pytest','tests/test_local_lead_journeys.py','-v'],cwd=root,env=env,timeout=300)
    finally:
        if started:run([pg/'pg_ctl','-D',data,'-m','immediate','-w','stop'],stdout=subprocess.DEVNULL)
