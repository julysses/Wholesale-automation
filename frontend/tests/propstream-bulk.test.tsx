import {expect,it} from 'vitest';
import Papa from 'papaparse';
import {parseBulkCsv} from '@/lib/propstreamBulkCsv';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const row={action:'reconcile',lead_id:id(1),request_id:id(2),input_hash:'a'.repeat(64),no_match:'false',actual_cents:'15',provider_receipt:'batch-order',confirmed_match:'true',phone_1:'+12145550198',phone_type_1:'mobile'};
it('bulk results preserve stable identities and matching contacts, not row order',()=>{
 const r=parseBulkCsv(Papa.unparse([row,{...row,lead_id:id(3),request_id:id(4),phone_1:'',no_match:'true'}]),'reconcile');
 expect(r.items).toHaveLength(2);expect(r.items[0].request_id).toBe(id(2));expect(r.items[0].payload.contacts).toHaveLength(1);expect(r.items[1].payload.contacts).toEqual([]);
});
it('rejects duplicate leads, missing receipt mapping, unconfirmed matches and ambiguous empty results',()=>{
 for(const rows of [[row,row],[{...row,request_id:''}],[{...row,confirmed_match:'false'}],[{...row,phone_1:''}],[{...row,no_match:'true'}]])expect(()=>parseBulkCsv(Papa.unparse(rows),'reconcile')).toThrow();
});
it('bulk status review requires an explicit current-status confirmation',()=>{
 const status={action:'review_status',lead_id:id(1),signal_id:id(5),signal_hash:'a'.repeat(32),active:'true',auction_date:'2026-12-01',status_evidence_url:'https://www.dallascounty.org/test',notes:'Synthetic current sale evidence',confirmed_current_status:'false'};
 expect(()=>parseBulkCsv(Papa.unparse([status]),'review_status')).toThrow();
 expect(parseBulkCsv(Papa.unparse([{...status,confirmed_current_status:'true'}]),'review_status').items[0].payload.active).toBe(true);
});
