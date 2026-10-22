"""Rehearse the allowlisted integration upgrade and protected intake journeys locally."""
import os
import re
import sys
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
if sys.argv[1:] not in ([], ['--schema-security'], ['--buyer-sms'], ['--buyer-enrollment'], ['--buyer-manual'], ['--buyer-analysis'], ['--buyer-mutations']):
    raise SystemExit('Unknown local rehearsal mode')
pg=Path(os.environ.get('PG_BIN','/opt/homebrew/opt/postgresql@17/bin'))
node=shutil.which('node')
if not node or not all((pg/x).is_file() for x in ('initdb','pg_ctl','createdb','postgres')):
    raise SystemExit('Node and PostgreSQL binaries are required')
version=subprocess.check_output([pg/'postgres','--version'],text=True).strip()
major=re.search(r'\(PostgreSQL\) (\d+)',version)
if not major or int(major[1])<17:
    raise SystemExit('Saved production catalog requires PostgreSQL 17 or newer; got '+version)
print('Disposable production-catalog runtime: '+version,flush=True)
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
        run([root/'.venv/bin/python','pipeline/integration/verify_production_schema_drift.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_authorization.py'],cwd=root,env=env,timeout=90)
        if sys.argv[1:] == ['--schema-security']:
            raise SystemExit(0)
        run([root/'.venv/bin/python','pipeline/integration/rehearse_full_upgrade.py'],cwd=root,env=env,timeout=90)
        if sys.argv[1:] == ['--buyer-mutations']:
            run([root/'.venv/bin/python','pipeline/integration/verify_buyer_mutations.py'],cwd=root,env=env,timeout=90)
            raise SystemExit(0)
        if sys.argv[1:] == ['--buyer-analysis']:
            run([root/'.venv/bin/python','pipeline/integration/verify_buyer_analysis.py'],cwd=root,env=env,timeout=90)
            raise SystemExit(0)
        if sys.argv[1:] == ['--buyer-manual']:
            run([root/'.venv/bin/python','pipeline/integration/verify_buyer_manual.py'],cwd=root,env=env,timeout=90)
            raise SystemExit(0)
        if sys.argv[1:] == ['--buyer-enrollment']:
            run([root/'.venv/bin/python','pipeline/integration/verify_buyer_enrollment.py'],cwd=root,env=env,timeout=90)
            raise SystemExit(0)
        if sys.argv[1:] == ['--buyer-sms']:
            run([root/'.venv/bin/python','pipeline/integration/verify_buyer_sms.py'],cwd=root,env=env,timeout=90)
            raise SystemExit(0)
        run([root/'.venv/bin/python','pipeline/integration/verify_land_import.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_csv_import.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_csv_scoring.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_import.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_outreach.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_sms_consent.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_sms.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_enrollment.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_manual.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_analysis.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_mutations.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_buyer_reads.py'],cwd=root,env=env,timeout=90)
        run([root/'.venv/bin/python','pipeline/integration/verify_versioned_call_concurrency.py'],cwd=root,env=env,timeout=90)
        env['PYTHONPATH']=str(root/'scripts/offline-tests')+os.pathsep+str(root)
        run([root/'.venv/bin/python','-m','pytest','tests/test_local_lead_journeys.py','-v'],cwd=root,env=env,timeout=300)
    finally:
        if started:run([pg/'pg_ctl','-D',data,'-m','immediate','-w','stop'],stdout=subprocess.DEVNULL)
