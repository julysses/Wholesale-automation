import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function fixture(t){
 const f=await setup(t);
 for(const file of ['20261012232054_list_scoring_jobs.sql','20261012235046_list_scoring_inspection.sql'])await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await f.db.exec(`INSERT INTO public.profiles VALUES('${id(10)}','admin','approved'),('${id(11)}','user','approved'),('${id(12)}','admin','pending')`);
 await rpc(f.db,'prepare_list_score_job',[id(5),id(1),'claude-fixture']);
 return f;
}
const inspect=(db,actor=id(10),job=id(5))=>rpc(db,'inspect_list_scoring_job',[actor,job]);
test('inspection preserves submitted hold and hides claim credentials while comparing freshness',async t=>{
 const {db}=await fixture(t);const claim=await rpc(db,'claim_list_score_job',[id(5)]);
 let evidence=await inspect(db);assert.equal(evidence.job.state,'submitted');assert.equal(evidence.freshness.current,true);assert.deepEqual(evidence.freshness.changed_sections,[]);
 assert.equal(evidence.job.claim_token,undefined);assert.ok(!JSON.stringify(evidence).includes(claim.job.claim_token));assert.equal(evidence.outreach_authorized,false);
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=69');
 evidence=await inspect(db);assert.equal(evidence.freshness.current,false);assert.deepEqual(evidence.freshness.changed_sections,['score_threshold']);
 assert.equal(evidence.job.input_snapshot.score_threshold,70);
 assert.equal((await rpc(db,'claim_list_score_job',[id(5)])).dispatch,false);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.scoring_jobs')).rows[0].n,1);
});
test('inspection retains rejected response, validation reason and unavailable source state',async t=>{
 const {db,result}=await fixture(t);const claim=await rpc(db,'claim_list_score_job',[id(5)]);
 result.components.equity.points=1;
 await rpc(db,'receive_list_score_job',[id(5),claim.job.claim_token,'claude-fixture','msg-rejected',JSON.stringify(result)]);
 await rpc(db,'complete_list_score_job',[id(5)]);
 let evidence=await inspect(db);assert.equal(evidence.job.state,'review');assert.equal(evidence.job.error_code,'equity_unknown');assert.deepEqual(evidence.job.assessment,result);assert.equal(evidence.evaluation,null);
 await db.exec('UPDATE wholesale_ingest.distress_signals SET active=false');
 evidence=await inspect(db);assert.equal(evidence.freshness.current,false);assert.equal(evidence.freshness.blocked,'no_active_signals');assert.equal(evidence.job.state,'review');
});
test('completed jobs remain inspectable; missing job and privilege failures are distinct',async t=>{
 const {db,result}=await fixture(t);const claim=await rpc(db,'claim_list_score_job',[id(5)]);
 await rpc(db,'receive_list_score_job',[id(5),claim.job.claim_token,'claude-fixture','msg-good',JSON.stringify(result)]);
 await rpc(db,'complete_list_score_job',[id(5)]);
 assert.equal((await inspect(db)).evaluation.score,32);
 assert.equal((await inspect(db,id(10),id(99))).blocked,'job_missing');
 for(const actor of [id(11),id(12)])await assert.rejects(inspect(db,actor),/administrator/);
 for(const role of ['anon','authenticated']){await db.exec('SET ROLE '+role);await assert.rejects(inspect(db),/permission denied/);await db.exec('RESET ROLE');}
});
