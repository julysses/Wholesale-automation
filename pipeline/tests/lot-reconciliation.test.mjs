import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './lot-fixture.mjs';
import {id,rpc} from './scoring-fixture.mjs';
const state=async db=>(await db.query('select wholesale_ingest.lot_handoff_state($1) v',[id(21)])).rows[0].v;
const decide=(db,s,action='hold',event=id(60),actor=id(10))=>rpc(db,'reconcile_list_lot',[event,actor,id(21),s.version,action,s.evidence_hash,'Reviewed current lot evidence']);
async function ready(t){const f=await fixture(t);await f.review();await f.score();await f.handoff();return f;}
test('city and destination changes are detected even when scoring input hash is unchanged',async t=>{
 const {db}=await ready(t);const before=await state(db);assert.equal(before.current,true);
 await db.exec("UPDATE wholesale_ingest.properties SET city='Changed city'");
 const after=await state(db);assert.equal(after.current_input_hash,before.current_input_hash);assert.equal(after.current,false);
 assert.ok(after.reasons.includes('lot_review_required'));assert.ok(after.reasons.includes('destination_identity_conflict'));
 assert.equal((await decide(db,after,'reaffirm')).blocked,'current_reviewed_evidence_required');
 assert.equal((await decide(db,before)).blocked,'evidence_changed');
});
test('reviewed correction reaffirms current evidence while preserving original handoff and first receiver',async t=>{
 const {db}=await ready(t);await rpc(db,'acknowledge_list_lot',[id(21),id(11)]);
 const original=(await db.query('select to_jsonb(h) v from wholesale_ingest.lot_handoffs h')).rows[0].v;
 await db.exec("UPDATE wholesale_ingest.properties SET city='Corrected';UPDATE public.land_leads SET city='Corrected'");
 const hash=(await rpc(db,'list_scoring_input',[id(1)])).input_hash;
 await rpc(db,'review_list_lot',[id(61),id(10),id(1),hash,true,'https://example.invalid/corrected','Verified correction']);
 let s=await state(db);assert.equal(s.current,false);assert.equal(s.reaffirmable,true);
 const response=await decide(db,s,'reaffirm');assert.equal(response.event.version,1);
 s=await state(db);assert.equal(s.current,true);assert.equal(s.effective_review_id,id(61));
 assert.deepEqual((await db.query('select to_jsonb(h) v from wholesale_ingest.lot_handoffs h')).rows[0].v,original);
 assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,1);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 assert.equal((await rpc(db,'list_lot_handoffs',[id(11),0])).handoffs[0].current,true);
});
test('historical decision retry cannot restore a hold after a later reaffirmation',async t=>{
 const {db}=await ready(t);const first=await state(db);await decide(db,first);
 let s=await state(db);assert.equal(s.current,false);assert.ok(s.reasons.includes('administrator_hold'));
 assert.equal((await decide(db,first,'reaffirm',id(62))).blocked,'version_conflict');
 await decide(db,s,'reaffirm',id(63));assert.equal((await state(db)).current,true);
 assert.equal((await decide(db,first)).replayed,true);s=await state(db);assert.equal(s.current,true);assert.equal(s.version,2);
 assert.equal((await decide(db,first,'reaffirm')).blocked,'reference_conflict');
 await assert.rejects(db.exec("UPDATE wholesale_ingest.lot_reconciliations SET notes='rewrite'"),/Immutable/);
 await assert.rejects(db.exec('DELETE FROM wholesale_ingest.lot_reconciliations'),/Immutable/);
});
test('stale acknowledged handoff stays visible to monitoring without creating another task',async t=>{
 const {db}=await ready(t);await rpc(db,'acknowledge_list_lot',[id(21),id(11)]);
 await db.exec("UPDATE public.tasks SET status='completed';UPDATE public.land_leads SET property_address='Different parcel'");
 let m=await rpc(db,'monitor_list_lots',[]);assert.equal(m.stale_handoffs.length,1);assert.ok(m.stale_handoffs[0].reasons.includes('destination_identity_conflict'));assert.equal(m.overdue_receipts.length,0);
 await rpc(db,'monitor_list_lots',[]);assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);assert.equal((await db.query('select status from public.tasks')).rows[0].status,'pending');
});
test('stale score and unavailable receiver prevent reaffirmation; holds and access rules remain explicit',async t=>{
 const {db}=await ready(t);await db.exec(`UPDATE wholesale_ingest.settings SET score_threshold=31;UPDATE public.profiles SET status='pending' WHERE id='${id(11)}'`);
 const s=await state(db);assert.equal(s.reaffirmable,false);assert.ok(s.reasons.includes('current_qualifying_score_required'));assert.ok(s.reasons.includes('assigned_owner_unavailable'));
 assert.equal((await decide(db,s,'reaffirm')).blocked,'current_reviewed_evidence_required');
 assert.equal((await decide(db,s)).event.action,'hold');
 await assert.rejects(decide(db,await state(db),'hold',id(64),id(12)),/administrator/);
 await db.exec('SET ROLE authenticated');await assert.rejects(decide(db,s,'hold',id(65)),/permission denied/);
});

test('known source ZIP must still match the destination',async t=>{
 const {db}=await ready(t);
 await db.exec("UPDATE wholesale_ingest.properties SET zip='75201';UPDATE public.land_leads SET zip_code='75202'");
 assert.ok((await state(db)).reasons.includes('destination_identity_conflict'));
});

test('lost property association remains visible with original reviewed address and a review hold',async t=>{
 const {db}=await ready(t);await db.exec('UPDATE wholesale_ingest.properties SET lead_id=NULL');
 const inbox=await rpc(db,'list_lot_handoffs',[id(11),0]);
 assert.equal(inbox.count,1);assert.equal(inbox.handoffs.length,1);assert.equal(inbox.handoffs[0].address_std,'SYNTHETIC SCORING');
 assert.equal(inbox.handoffs[0].county,'Dallas');assert.equal(inbox.handoffs[0].current,false);
 assert.ok(inbox.handoffs[0].reconciliation.reasons.includes('verified_lot_required'));
 assert.equal((await decide(db,await state(db))).event.action,'hold');
});
