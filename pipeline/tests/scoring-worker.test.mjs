import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function fixture(t){
 const f=await setup(t);
 for(const file of ['20261012232054_list_scoring_jobs.sql','20261012234031_list_scoring_worker.sql'])await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 return f;
}
const next=(db,n=5)=>rpc(db,'next_list_scoring_jobs',['claude-fixture',n]);
test('selection creates durable jobs once and excludes unknown outcomes and current scores',async t=>{
 const {db,result}=await fixture(t);
 const initial=await next(db);assert.equal(initial.jobs.length,1);const job=initial.jobs[0];
 assert.equal((await next(db)).jobs[0].id,job.id);
 const claimed=await rpc(db,'claim_list_score_job',[job.id]);assert.equal((await next(db)).jobs.length,0);
 await rpc(db,'receive_list_score_job',[job.id,claimed.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 assert.equal((await next(db,1)).jobs[0].state,'received');
 await rpc(db,'complete_list_score_job',[job.id]);assert.equal((await next(db)).jobs.length,0);
});
test('obsolete unsubmitted attempt does not permanently block identical current evidence',async t=>{
 const {db}=await fixture(t);const first=(await next(db)).jobs[0];
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=69');
 assert.equal((await rpc(db,'claim_list_score_job',[first.id])).job.state,'obsolete');
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=70');
 const second=(await next(db)).jobs[0];assert.notEqual(second.id,first.id);
 assert.equal((await rpc(db,'claim_list_score_job',[first.id])).dispatch,false);
 assert.equal((await rpc(db,'claim_list_score_job',[second.id])).dispatch,true);
});
test('received job from prior model is selected first and no candidate exceeds the batch limit',async t=>{
 const {db,result}=await fixture(t);const first=(await next(db)).jobs[0];
 const claimed=await rpc(db,'claim_list_score_job',[first.id]);
 await rpc(db,'receive_list_score_job',[first.id,claimed.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 await db.exec(`INSERT INTO public.leads(id,property_address) VALUES('${id(7)}','SECOND SYNTHETIC');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,lead_id) VALUES('${id(8)}','TX','Dallas','SECOND SYNTHETIC','${id(7)}');
 INSERT INTO wholesale_ingest.distress_signals(property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
 SELECT '${id(8)}',source_id,'second-property',list_type,filed_date,source_url,first_run_id,last_run_id FROM wholesale_ingest.distress_signals WHERE id='${id(4)}'`);
 const limited=await rpc(db,'next_list_scoring_jobs',['new-model',1]);assert.equal(limited.jobs.length,1);assert.equal(limited.jobs[0].id,first.id);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.scoring_jobs')).rows[0].n,1);
 for(const n of [0,11])await assert.rejects(next(db,n),/configuration/);
 await db.exec('SET ROLE authenticated');await assert.rejects(next(db),/permission denied/);
});
