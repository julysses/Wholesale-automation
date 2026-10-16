import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {deliver,sendBatch,validateBatches} from '../collectors/deliver.mjs';
import {sha256,canonicalJSON} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
const make=()=>{const p=JSON.parse(fs.readFileSync(new URL('../fixtures/synthetic.json',import.meta.url)));p.status='partial';p.status_reason='Synthetic incomplete review';p.coverage_complete=false;return p;};
const options={endpoint:'https://tbhwxgfzbiaqjurghntj.supabase.co/functions/v1/daily-list-ingest',keyId:'synthetic',token:'synthetic-not-real-token-12345678901234567890'};
const response=(p,status=202,change={})=>new Response(JSON.stringify({run_id:p.run_id,batch_index:p.batch_index??0,state:'accepted',replayed:status===200,records_received:p.records.length,...change}),{status});
test('exact receipt and replay are recognized without claiming CRM lead creation',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'collector-test-'));t.after(()=>fs.rmSync(dir,{recursive:true}));const p=make();let tries=0;
 const opts={...options,journalPath:path.join(dir,'receipt.json'),fetcher:async()=>response(p,tries++?200:202)};
 assert.equal((await deliver([p],opts)).crm_leads_verified,false);assert.equal((await deliver([p],opts)).accepted_batches,1);
 const saved=JSON.parse(fs.readFileSync(opts.journalPath));assert.equal(saved.accepted[0].replayed,true);assert.ok(!JSON.stringify(saved).includes(options.token));
});
test('lost response retains pending identity and retry uses same payload',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'collector-test-'));t.after(()=>fs.rmSync(dir,{recursive:true}));const p=make();const journalPath=path.join(dir,'receipt.json');
 await assert.rejects(deliver([p],{...options,journalPath,fetcher:async()=>{throw new Error('network');}}),/uncertain/);
 assert.equal(JSON.parse(fs.readFileSync(journalPath)).pending_batch,0);
 await deliver([p],{...options,journalPath,fetcher:async()=>response(p,200)});
 p.status_reason='changed';await assert.rejects(deliver([p],{...options,journalPath}),/different payloads/);
});
test('a receipt from another project or credential scope cannot authorize delivery',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'collector-test-'));t.after(()=>fs.rmSync(dir,{recursive:true}));
 const p=make(),journalPath=path.join(dir,'receipt.json');
 await deliver([p],{...options,journalPath,fetcher:async()=>response(p)});
 const original=fs.readFileSync(journalPath,'utf8');
 for(const override of [{endpoint:'https://dvzhzlipbwzzcliujzyz.supabase.co/functions/v1/daily-list-ingest'},{keyId:'another-source'}]){
  let dispatched=false;
  await assert.rejects(deliver([p],{...options,...override,journalPath,fetcher:async()=>{dispatched=true;return response(p);}}),/destination/);
  assert.equal(dispatched,false);assert.equal(fs.readFileSync(journalPath,'utf8'),original);
 }
 const legacy=JSON.parse(original);delete legacy.endpoint;fs.writeFileSync(journalPath,JSON.stringify(legacy));
 await assert.rejects(deliver([p],{...options,journalPath}),/destination/);
});
test('wrong identity, redirects and denial cannot become acceptance',async()=>{
 const p=make();
 for(const r of [response(p,202,{run_id:crypto.randomUUID()}),response(p,202,{records_received:2}),new Response('',{status:403}),new Response('',{status:302})])await assert.rejects(sendBatch(p,{...options,fetcher:async()=>r}));
 await assert.rejects(sendBatch(p,{...options,endpoint:'https://evil.invalid'}),/exact Supabase/);
});
test('batch gaps and cross-batch duplicates rejected before delivery',async()=>{
 const a=make();a.batch_index=0;a.batch_count=2;const b=structuredClone(a);b.batch_index=1;
 await assert.rejects(validateBatches([a]),/Incomplete/);
 await assert.rejects(validateBatches([a,b]),/Duplicate record/);
 b.records[0].source_record_id='SYNTHETIC-SECOND';b.records_sha256=await sha256(canonicalJSON(b.records));assert.equal((await validateBatches([b,a])).length,2);
 b.status_reason='different manifest';await assert.rejects(validateBatches([a,b]),/identity mismatch/);
});

test('complete delivery transmits and journals exact coverage; changed review cannot replay',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'collector-test-'));t.after(()=>fs.rmSync(dir,{recursive:true}));
 const p=JSON.parse(fs.readFileSync(new URL('../fixtures/synthetic.json',import.meta.url)));
 const coverage=JSON.parse(fs.readFileSync(new URL('../fixtures/synthetic-coverage.json',import.meta.url)));
 let wire; const journalPath=path.join(dir,'receipt.json');
 const opts={...options,journalPath,coverage,fetcher:async(_url,init)=>{wire=JSON.parse(init.body);return response(wire);}};
 await deliver([p],opts);assert.deepEqual(wire.coverage,coverage);
 assert.equal(JSON.parse(fs.readFileSync(journalPath)).accepted[0].payload_sha256,await sha256(canonicalJSON(wire)));
 coverage.reviews[0].note+=' Changed review';
 await assert.rejects(deliver([p],opts),/different payloads/);
});
