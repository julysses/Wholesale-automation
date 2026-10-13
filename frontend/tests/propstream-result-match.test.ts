import {expect,it} from 'vitest';
import {matchPropstreamResults,readResultCsv} from '@/lib/propstreamResultMatch';
const columns={owner:'Name',address:'Address',city:'City',state:'State',zip:'Zip',phone:'Phone',email:'Email',dnc:'DNC'};
const base={action:'reconcile',request_id:'r1',lead_id:'l1',input_hash:'a'.repeat(64),owner_name:'Test Owner',property_address:'12 Test St',city:'Dallas',state:'TX',zip_code:'75201'};
const provider={Name:'Test Owner',Address:'12 Test St',City:'Dallas',State:'TX',Zip:'75201',Phone:'(214) 555-0198',Email:'',DNC:'No'};
it('matches reordered provider rows to exact owner and property and deduplicates contact rows',()=>{
 const second={...base,request_id:'r2',lead_id:'l2',property_address:'14 Test St'};
 const result=matchPropstreamResults([base,second],[{...provider,Address:'14 Test St'},provider,provider],columns);
 expect(result.matched.map(x=>x.request_id)).toEqual(['r1','r2']);expect(result.matched[0].phone_1).toBe('+12145550198');expect(result.matched[0].phone_2).toBe('');expect(result.matched[0].confirmed_match).toBe('false');expect(result.matched[0].actual_cents).toBe('');
});
it('never infers no-match or guesses an owner or unit',()=>{
 for(const change of [{Name:'Other Owner'},{Address:'12 Test St Unit 2'},{Zip:'75201-1234'}]){
 const r=matchPropstreamResults([base],[{...provider,...change}],columns);expect(r.matched).toHaveLength(0);expect(r.held).toHaveLength(1);
 }
 expect(matchPropstreamResults([base],[],columns).held[0].reason).toMatch(/No matched provider/);
});
it('holds every ambiguous identity and all provider suppression or invalid contact results',()=>{
 const ambiguous=matchPropstreamResults([base,{...base,request_id:'r2',lead_id:'l2'}],[provider],columns);expect(ambiguous.matched).toHaveLength(0);expect(ambiguous.held).toHaveLength(2);
 for(const change of [{DNC:'Yes'},{Phone:'not a phone'},{Phone:''}])expect(matchPropstreamResults([base],[provider,{...provider,...change}],columns).matched).toHaveLength(0);
 expect(matchPropstreamResults([base],[{...provider,DNC:'Yes'}],{...columns,dnc:''}).matched).toHaveLength(0);
});
it('rejects malformed CSV and duplicate request manifests',()=>{
 expect(()=>readResultCsv('Name,Name\na,b')).toThrow();expect(()=>matchPropstreamResults([base,base],[provider],columns)).toThrow();
});

it('maps multiple contact columns and refuses to silently discard an unmapped phone',()=>{
 const row={...provider,'Phone 2':'214-555-0199'};
 expect(matchPropstreamResults([base],[row],columns).held[0].reason).toMatch(/Unmapped/);
 const r=matchPropstreamResults([base],[row],{...columns,phone2:'Phone 2'});expect(r.matched[0].phone_2).toBe('+12145550199');
});
