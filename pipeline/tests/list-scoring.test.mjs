import test from 'node:test';
import assert from 'node:assert/strict';
import {setup,id,rpc} from './scoring-fixture.mjs';
test('weighted score persists exact evidence and replays without another evaluation',async t=>{
 const {db,save}=await setup(t);let v=await save();assert.equal(v.evaluation.score,32);assert.equal(v.evaluation.stack_count,1);assert.equal(v.outreach_authorized,false);
 assert.equal(v.evaluation.route,'nurture');assert.ok(v.evaluation.flags.includes('equity_unknown'));
 assert.equal((await save()).replayed,true);
 assert.equal((await rpc(db,'scan_list_pipeline',[])).top_ten.length,1);
 await db.exec('UPDATE wholesale_ingest.settings SET score_threshold=65');
 assert.equal((await rpc(db,'scan_list_pipeline',[])).top_ten.length,0);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.lead_evaluations')).rows[0].n,1);
 await db.exec('SET ROLE service_role');await assert.rejects(db.exec('DELETE FROM wholesale_ingest.lead_evaluations'),/permission denied/);
});
test('changed source evidence and threshold reject a stale score',async t=>{
 const {db,save}=await setup(t);
 await db.exec(`UPDATE wholesale_ingest.distress_signals SET filed_date=filed_date-1 WHERE id='${id(4)}'`);
 assert.equal((await save()).blocked,'stale_input');
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.lead_evaluations')).rows[0].n,0);
});
test('unknown equity, made-up evidence, inflated stack and model routing cannot persist',async t=>{
 const {result,save}=await setup(t);const original=structuredClone(result);
 for(const change of [()=>{result.components.equity.points=20;},()=>{result.components.recency.evidence_ids=[id(99)];},()=>{result.components.distress_stack.points=30;},()=>{result.route='call_sms';},()=>{result.components.contactability.points=true;}]){
  Object.keys(result).forEach(k=>delete result[k]);Object.assign(result,structuredClone(original));change();assert.ok((await save()).blocked);
 }
});
test('inactive signals, browser roles and changed retry content are rejected',async t=>{
 const {db,result,save}=await setup(t);await save();result.components.recency.points=9;
 assert.equal((await save()).blocked,'reference_conflict');
 await db.exec(`UPDATE wholesale_ingest.distress_signals SET active=false`);
 assert.equal((await rpc(db,'list_scoring_input',[id(1)])).blocked,'no_active_signals');
 for(const role of ['anon','authenticated']){await db.exec('SET ROLE '+role);await assert.rejects(save(),/permission denied/);await db.exec('RESET ROLE');}
});

test('recent observation cannot make an old filing recent',async t=>{
 const {db,result}=await setup(t);
 await db.exec(`UPDATE wholesale_ingest.distress_signals SET filed_date=filed_date-90,last_seen_at=now()`);
 const current=await rpc(db,'list_scoring_input',[id(1)]);
 const value=await rpc(db,'save_list_score',[id(5),id(1),current.input_hash,'claude-fixture','daily-list-score-v1','msg-fixture',JSON.stringify(result)]);
 assert.equal(value.blocked,'unknown_evidence');
});
test('CRM contact changes alter input identity without sending contact values to Claude',async t=>{
 const {db,snapshot}=await setup(t);
 await db.exec(`ALTER TABLE public.leads ADD owner_phone_1 text;UPDATE public.leads SET owner_phone_1='+12145550198' WHERE id='${id(1)}'`);
 const first=await rpc(db,'list_scoring_input',[id(1)]);
 assert.notEqual(first.input_hash,snapshot.input_hash);
 assert.equal(first.input.contacts[0].phone_available,true);
 assert.ok(!JSON.stringify(first.input).includes('+12145550198'));
 await db.exec(`UPDATE public.leads SET owner_phone_1='+12145550199' WHERE id='${id(1)}'`);
 const changed=await rpc(db,'list_scoring_input',[id(1)]);assert.notEqual(changed.input_hash,first.input_hash);
});
test('multiple records from one list type do not inflate the stack',async t=>{
 const {db,result}=await setup(t);
 await db.exec(`INSERT INTO wholesale_ingest.distress_signals(property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
 SELECT property_id,source_id,'second-record',list_type,filed_date,source_url,first_run_id,last_run_id FROM wholesale_ingest.distress_signals WHERE id='${id(4)}'`);
 const current=await rpc(db,'list_scoring_input',[id(1)]);
 const value=await rpc(db,'save_list_score',[id(5),id(1),current.input_hash,'claude-fixture','daily-list-score-v1','msg-fixture',JSON.stringify(result)]);
 assert.equal(value.evaluation.stack_count,1);assert.equal(value.evaluation.score,32);
});
