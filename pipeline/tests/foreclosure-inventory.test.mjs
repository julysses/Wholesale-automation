import test from 'node:test';
import assert from 'node:assert/strict';
import {inventoryManifests,normalizeDallasCapture} from '../collectors/foreclosure_inventory.mjs';
const now=new Date('2026-10-13T19:00:00Z');
function fixture(county='Dallas'){
 const id='12345';const d={document_id:id,document_number:'202600000001',document_url:county==='Dallas'?`https://dallas.tx.publicsearch.us/doc/${id}`:`https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/${id}`,filed_date:'2026-10-01',auction_date:'2026-10-06',indexed_address:'Two properties, SYNTHETIC COUNTY INDEX ONLY'};
 return {schema_version:'1.0',county,window_start:'2026-09-14',window_end:'2026-10-13',page_size:25,scans:[[{page:1,total:1,captured_at:'2026-10-13T18:00:00Z',documents:[d]}],[{page:1,total:1,captured_at:'2026-10-13T18:05:00Z',documents:[structuredClone(d)]}]]};
}
test('both county inventories become only unresolved discovery, with raw address retained',async()=>{
 for(const county of ['Dallas','Collin']){
  const {batches,records}=await inventoryManifests(fixture(county),now);const p=batches[0],r=p.records[0];
  assert.equal(records,1);assert.equal(p.status,'partial');assert.equal(p.coverage_complete,false);
  assert.equal(r.property_address,null);assert.equal(r.city,null);assert.equal(r.amount_owed,null);
  assert.equal(r.raw.current_status_checked,false);assert.equal(r.raw.filing_stamp_verified,false);
  assert.match(r.raw.indexed_address,/Two properties/);assert.equal(r.source_record_id,'12345');
 }
});
test('drift, duplicate IDs, missing pages, foreign detail IDs and invalid filing dates fail',async()=>{
 for(const mutate of [
  c=>c.scans[1][0].documents[0].indexed_address='changed',
  c=>c.scans[0][0].total=26,
  c=>{for(const s of c.scans){s[0].total=2;s[0].documents.push({...s[0].documents[0]});}},
  c=>c.scans[0][0].documents[0].document_url='https://evil.example/doc/12345',
  c=>c.scans[0][0].documents[0].filed_date='2026-09-01',
  c=>c.scans[0][0].documents[0].auction_date='2026-02-30',
  c=>c.scans[1][0].captured_at='2026-10-13T17:00:00Z',
  c=>c.scans[0][0].captured_at='2026-10-11T18:00:00Z',
 ]){const c=fixture();mutate(c);await assert.rejects(inventoryManifests(c,now));}
});
test('Dallas adapter binds displayed range and IDs, not sale-date filters or guessed identifiers',async()=>{
 const page={status:'1-1 of 1 results for "09/14/2026-10/13/2026"',at:'2026-10-13T18:00:00Z',rows:[{id:'Document 12345, not selected, checkbox',cells:['','','','NOTICE OF FORECLOSURE','10/1/2026','10/6/2026','202600000001','SYNTHETIC ONLY']}]};
 const c={source:'https://dallas.tx.publicsearch.us/results?department=FC&searchType=advancedSearch&recordedDateRange=20260914%2C20261013',passes:[[page],[{...structuredClone(page),at:'2026-10-13T18:05:00Z'}]]};
 assert.equal((await inventoryManifests(normalizeDallasCapture(c),now)).records,1);
 const sale=structuredClone(c);sale.source+='&saleDateRange=20260914%2C20261013';assert.throws(()=>normalizeDallasCapture(sale),/sale-date/);
 const drift=structuredClone(c);drift.passes[1][0].status='1-1 of 1 results for "09/01/2026-10/13/2026"';assert.throws(()=>normalizeDallasCapture(drift),/filter/);
 c.passes[0][0].rows[0].id='Unknown';assert.throws(()=>normalizeDallasCapture(c),/layout/);
});
