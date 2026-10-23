import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './lot-fixture.mjs';
import {id,rpc} from './scoring-fixture.mjs';
const owner=async db=>db.exec(`INSERT INTO public.app_settings(key,value) VALUES('lead_owner_user_id','${id(11)}')`);
const monitor=async(db,now='now()')=>(await db.query(`select wholesale_ingest.scan_lots_at(${now}) v`)).rows[0].v;
test('worker routes reviewed current lot once with explicit automatic origin and assigned task',async t=>{
 const {db,review,score}=await fixture(t);await review();await score();await owner(db);
 const result=await rpc(db,'route_list_lots',[5]);assert.equal(result.outreach_authorized,false);assert.equal(result.outcomes.length,1);assert.equal(result.outcomes[0].blocked,null);
 const inbox=await rpc(db,'list_lot_handoffs',[id(11),0]);assert.equal(inbox.count,1);assert.equal(inbox.handoffs[0].operator_id,null);assert.equal(inbox.handoffs[0].initiation,'worker');
 assert.equal((await rpc(db,'route_list_lots',[5])).outcomes.length,0);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 await assert.rejects(db.exec("UPDATE wholesale_ingest.lot_handoffs SET initiation='operator'"),/Immutable/);
 assert.equal((await rpc(db,'handoff_list_lot',[result.outcomes[0].handoff_id,id(10),id(5),id(11)])).blocked,'reference_conflict');
});
test('missing owner holds then creates one recovery task; source review remains mandatory',async t=>{
 const {db,score}=await fixture(t);await db.exec('UPDATE wholesale_ingest.properties SET is_vacant_lot=true');await score();
 assert.equal((await rpc(db,'route_list_lots',[5])).outcomes[0].blocked,'owner_not_configured');
 let status=await monitor(db);assert.equal(status.owner_configured,false);assert.equal(status.open_incidents[0].task_id,null);
 await owner(db);await monitor(db);await monitor(db);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 assert.equal((await rpc(db,'route_list_lots',[5])).outcomes[0].blocked,'lot_review_required');
 const hash=(await rpc(db,'list_scoring_input',[id(1)])).input_hash;
 await rpc(db,'review_list_lot',[id(30),id(10),id(1),hash,true,'https://example.invalid/lot','Reviewed']);
 assert.equal((await rpc(db,'route_list_lots',[5])).outcomes[0].blocked,null);
 assert.equal((await monitor(db)).open_incidents.length,0);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,2);
});
test('per-candidate persistence error rolls back land writes and retains safe failure evidence',async t=>{
 const {db,review,score}=await fixture(t);await review();await score();await owner(db);
 await db.exec("ALTER TABLE public.tasks ADD CONSTRAINT fixture_lot_error CHECK(title<>'Review lot underwriting intake')");
 const result=await rpc(db,'route_list_lots',[5]);assert.equal(result.outcomes[0].blocked,'routing_error_23514');
 assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,0);
 assert.equal((await monitor(db)).open_incidents.length,1);
 await db.exec('ALTER TABLE public.tasks DROP CONSTRAINT fixture_lot_error');
 assert.ok((await rpc(db,'route_list_lots',[5])).outcomes[0].handoff_id);
});
test('overdue acknowledgement reuses original task and clears only after receiving receipt',async t=>{
 const {db,review,score}=await fixture(t);await review();await score();await owner(db);
 const result=await rpc(db,'route_list_lots',[5]);
 const stamp="(SELECT created_at FROM wholesale_ingest.lot_handoffs LIMIT 1)";
 assert.equal((await monitor(db,stamp+"+interval '59 minutes 59 seconds'")).overdue_receipts.length,0);
 assert.equal((await monitor(db,stamp+"+interval '60 minutes'")).overdue_receipts.length,1);
 await monitor(db,stamp+"+interval '61 minutes'");
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 await rpc(db,'acknowledge_list_lot',[result.outcomes[0].handoff_id,id(11)]);
 assert.equal((await monitor(db,stamp+"+interval '62 minutes'")).overdue_receipts.length,0);
 assert.equal((await db.query('select status from public.tasks')).rows[0].status,'pending');
});
test('blocked oldest lead cannot starve unseen candidates and stale scores cannot route',async t=>{
 const {db,review,score}=await fixture(t);await review();await score();await owner(db);
 await db.exec(`INSERT INTO public.leads(id,property_address) VALUES('${id(40)}','SYNTHETIC SECOND');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,lead_id,city,is_vacant_lot) VALUES('${id(41)}','TX','Dallas','SYNTHETIC SECOND','${id(40)}','Dallas',true);
 INSERT INTO wholesale_ingest.lead_evaluations SELECT (jsonb_populate_record(NULL::wholesale_ingest.lead_evaluations,to_jsonb(e)||jsonb_build_object('id','${id(42)}','lead_id','${id(40)}','created_at',now()+interval '1 second'))).* FROM wholesale_ingest.lead_evaluations e WHERE id='${id(5)}';
 UPDATE wholesale_ingest.settings SET score_threshold=31;`);
 const first=await rpc(db,'route_list_lots',[1]),second=await rpc(db,'route_list_lots',[1]);
 assert.equal(first.outcomes[0].lead_id,id(1));assert.equal(second.outcomes[0].lead_id,id(40));
 assert.equal(first.outcomes[0].blocked,'stale_score');assert.equal(second.outcomes[0].blocked,'stale_score');
 assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,0);
});
test('worker enforces limits, approved owner and browser denial',async t=>{
 const {db,review,score}=await fixture(t);await review();await score();await owner(db);
 await assert.rejects(rpc(db,'route_list_lots',[11]),/Invalid routing limit/);
 await db.exec(`UPDATE public.profiles SET status='pending' WHERE id='${id(11)}'`);
 assert.equal((await rpc(db,'route_list_lots',[1])).outcomes[0].blocked,'owner_not_configured');
 await db.exec('SET ROLE authenticated');await assert.rejects(rpc(db,'route_list_lots',[1]),/permission denied/);await assert.rejects(rpc(db,'monitor_list_lots',[]),/permission denied/);
});
