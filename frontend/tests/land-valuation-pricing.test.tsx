import {fireEvent,render,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
import type {LandLead,LandComps} from '@/types';
const mocks=vi.hoisted(()=>({from:vi.fn(),insert:vi.fn(),update:vi.fn(),eq:vi.fn(),select:vi.fn(),single:vi.fn()}));
vi.mock('@/lib/supabase',()=>({supabase:{from:mocks.from}}));
import {QuickCompCalculator} from '@/components/land/QuickCompCalculator';
const lead={id:'land-fixture',property_address:'SYNTHETIC LOT',tav:100000,mao:75000,offer_price:65000} as LandLead;
const mount=(existing?:LandComps)=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{mutations:{retry:false}}})}><QuickCompCalculator lead={lead} existing={existing}/></QueryClientProvider>);
beforeEach(()=>{vi.resetAllMocks();mocks.from.mockReturnValue({insert:mocks.insert,update:mocks.update});mocks.insert.mockReturnValue({select:mocks.select});mocks.update.mockReturnValue({eq:mocks.eq});mocks.eq.mockReturnValue({eq:mocks.eq,select:mocks.select});mocks.select.mockReturnValue({single:mocks.single});mocks.single.mockResolvedValue({data:{id:'comp-saved',land_lead_id:lead.id},error:null});});
it('retains valuation calculations but never creates an offer range or writes a lead price or stage',async()=>{
 mount();fireEvent.change(screen.getByPlaceholderText('280000'),{target:{value:'200000'}});
 expect(screen.getByText('$30,000')).toBeTruthy();expect(screen.queryByText('Recommended Offer Range')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 const payload=mocks.insert.mock.calls[0][0];expect(payload.arv_15pct_value).toBe(30000);expect(payload.tav).toBe(100000);
 for(const key of ['recommended_offer_low','recommended_offer_high','mao','offer_price'])expect(payload).not.toHaveProperty(key);
 expect(mocks.from.mock.calls.map(call=>call[0])).toEqual(['land_comps']);
});
it('editing historical valuations leaves stored offer fields untouched',async()=>{
 mocks.single.mockResolvedValue({data:{id:'comp-existing',land_lead_id:lead.id},error:null});
 mount({id:'comp-existing',land_lead_id:lead.id,created_at:'2026-10-12',tav:100000,recommended_offer_low:65000,recommended_offer_high:75000});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 expect(mocks.update.mock.calls[0][0]).not.toHaveProperty('recommended_offer_high');expect(mocks.update.mock.calls[0][0]).not.toHaveProperty('recommended_offer_low');expect(mocks.eq).toHaveBeenCalledWith('id','comp-existing');
 expect(screen.queryByText('$75,000')).toBeNull();
});
it('failed valuation storage has an explicit error and no success or lead update',async()=>{
 mocks.single.mockResolvedValue({error:new Error('Storage unavailable')});mount();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('alert');
 expect(screen.queryByRole('status')).toBeNull();expect(mocks.from.mock.calls.map(call=>call[0])).toEqual(['land_comps']);
});

it('rejects a zero-row acknowledgement and reuses a confirmed record for subsequent edits',async()=>{
 mocks.single.mockResolvedValueOnce({data:null,error:null});const first=mount();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('alert');expect(screen.queryByRole('status')).toBeNull();
 first.unmount();vi.clearAllMocks();mount();
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 fireEvent.change(screen.getByPlaceholderText('42000'),{target:{value:'90000'}});
 fireEvent.click(screen.getByRole('button',{name:'Save Comp Analysis'}));await screen.findByRole('status');
 expect(mocks.insert).toHaveBeenCalledTimes(1);expect(mocks.update).toHaveBeenCalledTimes(1);expect(mocks.eq).toHaveBeenCalledWith('id','comp-saved');
});
