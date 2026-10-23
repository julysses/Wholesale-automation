"""Prepare public, read-only metadata for a credential-free local build only."""
import json
import os
from pathlib import Path

for key in ('VERCEL_TOKEN', 'SUPABASE_SERVICE_ROLE_KEY', 'TWILIO_AUTH_TOKEN',
            'SENDGRID_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
    assert not os.environ.get(key), f'Do not pass {key} to this build check'
directory = Path('.vercel')
directory.mkdir()  # Refuse to overwrite an existing link/environment.
settings = {
    'orgId': 'team_XZeRcNxzGjDXsr7Z2AqwhfAe',
    'projectId': 'prj_ZRURRXQ1GbBiIUBtmGFiYZdVMNgd',
    'projectName': 'wholesale-automation',
    'settings': {'framework': 'fastapi', 'nodeVersion': '24.x',
                 'createdAt': 1781546893959, 'rootDirectory': None,
                 'buildCommand': None, 'installCommand': None, 'outputDirectory': None},
}
(directory / 'project.json').write_text(json.dumps(settings) + '\n')
(directory / '.env.production.local').write_text('')
print('Build-only metadata ready; production environment was not retrieved')
