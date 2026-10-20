"""Non-sending deployment probes: public configuration and rejected inputs only.

No valid inquiry, provider call, worker invocation or schedule execution is sent.
Uses Vercel's existing CLI authentication for a specifically named deployment.
"""
import argparse
import json
import subprocess
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--deployment',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
if not args.deployment.startswith(('wholesale-automation-', 'https://wholesale-automation-')) and args.deployment!='wholesale-automation.vercel.app':
    raise SystemExit('Only the reviewed WholesaleOS deployment may be probed')
checks=[]
def probe(path,expected,body=None):
    cmd=['vercel','curl',path,'--deployment',args.deployment,'--scope','team_XZeRcNxzGjDXsr7Z2AqwhfAe','--','--silent','--show-error','--max-time','45','--write-out','\n%{http_code}']
    if body is not None:cmd+=['--request','POST','--header','Content-Type: application/json','--data',json.dumps(body)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=75)
    if result.returncode:raise RuntimeError('Deployment probe failed: '+path+'; CLI exit '+str(result.returncode))
    content,status=result.stdout.rsplit('\n',1)
    status=int(status.strip())
    row={'path':path,'method':'POST' if body is not None else 'GET','status':status,'expected':expected}
    try:data=json.loads(content)
    except ValueError:data=None
    if isinstance(data,dict):
        if 'questions' in data:row.update(slug=data.get('slug'),question_count=len(data['questions']),required_fields=[q.get('field_name') for q in data['questions'] if q.get('required')])
        else:row['response']=data
    else:row['html']=bool('<html' in content.lower())
    checks.append(row)
    Path(args.output).write_text(json.dumps({'deployment':args.deployment,'scope':'configuration_and_rejection_only','valid_submissions':0,'checks':checks},indent=2)+'\n')
    print(json.dumps(row),flush=True)
    assert status==expected,(path,status)
    return data
probe('/api/readiness',200)
for slug in ['hilltop-home-co','the-jays-dallas']:
    form=probe('/api/forms/'+slug,200)
    assert form and form.get('slug')==slug and form.get('questions')
    probe('/form/'+slug,200)
    probe('/api/forms/'+slug+'/submit',422,{'answers':{}})
probe('/webhooks/facebook/lead?hub.mode=subscribe&hub.verify_token=invalid-release-probe&hub.challenge=paused-release',403)
probe('/webhooks/facebook/lead',403,{'entry':[]})
print('Paused intake probes passed. Native Meta retrieval and valid production submissions were not exercised.',flush=True)
