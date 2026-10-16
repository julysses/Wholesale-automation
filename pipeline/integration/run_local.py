"""Start/stop a disposable localhost PostgreSQL cluster for real ingress acceptance."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
pg = Path(os.environ.get('PG_BIN', '/opt/homebrew/opt/postgresql@17/bin'))
deno = os.environ.get('DENO_BIN') or shutil.which('deno')
if not deno:
    raise SystemExit('Set DENO_BIN to the installed Deno executable')
for executable in ('initdb', 'pg_ctl', 'createdb'):
    if not (pg / executable).is_file():
        raise SystemExit('Set PG_BIN to the PostgreSQL binary directory')
with tempfile.TemporaryDirectory(prefix='wholesale-ingress-') as folder:
    path = Path(folder)
    data = path / 'data'
    password = path / 'password'
    password.write_text('local-only-test-admin')
    password.chmod(0o600)
    def run(args, **kwargs):
        return subprocess.run([str(arg) for arg in args], check=True, **kwargs)
    run([pg/'initdb', '-D', data, '-U', 'test_admin', '--pwfile', password,
         '--auth-host=scram-sha-256', '--auth-local=trust', '--no-locale'], stdout=subprocess.DEVNULL)
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
         '-subj', '/CN=localhost', '-keyout', data/'server.key', '-out', data/'server.crt'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (data/'server.key').chmod(0o600)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with (data/'postgresql.conf').open('a') as config:
        config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nssl=on\nunix_socket_directories='{folder}'\n")
    started = False
    try:
        run([pg/'pg_ctl', '-D', data, '-l', path/'server.log', '-w', 'start'], stdout=subprocess.DEVNULL)
        started = True
        env = {**os.environ, 'PGPASSWORD':'local-only-test-admin'}
        run([pg/'createdb', '-h', '127.0.0.1', '-p', port, '-U', 'test_admin', 'wholesale_ingress_test'], env=env)
        env['INGRESS_TEST_ADMIN_URL'] = f'postgresql://test_admin:local-only-test-admin@127.0.0.1:{port}/wholesale_ingress_test'
        run([deno, 'run', '--check', '--lock=pipeline/integration/deno.lock', '--frozen', '--node-modules-dir=none',
             '--allow-env', '--allow-read', '--allow-net=127.0.0.1', 'pipeline/integration/ingress-postgres.ts'], cwd=root, env=env, timeout=180)
    finally:
        if started:
            run([pg/'pg_ctl', '-D', data, '-m', 'immediate', '-w', 'stop'], stdout=subprocess.DEVNULL)
