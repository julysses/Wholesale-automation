import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
const db = vi.hoisted(() => ({read: vi.fn()}));
vi.mock('@/lib/supabase', () => ({supabase: {from: (table: string) => ({
 select: () => ({eq: (column: string, id: string) => ({single: () => db.read(table,column,id)})}),
})}}));
vi.mock('@/hooks/useLeads', async original => ({
 ...await original<typeof import('@/hooks/useLeads')>(),
 useLeads: () => ({data:{data:[],count:17449},isLoading:false,error:null}),
}));
vi.mock('@/hooks/useDeals', () => ({useCreateDeal: () => ({mutateAsync:vi.fn()})}));
vi.mock('@/hooks/useAIAgent', () => ({useLeadQualifier: () => ({qualify:vi.fn()})}));
vi.mock('@/components/leads/OutreachTimeline', () => ({OutreachTimeline: ({leadId}:{leadId:string}) => <p>History for {leadId}</p>}));
import { Leads } from '@/pages/Leads';
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const lead=(id:string) => ({id,property_address:id===A?'First inquiry address':'Second inquiry address',city:'Dallas',state:'TX',status:'new',owner_first_name:'Test',internal_notes:'Saved note',created_at:'2026-10-16',updated_at:'2026-10-16'});
function Harness(){
 const location=useLocation(),navigate=useNavigate();
 return <><output aria-label="Current location">{location.search}</output><button onClick={()=>navigate(`/leads?lead=${B}`)}>Open second inquiry</button><Leads /></>;
}
function show(query=`?lead=${A}&status=new&search=keep`){
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/leads'+query]}><Harness /></MemoryRouter></QueryClientProvider>);
}
beforeEach(()=>{vi.clearAllMocks();db.read.mockImplementation(async (_table,_column,id)=>({data:lead(id),error:null}));});
it('opens the exact record outside the list page and preserves other filters on close',async()=>{
 show(); expect(await screen.findByLabelText('Internal Notes')).toHaveValue('Saved note');
 expect(db.read).toHaveBeenCalledWith('leads','id',A);
 expect(screen.getByRole('heading',{name:'First inquiry address'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Activity Timeline',exact:true}));
 expect(screen.getByText(`History for ${A}`)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Details',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Cancel',exact:true}));
 await waitFor(()=>expect(screen.queryByLabelText('Internal Notes')).not.toBeInTheDocument());
 expect(screen.getByLabelText('Current location')).toHaveTextContent('?status=new&search=keep');
});
it('rejects malformed links without a database request',()=>{
 show('?lead=not-a-uuid'); expect(screen.getByRole('alert')).toHaveTextContent('This lead link is invalid'); expect(db.read).not.toHaveBeenCalled();
});
it('shows an unavailable record without choosing another lead and supports explicit read retry',async()=>{
 db.read.mockResolvedValueOnce({data:null,error:{message:'private backend detail'}}); show();
 expect(await screen.findByRole('alert')).toHaveTextContent('This lead could not be opened');
 expect(screen.queryByText('private backend detail')).not.toBeInTheDocument(); expect(screen.queryByLabelText('Internal Notes')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Retry opening lead'}));
 expect(await screen.findByLabelText('Internal Notes')).toHaveValue('Saved note'); expect(db.read).toHaveBeenCalledTimes(2);
});
it('does not carry an unsaved draft into a different linked lead',async()=>{
 show(); fireEvent.change(await screen.findByLabelText('Internal Notes'),{target:{value:'Unsaved first inquiry draft'}});
 fireEvent.click(screen.getByRole('button',{name:'Open second inquiry'})); await screen.findByRole('heading',{name:'Second inquiry address'});
 expect(screen.getByLabelText('Internal Notes')).toHaveValue('Saved note');
});
it('ignores a late first-record response after the link changes',async()=>{
 let resolveFirst!: (value:unknown)=>void;
 db.read.mockImplementation((_table,_column,id)=>id===A?new Promise(resolve=>{resolveFirst=resolve;}):Promise.resolve({data:lead(id),error:null}));
 show(); expect(screen.getByText('Opening the linked inquiry…')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Open second inquiry'})); await screen.findByRole('heading',{name:'Second inquiry address'});
 resolveFirst({data:lead(A),error:null});
 await waitFor(()=>expect(screen.queryByRole('heading',{name:'First inquiry address'})).not.toBeInTheDocument());
 expect(screen.getByRole('heading',{name:'Second inquiry address'})).toBeInTheDocument();
});
