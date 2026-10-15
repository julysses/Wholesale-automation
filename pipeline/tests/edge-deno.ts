import {handler} from '../../frontend/supabase/functions/daily-list-ingest/index.ts';
import {sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
import coverageData from '../fixtures/synthetic-coverage.json' with {type:'json'};
import fixtureData from '../fixtures/synthetic.json' with {type:'json'};
Deno.test('real handler rejects unauthorized and invalid requests before database access',async()=>{
 const fixture={...fixtureData,pulled_at:new Date().toISOString()};
 const token='synthetic-test-token-not-a-real-secret-12345';
 Deno.env.set('INGEST_DATABASE_URL','postgresql://invalid:invalid@localhost:1/invalid');
 const set=(scope:string[],expires='2099-01-01T00:00:00Z')=>Deno.env.set('INGEST_TOKEN_CONFIG',JSON.stringify({test:{sha256:hash,source_keys:scope,expires_at:expires}}));
 const hash=await sha256(token);set([fixture.source_key]);
 const call=(body:unknown,auth=true,method='POST',contentType='application/json')=>handler(new Request('https://ingest.invalid',{method,headers:{'Content-Type':contentType,'X-Ingest-Key-Id':'test',...(auth?{Authorization:'Bearer '+token}:{})},...(method==='POST'?{body:typeof body==='string'?body:JSON.stringify(body)}:{})}));
 const expect=async(p:Promise<Response>,status:number)=>{const r=await p;if(r.status!==status)throw new Error(`Expected ${status}, got ${r.status}: ${await r.text()}`);};
 // Coverage errors must be rejected before any connection to the intentionally invalid DB.
 const evidenceRejected=async(body:unknown)=>{const r=await call(body);const b=await r.json();if(r.status!==422||b.error!=='collector_evidence_invalid')throw new Error('Expected collector evidence rejection');};
 await evidenceRejected(fixture);
 await evidenceRejected({...fixture,coverage:{}});
 const changed=structuredClone(coverageData);changed.scans[1].pages[0].documents[0].document_id='changed-index';
 await evidenceRejected({...fixture,coverage:changed});
 await evidenceRejected({...fixture,coverage:{...coverageData,run_id:crypto.randomUUID()}});
 await evidenceRejected({...fixture,coverage:coverageData,batch_count:2});
 await evidenceRejected({...fixture,status:'partial',coverage_complete:false,status_reason:'partial',coverage:coverageData});
 set(['tx-dallas-probate']);
 await evidenceRejected({...fixture,status:'partial',coverage_complete:false,status_reason:'partial',source_key:'tx-dallas-probate',source:{...fixture.source,list_type:'probate'}});
 set([fixture.source_key]);
 await expect(call(fixture,false),401);
 await expect(call(null,true,'GET'),405);
 await expect(call('{}',true,'POST','text/plain'),415);
 await expect(call('{broken'),400);
 await expect(call({...fixture,status:'INVALID'}),422);
 await expect(call({...fixture,records_sha256:'f'.repeat(64)}),422);
 await expect(call('x'.repeat(2*1024*1024+1)),413);
 set(['tx-collin-probate']);await expect(call(fixture),403);
 set([fixture.source_key],'2020-01-01T00:00:00Z');await expect(call(fixture),401);
 Deno.env.delete('INGEST_DATABASE_URL');Deno.env.delete('INGEST_TOKEN_CONFIG');
});


Deno.test('retired outreach writer returns no generated text or provider activity', async () => {
  const {handler: retired} = await import('../../frontend/supabase/functions/write-outreach/index.ts');
  const response = retired();
  if (response.status !== 410) throw new Error('Legacy writer must stay retired');
  const body = await response.json();
  if (body.error !== 'outreach_writer_retired' || 'body' in body) throw new Error('Unexpected legacy draft');
});
