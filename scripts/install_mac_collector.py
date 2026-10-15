"""Install the rehearsal tax worker as a per-user macOS login service.
Copies a scoped runtime to Application Support; never changes power settings,
Keychain ACLs, browser sessions, provider plans or production configuration.
"""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
base = Path.home() / 'Library/Application Support/WholesaleOS/rehearsal-worker'
runtime = base / 'runtime'
state = base / 'state'
label = 'com.wholesaleos.rehearsal.collector'
plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
node = shutil.which('node')
if sys.platform != 'darwin' or not node:
    raise SystemExit('macOS and an existing Node installation are required')
files = ['pipeline/collectors/' + name for name in (
    'persistent_worker.py','fetch_tax_roll.py','tax_roll.py','deliver_keychain.py','deliver.mjs','preflight.mjs')]
files += ['frontend/supabase/functions/daily-list-ingest/' + name for name in (
    'core.mjs','coverage.mjs','collector-policy.mjs','ingest.schema.json')]
packages = ('ajv','ajv-formats','fast-deep-equal','fast-uri','json-schema-traverse','require-from-string')
for relative in files:
    if not (repo / relative).is_file():
        raise SystemExit('Required worker source missing')
for package in packages:
    if not (repo / 'pipeline/node_modules' / package).is_dir():
        raise SystemExit('Install pipeline dependencies before deployment')
# Stop only this specifically named service before updating its runtime.
subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
os.umask(0o077)
state.mkdir(parents=True,exist_ok=True,mode=0o700)
for relative in files:
    target = runtime / relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo / relative,target)
for package in packages:
    shutil.copytree(repo / 'pipeline/node_modules' / package,
                    runtime / 'pipeline/node_modules' / package,dirs_exist_ok=True)
receipt = {relative:hashlib.sha256((runtime/relative).read_bytes()).hexdigest() for relative in files}
(base/'installed-source-hashes.json').write_text(json.dumps(receipt,indent=2))
config = {'Label':label,'ProgramArguments':['/usr/bin/python3',str(runtime/'pipeline/collectors/persistent_worker.py'),'--state',str(state)],
          'WorkingDirectory':str(runtime),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':60,'Umask':63,
          'EnvironmentVariables':{'PATH':str(Path(node).parent)+':/usr/bin:/bin:/usr/sbin:/sbin','PYTHONUNBUFFERED':'1'},
          'StandardOutPath':str(state/'worker.log'),'StandardErrorPath':str(state/'worker-error.log')}
plist.parent.mkdir(parents=True,exist_ok=True)
plist.write_bytes(plistlib.dumps(config));plist.chmod(0o600)
subprocess.run(['plutil','-lint',str(plist)],check=True)
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
print(json.dumps({'installed':True,'label':label,'state':str(state),'project':'tbhwxgfzbiaqjurghntj','scope':'tax_collection_delivery_only'}))
