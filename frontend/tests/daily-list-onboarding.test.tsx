import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {it,expect,vi} from 'vitest';
const mocks=vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:true,profile:{id:'operator'}})}));
import {DailyLists} from '@/pages/DailyLists';
it('exposes property verification, paginates unresolved records and opens existing-order handoff',async()=>{
 mocks.fetch.mockImplementation(async(url:string)=>({ok:true,json:async()=>{
  if(url.includes('/captures'))return {counties:[]};
  if(url.includes('/foreclosures'))return {day:'2026-10-16',total:0,new_today:0,backlog:0,items:[]};
  if(url.includes('/propstream'))return {total:0,items:[],total_budget:{remaining_cents:5000,committed_cents:0}};
  return {day:'2026-10-16',runs:[],review_count:101,reviews:[{run_id:'run',batch_index:0,ordinal:url.endsWith('100')?100:0,source_record_id:'notice',source_key:'tx-dallas-pre_foreclosure',property_address:'Synthetic property',source_fingerprint:'a'.repeat(32),source_url:'https://www.dallascounty.org/test',review_reason:'verify_identity'}]};
 }}));
 render(<MemoryRouter><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><DailyLists/></QueryClientProvider></MemoryRouter>);
 await screen.findByText(/101 source records/);
 fireEvent.click(screen.getByRole('button',{name:'Open property reviews'}));
 expect(screen.getByRole('button',{name:'Save verified association'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Next reviews'}));
 await waitFor(()=>expect(mocks.fetch).toHaveBeenCalledWith('/api/operations/lists?offset=100'));
 fireEvent.click(screen.getByRole('button',{name:'Open PropStream controls'}));
 expect(screen.getByRole('button',{name:'Hide PropStream controls'})).toBeInTheDocument();
 expect(mocks.fetch.mock.calls.every(([url])=>!url.includes('/actions')&&!url.includes('/batches'))).toBe(true);
});
