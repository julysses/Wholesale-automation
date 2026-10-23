import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function jobs(t){
 const fixture=await setup(t);
 await fixture.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012232054_list_scoring_jobs.sql',import.meta.url),'utf8'));
 return fixture;
}
const prepare=db=>rpc(db,'prepare_list_score_job',[id(5),id(1),'claude-fixture']);
const claim=db=>rpc(db,'claim_list_score_job',[id(5)]);
const complete=db=>rpc(db,'complete_list_score_job',[id(5)]);
test('job claims once and durable receipt resumes evaluation without another dispatch',async t=>{
 const {db,result}=await jobs(t);
 assert.equal((await prepare(db)).replayed,false);assert.equal((await prepare(db)).replayed,true);
 const active=await claim(db);assert.equal(active.dispatch,true);assert.equal((await claim(db)).dispatch,false);
 const args=[id(5),active.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)];
 assert.equal((await rpc(db,'receive_list_score_job',args)).job.state,'received');
 assert.equal((await prepare(db)).job.state,'received');
 assert.equal((await rpc(db,'receive_list_score_job',args)).replayed,true);
 const finished=await complete(db);assert.equal(finished.job.state,'completed');assert.equal(finished.evaluation.score,32);
 assert.equal((await complete(db)).replayed,true);assert.equal((await claim(db)).dispatch,false);
 assert.equal((await rpc(db,'prepare_list_score_job',[id(9),id(1),'claude-fixture'])).blocked,'existing_job');
});
test('stale queued job becomes obsolete without dispatch; stale received evidence is retained',async t=>{
 const {db,result}=await jobs(t);await prepare(db);
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=69');
 const stale=await claim(db);assert.equal(stale.dispatch,false);assert.equal(stale.job.state,'obsolete');assert.equal(stale.job.claim_token,null);
 await rpc(db,'prepare_list_score_job',[id(6),id(1),'claude-fixture']);
 const active=await rpc(db,'claim_list_score_job',[id(6)]);
 await rpc(db,'receive_list_score_job',[id(6),active.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=68');
 const finished=await rpc(db,'complete_list_score_job',[id(6)]);assert.equal(finished.blocked,'stale_input');assert.equal(finished.job.state,'obsolete');assert.deepEqual(finished.job.assessment,result);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.lead_evaluations')).rows[0].n,0);
});
test('unknown dispatch cannot be reclaimed, retargeted or replaced with another job',async t=>{
 const {db,result}=await jobs(t);await prepare(db);const active=await claim(db);
 assert.equal((await rpc(db,'prepare_list_score_job',[id(9),id(1),'other-model'])).blocked,'existing_job');
 assert.equal((await rpc(db,'receive_list_score_job',[id(5),id(99),'claude-fixture','msg-fixture',JSON.stringify(result)])).blocked,'receipt_identity_mismatch');
 await assert.rejects(db.exec(`UPDATE wholesale_ingest.scoring_jobs SET state='queued' WHERE id='${id(5)}'`),/transition/);
 await assert.rejects(db.exec(`UPDATE wholesale_ingest.scoring_jobs SET requested_model='other' WHERE id='${id(5)}'`),/immutable/);
 const args=[id(5),active.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)];await rpc(db,'receive_list_score_job',args);
 args[3]='different';assert.equal((await rpc(db,'receive_list_score_job',args)).blocked,'receipt_conflict');
 for(const role of ['anon','authenticated']){await db.exec('SET ROLE '+role);await assert.rejects(complete(db),/permission denied/);await db.exec('RESET ROLE');}
});
