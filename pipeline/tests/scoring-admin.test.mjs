import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function fixture(t){
 const f=await setup(t);
 for(const file of ['20261012232054_list_scoring_jobs.sql','20261012232711_list_scoring_monitor.sql','20261012233212_list_scoring_admin.sql'])await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await f.db.exec(`INSERT INTO public.profiles VALUES('${id(10)}','admin','approved'),('${id(11)}','user','approved')`);
 return f;
}
const act=(db,event,action,payload,actor=id(10))=>rpc(db,'apply_list_scoring_operation',[event,actor,action,JSON.stringify(payload)]);
test('threshold edits audit exact retries and reject stale versions without reverting later changes',async t=>{
 const {db}=await fixture(t);
 const first={expected_version:1,score_threshold:65};
 assert.equal((await act(db,id(20),'threshold',first)).event.result.version,2);
 assert.equal((await act(db,id(21),'threshold',first)).blocked,'version_conflict');
 await act(db,id(22),'threshold',{expected_version:2,score_threshold:80});
 assert.equal((await act(db,id(20),'threshold',first)).replayed,true);
 const snapshot=await rpc(db,'list_scoring_operations',[id(10),0]);assert.equal(snapshot.settings.score_threshold,80);assert.equal(snapshot.settings.version,3);assert.equal(snapshot.recent_actions.length,2);
 assert.equal((await act(db,id(20),'threshold',{...first,score_threshold:60})).blocked,'reference_conflict');
 await db.exec('SET ROLE service_role');await assert.rejects(db.exec('DELETE FROM wholesale_ingest.scoring_operator_events'),/permission denied/);
});
test('operator can complete a saved response but cannot trigger an uncertain model request',async t=>{
 const {db,result}=await fixture(t);
 await rpc(db,'prepare_list_score_job',[id(5),id(1),'claude-fixture']);const claimed=await rpc(db,'claim_list_score_job',[id(5)]);
 assert.equal((await act(db,id(20),'complete_received',{job_id:id(5)})).blocked,'saved_response_required');
 await rpc(db,'receive_list_score_job',[id(5),claimed.job.claim_token,'claude-fixture','msg-fixture',JSON.stringify(result)]);
 const action=await act(db,id(21),'complete_received',{job_id:id(5)});assert.equal(action.event.result.state,'completed');assert.equal(action.event.result.evaluation_id,id(5));
 assert.equal((await act(db,id(21),'complete_received',{job_id:id(5)})).replayed,true);
 assert.equal((await rpc(db,'list_scoring_operations',[id(10),0])).open_count,0);
});
test('unauthorized actors, browser roles and malformed thresholds cannot change settings',async t=>{
 const {db}=await fixture(t);
 await assert.rejects(act(db,id(20),'threshold',{expected_version:1,score_threshold:50},id(11)),/administrator/);
 for(const value of [101,-1,true,'70'])assert.ok((await act(db,id(20),'threshold',{expected_version:1,score_threshold:value})).blocked);
 for(const role of ['anon','authenticated']){await db.exec('SET ROLE '+role);await assert.rejects(act(db,id(20),'threshold',{expected_version:1,score_threshold:50}),/permission denied/);await db.exec('RESET ROLE');}
 assert.equal((await rpc(db,'list_scoring_operations',[id(10),0])).settings.version,1);
});
