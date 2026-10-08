import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {render,screen,cleanup,renderHook,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import type {ReactNode} from 'react';
const db=vi.hoisted(()=>({calls:[] as {table:string;filters:unknown[]}[],failure:false,metrics:{total_calls:0,conversations:0,interested:0,hot_leads:0,appointments:3,appointments_completed:3,contracts_closed:0,closed_fees:0}}));
vi.mock('@/lib/supabase',()=>({supabase:{from:(table:string)=>{
 const row={table,filters:[] as unknown[]};db.calls.push(row);
 const q:Record<string,unknown>={select:()=>q,not:(...args:unknown[])=>{row.filters.push(['not',...args]);return q;},in:(...args:unknown[])=>{row.filters.push(['in',...args]);return q;},eq:(...args:unknown[])=>{row.filters.push(['eq',...args]);return q;},single:async()=>({data:db.metrics,error:db.failure?new Error('Offline'):null}),then:(resolve:(value:unknown)=>void)=>resolve({count:0,error:db.failure?new Error('Offline'):null})};
 return q;
}}}));
import {loadWorkflowEvidence,useWorkflowStep} from '@/hooks/useWorkflowStep';
import {FunnelPanel} from '@/components/dashboard/FunnelPanel';
function wrapper({children}:{children:ReactNode}) {return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{children}</QueryClientProvider>;}
beforeEach(()=>{db.calls=[];db.failure=false;localStorage.clear();db.metrics.contracts_closed=0;db.metrics.closed_fees=0;});
afterEach(cleanup);
it('uses reportable records and active appointments or actual closed deals for milestones',async()=>{
 const data=await loadWorkflowEvidence();expect(data.hasDeals).toBe(false);expect(data.hasAppointments).toBe(false);
 expect(db.calls.every(row=>row.table.startsWith('reportable_'))).toBe(true);
 expect(db.calls.find(row=>row.table==='reportable_appointments')?.filters).toContainEqual(['in','status',['scheduled','confirmed','completed']]);
 expect(db.calls.find(row=>row.table==='reportable_deals')?.filters).toContainEqual(['eq','stage','closed']);
 const {result}=renderHook(()=>useWorkflowStep(),{wrapper});await waitFor(()=>expect(result.current.isLoading).toBe(false));
 expect(result.current.completedSteps.has(1)).toBe(false);expect(result.current.completedSteps.has(8)).toBe(false);expect(result.current.completedSteps.has(11)).toBe(false);
});
it('does not convert failed workflow reads into evidence of completion',async()=>{
 db.failure=true;await expect(loadWorkflowEvidence()).rejects.toThrow('Offline');
});
it('completed appointments do not become contracts or fee revenue',async()=>{
 render(<FunnelPanel/>,{wrapper});await screen.findByText('Contracts Closed');
 expect(screen.queryByText('Recorded Closed Fees')).not.toBeInTheDocument();
 expect(screen.getByText('Contracts Closed').closest('div.flex-1')?.textContent).toContain('0 /');
 expect(db.calls.some(row=>row.table==='business_funnel_metrics')).toBe(true);
});
it('shows recorded fees rather than a fixed fee times appointment count',async()=>{
 db.metrics.contracts_closed=1;db.metrics.closed_fees=7200;
 render(<FunnelPanel/>,{wrapper});await screen.findByText('Recorded Closed Fees');expect(screen.getByText('$7,200')).toBeInTheDocument();expect(screen.queryByText('$30,000')).not.toBeInTheDocument();
});
it('shows an error when funnel evidence fails instead of successful zero totals',async()=>{
 db.failure=true;render(<FunnelPanel/>,{wrapper});expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');expect(screen.queryByText('Contracts Closed')).not.toBeInTheDocument();
});
