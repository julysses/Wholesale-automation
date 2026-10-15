import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
import type {LandLead} from '@/types';
import {ApiError} from '@/lib/api';
const actor='00000000-0000-4000-8000-000000000001',land='00000000-0000-4000-8000-000000000002',comp='00000000-0000-4000-8000-000000000003';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),approved:true}));
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({profile:{id:actor},isApproved:mocks.approved})}));
import {QuickCompCalculator} from '@/components/land/QuickCompCalculator';
const lead={id:land,property_address:'SYNTHETIC LOT',tav:100000,mao:75000,offer_price:65000} as LandLead;
const mount=()=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><QuickCompCalculator lead={lead}/></QueryClientProvider>);
const base=()=>({land_lead_id:land,snapshot_hash:'a'.repeat(64),record_count:0,comp:null as Record<string,unknown>|null,property_address:'SYNTHETIC LOT',reference_tav:100000,outreach_authorized:false});
let snapshot=base();let events=new Map<string,unknown>();let loseNext=false;
beforeEach(()=>{
 sessionStorage.clear();vi.resetAllMocks();mocks.approved=true;snapshot=base();events=new Map();loseNext=false;
 mocks.fetch.mockImplementation(async(_url:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>snapshot};
  const body=JSON.parse(init.body as string);
  if(!events.has(body.request_id)){
   snapshot={...snapshot,snapshot_hash:'b'.repeat(64),record_count:1,comp:{id:comp,land_lead_id:land,revision:Number(snapshot.comp?.revision??0)+1,...body.payload}};
   events.set(body.request_id,{event:{id:body.request_id,operator_id:actor,land_lead_id:land,comp_id:comp,expected_hash:body.expected_hash,payload:body.payload,saved_snapshot:snapshot},outreach_authorized:false});
  }
  if(loseNext){loseNext=false;throw new Error('Receipt connection lost');}
  return {json:async()=>events.get(body.request_id)};
 });
});
it('retains valuation arithmetic, submits raw evidence only and never writes offers or lead stage',async()=>{
 mount();fireEvent.change(await screen.findByPlaceholderText('280000'),{target:{value:'200000'}});
 fireEvent.change(screen.getByPlaceholderText('6'),{target:{value:'2'}});
 expect(screen.getByText('$30,000')).toBeTruthy();expect(screen.queryByText('Recommended Offer Range')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 const request=JSON.parse(mocks.fetch.mock.calls.find(call=>call[1])![1].body);expect(request.payload.avg_house_arv).toBe(200000);expect(request.payload.tav).toBe(100000);
 for(const key of ['recommended_offer_low','recommended_offer_high','mao','offer_price','arv_15pct_value','direct_comp_avg'])expect(request.payload).not.toHaveProperty(key);
 expect(mocks.fetch.mock.calls.every(call=>call[0]===`/api/land-underwriting/valuations/${land}`)).toBe(true);
});
it('lost receipt survives remount and retries the same exact request without a second record',async()=>{
 loseNext=true;const first=mount();fireEvent.click(await screen.findByRole('button',{name:'Save Comp Analysis'}));await screen.findByText('Receipt connection lost');
 const firstBody=mocks.fetch.mock.calls.find(call=>call[1])![1].body;first.unmount();
 mount();fireEvent.click(await screen.findByRole('button',{name:'Retry saved valuation'}));await screen.findByRole('status');
 const bodies=mocks.fetch.mock.calls.filter(call=>call[1]).map(call=>call[1].body);expect(bodies).toEqual([firstBody,firstBody]);expect(events.size).toBe(1);expect(sessionStorage.length).toBe(0);
});
it('reloads saved historical analysis and leaves historical offer fields out of edits',async()=>{
 snapshot={...snapshot,record_count:2,comp:{id:comp,land_lead_id:land,revision:0,tav:90000,tav_source:'county',house_comp_radius_mi:0.75,recommended_offer_low:65000,recommended_offer_high:75000,direct_comp_details:[]}};
 mount();expect(await screen.findByPlaceholderText('42000')).toHaveValue(90000);expect(screen.queryByText('$75,000')).toBeNull();expect(screen.getByText('Avg House ARV (0.75mi radius)')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 const body=JSON.parse(mocks.fetch.mock.calls.find(call=>call[1])![1].body);expect(body.expected_hash).toBe('a'.repeat(64));expect(body.payload).not.toHaveProperty('recommended_offer_high');
});
it('rejects malformed receipts and retains recovery instead of reporting success',async()=>{
 mocks.fetch.mockImplementation(async(_url:string,init?:RequestInit)=>({json:async()=>init?{event:{}}:snapshot}));
 mount();fireEvent.click(await screen.findByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('button',{name:'Retry saved valuation'});
 expect(screen.queryByRole('status')).toBeNull();expect(sessionStorage.length).toBe(1);
});
it('keeps unknown comp metadata null, preserves zero distance and refuses incomplete rows',async()=>{
 mount();fireEvent.change(await screen.findByPlaceholderText('123 Oak St'),{target:{value:'Example comp'}});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('alert');expect(mocks.fetch.mock.calls.filter(call=>call[1])).toHaveLength(0);
 fireEvent.change(screen.getByPlaceholderText('45000'),{target:{value:'100000'}});fireEvent.change(screen.getByPlaceholderText('0.3'),{target:{value:'0'}});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 const row=JSON.parse(mocks.fetch.mock.calls.find(call=>call[1])![1].body).payload.direct_comp_details[0];
 expect(row).toMatchObject({sqft:null,date:null,distance_mi:0,source_url:null});
});
it('conflicts clear the rejected request and reload current saved values without auto-overwriting',async()=>{
 mocks.fetch.mockImplementation(async(_url:string,init?:RequestInit)=>{
  if(init){snapshot={...snapshot,snapshot_hash:'c'.repeat(64),record_count:1,comp:{id:comp,land_lead_id:land,revision:2,tav:50000}};throw new ApiError('Another operator saved changes',409);}
  return {json:async()=>snapshot};
 });
 mount();fireEvent.click(await screen.findByRole('button',{name:'Save Comp Analysis'}));await screen.findByText('Another operator saved changes');
 await waitFor(()=>expect(screen.getByPlaceholderText('42000')).toHaveValue(50000));expect(sessionStorage.length).toBe(0);expect(mocks.fetch.mock.calls.filter(call=>call[1])).toHaveLength(1);
});
it('does not replace a saved unknown tax value with a lead reference value on reopen',async()=>{
 snapshot={...snapshot,record_count:1,comp:{id:comp,land_lead_id:land,revision:1,tav:null,avg_house_arv:200000,house_comp_count:2}};
 mount();expect(await screen.findByPlaceholderText('42000')).toHaveValue(null);
});
it('blocks future dates and fractional counts before sending',async()=>{
 mount();fireEvent.change(await screen.findByPlaceholderText('280000'),{target:{value:'200000'}});fireEvent.change(screen.getByPlaceholderText('6'),{target:{value:'2.5'}});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('alert');
 expect(mocks.fetch.mock.calls.filter(call=>call[1])).toHaveLength(0);
 fireEvent.change(screen.getByPlaceholderText('6'),{target:{value:'2'}});fireEvent.change(screen.getByLabelText('Tax assessment date'),{target:{value:'2999-01-01'}});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));expect(mocks.fetch.mock.calls.filter(call=>call[1])).toHaveLength(0);
});
