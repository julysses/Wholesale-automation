import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,payload} from './valuation-fixture.mjs';
import {id,rpc} from './scoring-fixture.mjs';
test('save derives valuation math, retains unknowns, and replays exact receipt once without pricing writes',async t=>{
 const {db,read,save}=await fixture(t);const before=await read();const p=payload();
 p.direct_comp_details=[100,200].map((price,i)=>({address:`Synthetic comp ${i}`,price,sqft:null,date:null,distance_mi:0,source_url:null}));p.avg_house_arv=200000;p.house_comp_count=2;
 const saved=await save(before.snapshot_hash,p);assert.equal(saved.outreach_authorized,false);
 const comp=saved.event.saved_snapshot.comp;assert.equal(comp.direct_comp_avg,150);assert.equal(comp.arv_15pct_value,30000);assert.equal(comp.direct_comp_count,2);assert.equal(comp.tav,0);assert.equal(comp.recommended_offer_low,null);
 assert.equal(comp.direct_comp_details[0].sqft,null);assert.equal(comp.direct_comp_details[0].distance_mi,0);
 assert.equal((await save(before.snapshot_hash,p)).replayed,true);
 assert.equal((await db.query('select count(*)::int n from public.land_comps')).rows[0].n,1);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.land_valuation_events')).rows[0].n,1);
 const land=(await db.query('select * from public.land_leads')).rows[0];assert.equal(land.offer_price,'12345');assert.equal(land.mao,'23456');assert.equal(land.status,'new');
});
test('new and existing saves reject stale snapshots, while replay cannot overwrite a later revision',async t=>{
 const {db,read,save}=await fixture(t);const start=await read();const p=payload();await save(start.snapshot_hash,p);
 assert.equal((await save(start.snapshot_hash,p,id(72))).blocked,'valuation_changed');
 const current=await read();const edited={...p,tav:100};await save(current.snapshot_hash,edited,id(73));
 assert.equal((await read()).comp.revision,2);
 assert.equal((await save(start.snapshot_hash,p)).replayed,true);assert.equal((await read()).comp.tav,100);
 assert.equal((await save(start.snapshot_hash,edited)).blocked,'reference_conflict');
 const view=await read();await db.exec("UPDATE public.land_leads SET city='Changed city'");assert.equal((await save(view.snapshot_hash,p,id(74))).blocked,'valuation_changed');
});
test('historical duplicates remain intact and only the selected latest record is revised',async t=>{
 const {db,read,save}=await fixture(t);
 await db.exec(`INSERT INTO public.land_comps(id,land_lead_id,created_at,tav,recommended_offer_low,recommended_offer_high) VALUES('${id(80)}','${id(70)}','2026-01-01',100,65,75),('${id(81)}','${id(70)}','2026-01-02',200,130,150)`);
 await db.exec('UPDATE public.land_comps SET house_comp_radius_mi=0.75');
 const s=await read();assert.equal(s.record_count,2);assert.equal(s.comp.id,id(81));
 const result=await save(s.snapshot_hash,{...payload(),tav:300});assert.equal(result.event.comp_id,id(81));
 assert.equal((await read()).record_count,2);assert.equal((await read()).comp.recommended_offer_high,150);assert.equal((await read()).comp.house_comp_radius_mi,0.75);
 assert.equal((await db.query('select tav from public.land_comps where id=$1',[id(80)])).rows[0].tav,'100.00');
});
test('failed receipt persistence rolls back the comp write',async t=>{
 const {db,read,save}=await fixture(t);const s=await read();
 await db.exec("ALTER TABLE wholesale_ingest.land_valuation_events ADD CONSTRAINT fixture_fail CHECK(payload->>'comp_notes'<>'reject')");
 await assert.rejects(save(s.snapshot_hash,{...payload(),comp_notes:'reject'}),/fixture_fail/);
 assert.equal((await read()).record_count,0);assert.equal((await read()).snapshot_hash,s.snapshot_hash);
});
test('invalid or fabricated valuation inputs never enter storage',async t=>{
 const {read,save}=await fixture(t);const s=await read();
 const cases=[{tav:-1},{tav:1.001},{tav:'12'},{avg_house_arv:100000},{house_comp_count:1.5},{tav_assessment_date:'2999-01-01'},{tav_assessment_date:'2026-02-30'},{offer_price:100},
 {direct_comp_details:[{address:' ',price:100,sqft:null,date:null,distance_mi:null,source_url:null}]},
 {direct_comp_details:[{address:'Example',price:0,sqft:null,date:null,distance_mi:null,source_url:null}]},
 {direct_comp_details:[{address:'Example',price:100,sqft:0,date:null,distance_mi:null,source_url:null}]},
 {direct_comp_details:[{address:'Example',price:100,sqft:null,date:null,distance_mi:null,source_url:'javascript:bad'}]}];
 for(const change of cases)assert.equal((await save(s.snapshot_hash,{...payload(),...change})).blocked,'invalid_valuation',JSON.stringify(change));
 assert.equal((await read()).record_count,0);
});
test('browser writes and direct RPCs are denied, and receipts are immutable',async t=>{
 const {db,read,save}=await fixture(t);await save((await read()).snapshot_hash);
 await assert.rejects(db.exec("UPDATE wholesale_ingest.land_valuation_events SET expected_hash=repeat('b',64)"),/Immutable/);
 await assert.rejects(db.exec('DELETE FROM wholesale_ingest.land_valuation_events'),/Immutable/);
 await db.exec(`UPDATE public.profiles SET status='pending' WHERE id='${id(12)}'`);await assert.rejects(rpc(db,'read_land_valuation',[id(70),id(12)]),/Approved/);
 await db.exec('SET ROLE authenticated');await assert.rejects(read(),/permission denied/);
 await assert.rejects(db.exec('UPDATE public.land_comps SET tav=999'),/permission denied/);
 await assert.rejects(db.exec(`INSERT INTO public.land_comps(land_lead_id) VALUES('${id(70)}')`),/permission denied/);
});
