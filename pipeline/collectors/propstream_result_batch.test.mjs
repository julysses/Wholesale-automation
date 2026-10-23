import test from 'node:test';
import assert from 'node:assert/strict';
import {matchCompletedResults} from './propstream_result_batch.mjs';
const q={properties:[{identity:{property_address:'1 TEST LN',city:'ANNA',state:'TX',zip:'75409',parcel_id:'R-1'},owner_name:'EXAMPLE OWNER'}]};
const row={url:'https://app.propstream.com/contact/A123/123',cells:['EXAMPLE OWNER (Litigator)','(214)-555-0100 DNC','(214)-555-0101','','example@example.com','1 TEST LN ANNA, TX 75409','','Owner','Group']};
const receipt={job:'A123',status:'complete',rows:[row]};
test('completed batch retains provider exclusions without assuming channel clearance',()=>{
 const [r]=matchCompletedResults(q,receipt);assert.equal(r.provider_litigator_flag,true);assert.equal(r.contacts.length,3);
 assert.equal(r.contacts[0].dnc_status,'listed');assert.equal(r.contacts[1].dnc_status,'unknown');assert.equal(r.outreach_authorized,false);
});
test('partial, wrong owner, duplicate and unreadable provider batches fail closed',()=>{
 assert.throws(()=>matchCompletedResults(q,{...receipt,status:'processing'}),/Complete/);
 assert.throws(()=>matchCompletedResults(q,{...receipt,rows:[]}),/Complete/);
 for(const [i,text] of [[0,'DIFFERENT OWNER'],[1,'unknown phone'],[5,'1 TEST LN UNIT A ANNA TX 75409']]) {
  const cells=[...row.cells];cells[i]=text;assert.throws(()=>matchCompletedResults(q,{...receipt,rows:[{...row,cells}]}));
 }
 assert.throws(()=>matchCompletedResults({properties:[...q.properties,{...q.properties[0],identity:{...q.properties[0].identity,property_address:'2 TEST LN',parcel_id:'R-2'}}]}, {...receipt,rows:[row,row]}),/Duplicate/);
});
