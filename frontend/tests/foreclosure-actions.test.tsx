import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:mocks.admin})}));
import {ForeclosureActions} from '@/components/lists/ForeclosureActions';
const item={run_id:'one',batch_index:0,ordinal:0,source_record_id:'123',source_key:'tx-dallas-pre_foreclosure',county:'Dallas',property_address:null,source_url:'https://dallas.tx.publicsearch.us/doc/123',source_fingerprint:'a'.repeat(32),review_reason:'verify_property',new_today:true,indexed_address:'County index location',filed_date:'2026-10-12',auction_date:'2026-11-03'};
function show(compact=false){render(<MemoryRouter><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><ForeclosureActions compact={compact}/></QueryClientProvider></MemoryRouter>);}
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
