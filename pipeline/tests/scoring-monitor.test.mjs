import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function fixture(t){
 const f=await setup(t);
 for(const file of ['20261012232054_list_scoring_jobs.sql','20261012232711_list_scoring_monitor.sql'])await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await rpc(f.db,'prepare_list_score_job',[id(5),id(1),'claude-fixture']);
 return f;
}
const scan=async(db,stamp)=>(await db.query('select wholesale_ingest.scan_scoring_at($1) v',[stamp])).rows[0].v;
const count=async db=>(await db.query('select count(*)::int n from public.tasks')).rows[0].n;
async function owner(db){await db.exec(`INSERT INTO public.profiles VALUES('${id(9)}','admin','approved');INSERT INTO public.app_settings VALUES('lead_owner_user_id','${id(9)}')`);}
test('inclusive submitted deadline creates one task and never resets uncertain claim',async t=>{
 const {db,result}=await fixture(t);await owner(db);
 const claimed=await rpc(db,'claim_list_score_job',[id(5)]);
 const due=new Date(new Date(claimed.job.claimed_at).getTime()+15*60*1000);
 assert.equal((await scan(db,new Date(due.getTime()-1).toISOString())).open_incidents.length,0);
 const first=await scan(db,due.toISOString());assert.equal(first.open_incidents[0].kind,'model_outcome_unknown');assert.equal(await count(db),1);
 await scan(db,due.toISOString());assert.equal(await count(db),1);
 assert.equal((await rpc(db,'claim_list_score_job',[id(5)])).dispatch,false);
 await rpc(db,'receive_list_score_job',[id(5),claimed.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 await rpc(db,'complete_list_score_job',[id(5)]);
 assert.equal((await scan(db,due.toISOString())).open_incidents.length,0);
 assert.equal((await db.query('select status from public.tasks')).rows[0].status,'pending');
});
test('missing owner retains incident and creates task after owner is configured',async t=>{
 const {db}=await fixture(t);
 const job=(await rpc(db,'prepare_list_score_job',[id(5),id(1),'claude-fixture'])).job;
 const due=new Date(new Date(job.created_at).getTime()+60*60*1000).toISOString();
 let status=await scan(db,due);assert.equal(status.owner_configured,false);assert.equal(status.open_incidents[0].kind,'scoring_queue_overdue');assert.equal(await count(db),0);
 await owner(db);status=await scan(db,due);assert.equal(status.owner_configured,true);assert.equal(await count(db),1);
});
test('saved response awaiting completion alerts without another model call',async t=>{
 const {db,result}=await fixture(t);await owner(db);
 const claimed=await rpc(db,'claim_list_score_job',[id(5)]);
 const saved=await rpc(db,'receive_list_score_job',[id(5),claimed.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 const due=new Date(new Date(saved.job.received_at).getTime()+15*60*1000).toISOString();
 assert.equal((await scan(db,due)).open_incidents[0].kind,'receipt_completion_overdue');
 assert.equal((await rpc(db,'claim_list_score_job',[id(5)])).dispatch,false);
 await db.exec('SET ROLE authenticated');await assert.rejects(scan(db,due),/permission denied/);
});
