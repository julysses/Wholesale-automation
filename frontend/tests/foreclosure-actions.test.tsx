import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:mocks.admin})}));
import {ForeclosureActions} from '@/components/lists/ForeclosureActions';
const item={run_id:'one',batch_index:0,ordinal:0,source_record_id:'123',source_key:'tx-dallas-pre_foreclosure',county:'Dallas',property_address:null,source_url:'https://dallas.tx.publicsearch.us/doc/123',source_fingerprint:'a'.repeat(32),review_reason:'verify_property',new_today:true,indexed_address:'County index location',filed_date:'2026-10-12',auction_date:'2026-11-03'};
function show(compact=false){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<MemoryRouter><QueryClientProvider client={client}><ForeclosureActions compact={compact}/></QueryClientProvider></MemoryRouter>);return client;}
beforeEach(()=>{mocks.admin=true;vi.resetAllMocks();mocks.fetch.mockResolvedValue({json:async()=>({day:'2026-10-13',total:51,new_today:50,backlog:1,items:[item]})});});
it('surfaces new notices and supports pagination and county reset',async()=>{
 show();expect(await screen.findByText(/50 new notices to review/)).toBeVisible();
 expect(screen.getByText('HIGH PRIORITY · NEW TODAY')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Next notices'}));
 await waitFor(()=>expect(mocks.fetch).toHaveBeenCalledWith('/api/operations/lists/foreclosures?offset=50'));
 fireEvent.change(await screen.findByLabelText('Foreclosure county'),{target:{value:'Collin'}});
 await waitFor(()=>expect(mocks.fetch).toHaveBeenCalledWith('/api/operations/lists/foreclosures?offset=0&county=Collin'));
});
it('dashboard links directly to the app review queue',async()=>{show(true);expect(await screen.findByRole('link',{name:'Review foreclosure action items'})).toHaveAttribute('href','/daily-lists');});
it('does not fetch restricted data for non-admins',()=>{mocks.admin=false;show();expect(mocks.fetch).not.toHaveBeenCalled();expect(screen.queryByRole('region')).toBeNull();});
it('reports unavailable data instead of a zero count on failure',async()=>{mocks.fetch.mockRejectedValue(new Error('offline'));show();expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');expect(screen.queryByText(/0 new notices/)).toBeNull();});

async function openReview(){
 fireEvent.click((await screen.findByText('HIGH PRIORITY · NEW TODAY')).closest('summary')!);
 fireEvent.click(screen.getByRole('button',{name:'Review notice 123'}));
}
it('opens the exact notice evidence form without saving or treating an indexed address as verified',async()=>{
 show();await openReview();
 expect(screen.getByRole('link',{name:'Official source record'})).toHaveAttribute('href',item.source_url);
 expect(screen.getByLabelText('Verified property street address')).toHaveValue('');
 expect(screen.getByRole('button',{name:'Save verified association'})).toBeDisabled();
 expect(screen.getByLabelText(/currently active distress signal/)).not.toBeChecked();
 expect(mocks.fetch.mock.calls.every(([,options])=>!options)).toBe(true);
 fireEvent.change(screen.getByLabelText('Foreclosure county'),{target:{value:'Collin'}});
 expect(screen.queryByLabelText('Verified property street address')).toBeNull();
});
it('submits the selected receipt identity and refreshes the queues after explicit evidence confirmation',async()=>{
 show();await openReview();
 for(const [label,value] of [
  ['Verified property street address','1 Verified Site'],['Verified property city (Texas)','Dallas'],
  ['Verified property ZIP','75201'],['Official county or title evidence URL','https://www.dallascad.org/synthetic'],
  ['Evidence notes: explain the account-to-property match and current status','Official parcel independently matched; current sale unverified.'],
 ])fireEvent.change(screen.getByLabelText(label),{target:{value}});
 fireEvent.click(screen.getByLabelText(/I verified the exact property/));
 mocks.fetch.mockImplementation(async(path:string)=>({json:async()=>path.endsWith('/resolve')?{resolved:true}:{day:'2026-10-13',total:0,new_today:0,backlog:0,items:[]}}));
 fireEvent.click(screen.getByRole('button',{name:'Save verified association'}));
 await waitFor(()=>expect(screen.queryByLabelText('Verified property street address')).toBeNull());
 const saves=mocks.fetch.mock.calls.filter(([path])=>path==='/api/operations/lists/resolve');
 expect(saves).toHaveLength(1);
 const body=JSON.parse(saves[0][1].body);
 expect(body).toMatchObject({run_id:item.run_id,batch_index:0,ordinal:0,active_signal:false,review:{source_fingerprint:item.source_fingerprint}});
 expect(mocks.fetch.mock.calls.filter(([path])=>path==='/api/operations/lists/foreclosures?offset=0').length).toBe(2);
});
it('closes stale evidence fields when the selected source fingerprint changes',async()=>{
 const client=show();await openReview();
 fireEvent.change(screen.getByLabelText('Verified property street address'),{target:{value:'Unsaved review'}});
 mocks.fetch.mockResolvedValue({json:async()=>({day:'2026-10-13',total:1,new_today:1,backlog:0,items:[{...item,source_fingerprint:'b'.repeat(32)}]})});
 await client.invalidateQueries({queryKey:['foreclosure-actions']});
 await waitFor(()=>expect(screen.queryByLabelText('Verified property street address')).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Review notice 123'}));
 expect(screen.getByLabelText('Verified property street address')).toHaveValue('');
});
