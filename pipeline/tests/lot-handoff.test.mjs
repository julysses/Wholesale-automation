import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
async function fixture(t){
 const f=await setup(t);
 await f.db.exec(`CREATE TABLE public.land_leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),lead_id uuid,source text,owner_name text NOT NULL,property_address text,city text,state text,zip_code text,county text,apn text,status text,assigned_to uuid,sms_sequence_active boolean,offer_price numeric,mao numeric);
 INSERT INTO public.profiles VALUES('${id(10)}','admin','approved'),('${id(11)}','user','approved'),('${id(12)}','user','approved');
 UPDATE wholesale_ingest.properties SET city='Dallas';UPDATE wholesale_ingest.settings SET score_threshold=30;`);
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012235926_list_lot_handoff.sql',import.meta.url),'utf8'));
 const hash=(await rpc(f.db,'list_scoring_input',[id(1)])).input_hash;
 const review=()=>rpc(f.db,'review_list_lot',[id(20),id(10),id(1),hash,true,'https://example.invalid/official-lot','Reviewed exact parcel classification']);
 const score=async()=>{const s=await rpc(f.db,'list_scoring_input',[id(1)]);return rpc(f.db,'save_list_score',[id(5),id(1),s.input_hash,'claude-fixture','daily-list-score-v1','msg-fixture',JSON.stringify(f.result)]);};
 const handoff=(event=id(21))=>rpc(f.db,'handoff_list_lot',[event,id(10),id(5),id(11)]);
 return {...f,hash,review,score,handoff};
}
test('reviewed lot creates one linked destination/task, preserving unknowns and requiring separate receipt',async t=>{
 const {db,review,score,handoff}=await fixture(t);
 await review();assert.equal((await review()).replayed,true);assert.equal((await score()).evaluation.route,'underwrite_lot');
 const first=await handoff();assert.equal(first.outreach_authorized,false);assert.equal(first.handoff.acknowledged_at,null);
 assert.equal((await handoff()).handoff.id,first.handoff.id);assert.equal((await handoff(id(22))).blocked,'existing_handoff');
 const land=(await db.query('select * from public.land_leads')).rows;assert.equal(land.length,1);assert.equal(land[0].owner_name,null);assert.equal(land[0].offer_price,null);assert.equal(land[0].mao,null);assert.equal(land[0].sms_sequence_active,false);assert.equal(land[0].status,'new');
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 const ack=await rpc(db,'acknowledge_list_lot',[id(21),id(11)]);assert.equal(ack.handoff.acknowledged_by,id(11));assert.ok(ack.handoff.acknowledged_at);
 const replay=await rpc(db,'acknowledge_list_lot',[id(21),id(10)]);assert.equal(replay.handoff.acknowledged_by,id(11));assert.equal(replay.replayed,true);
 assert.equal((await db.query('select status from public.tasks')).rows[0].status,'pending');
});
test('lot flag alone, stale scoring and changed property cannot authorize handoff',async t=>{
 const {db,review,score,handoff}=await fixture(t);
 await db.exec('UPDATE wholesale_ingest.properties SET is_vacant_lot=true');await score();assert.equal((await handoff()).blocked,'lot_review_required');
 const hash=(await rpc(db,'list_scoring_input',[id(1)])).input_hash;
 await rpc(db,'review_list_lot',[id(20),id(10),id(1),hash,true,'https://example.invalid/official-lot','Reviewed']);
 await db.exec("UPDATE wholesale_ingest.properties SET city='Different'");assert.equal((await handoff()).blocked,'lot_review_required');
 await db.exec("UPDATE wholesale_ingest.properties SET city='Dallas';UPDATE wholesale_ingest.settings SET score_threshold=31");assert.equal((await handoff()).blocked,'stale_score');
 assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,0);
});
test('unlinked legacy matches block instead of duplicating or overwriting existing land',async t=>{
 const {db,review,score,handoff}=await fixture(t);await review();await score();
 await db.exec("INSERT INTO public.land_leads(property_address,city,state,county,owner_name,offer_price,status) VALUES('SYNTHETIC SCORING','Dallas','TX','Dallas','Manual owner',50000,'under_contract')");
 assert.equal((await handoff()).blocked,'legacy_land_match_requires_review');
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,0);
 await db.exec(`UPDATE public.land_leads SET lead_id='${id(1)}'`);const response=await handoff();assert.ok(response.handoff);
 assert.equal((await db.query('select offer_price,status from public.land_leads')).rows[0].offer_price,'50000');
 assert.equal((await db.query('select status from public.land_leads')).rows[0].status,'under_contract');
});
test('routing transaction rolls back destination when task persistence fails',async t=>{
 const {db,review,score,handoff}=await fixture(t);await review();await score();
 await db.exec("ALTER TABLE public.tasks ADD CONSTRAINT fixture_task_failure CHECK(title<>'Review lot underwriting intake')");
 await assert.rejects(handoff(),/fixture_task_failure/);assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,0);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.lot_handoffs')).rows[0].n,0);
});
test('operator scoping, immutable acknowledgements and browser privilege denial hold',async t=>{
 const {db,hash,review,score,handoff}=await fixture(t);await review();await score();await handoff();
 await assert.rejects(rpc(db,'review_list_lot',[id(23),id(11),id(1),hash,true,'https://example.invalid/lot','Reviewed']),/administrator/);
 assert.equal((await rpc(db,'list_lot_handoffs',[id(12),0])).count,0);
 await assert.rejects(rpc(db,'acknowledge_list_lot',[id(21),id(12)]),/Assigned operator/);
 await rpc(db,'acknowledge_list_lot',[id(21),id(11)]);
 await assert.rejects(db.exec("UPDATE wholesale_ingest.lot_handoffs SET acknowledged_at=NULL,acknowledged_by=NULL"),/Immutable/);
 await db.exec('SET ROLE authenticated');await assert.rejects(rpc(db,'list_lot_candidates',[id(10),0]),/permission denied/);await assert.rejects(rpc(db,'acknowledge_list_lot',[id(21),id(11)]),/permission denied/);
});
test('historical review replay cannot restore a superseded lot classification',async t=>{
 const {db,review}=await fixture(t);await review();
 const hash=(await rpc(db,'list_scoring_input',[id(1)])).input_hash;
 await rpc(db,'review_list_lot',[id(24),id(10),id(1),hash,false,'https://example.invalid/correction','Verified improved parcel']);
 assert.equal((await review()).replayed,true);
 assert.equal((await db.query('select is_vacant_lot from wholesale_ingest.properties')).rows[0].is_vacant_lot,false);
});
test('missing city or unsupported unit cannot create a land destination',async t=>{
 const {db,review,score,handoff}=await fixture(t);await db.exec('UPDATE wholesale_ingest.properties SET city=NULL');await review();await score();
 assert.equal((await handoff()).blocked,'land_identity_review_required');assert.equal((await db.query('select count(*)::int n from public.land_leads')).rows[0].n,0);
});
