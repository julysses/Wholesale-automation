import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
const actor='00000000-0000-4000-8000-000000000001',job='00000000-0000-4000-8000-000000000002';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:mocks.admin,profile:{id:actor}})}));
import {ScoringOperations} from '@/components/lists/ScoringOperations';
const snapshot={settings:{score_threshold:70,version:1},open_count:1,jobs:[{id:job,lead_id:actor,state:'submitted',requested_model:'claude-fixture',created_at:'2026-10-12T00:00:00Z',incident:'model_outcome_unknown',task_id:null}],recent_actions:[]};
const mount=()=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><ScoringOperations/></QueryClientProvider>);
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();mocks.admin=true;mocks.fetch.mockResolvedValue({json:async()=>snapshot});});
it('does not offer recovery that resubmits uncertain model requests',async()=>{
 mount();await screen.findByText('1 unresolved scoring jobs');
 expect(screen.queryByRole('button',{name:'Finish saved scoring response'})).toBeNull();
 expect(screen.getByText(/Automatic resubmission is blocked/)).toBeTruthy();
});
it('replays the same threshold action after lost acknowledgement and remount',async()=>{
 const bodies:string[]=[];
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>snapshot};
  bodies.push(init.body as string);if(bodies.length===1)throw new Error('Connection lost');
  const body=JSON.parse(init.body as string);
  return {json:async()=>({event:{id:body.event_id,operator_id:actor,action:'threshold',payload:{expected_version:body.expected_version,score_threshold:body.score_threshold},result:{score_threshold:body.score_threshold,version:body.expected_version+1}}})};
 });
 const first=mount();fireEvent.change(await screen.findByLabelText('New scoring threshold'),{target:{value:'65'}});
 fireEvent.click(screen.getByRole('button',{name:'Save scoring threshold'}));await screen.findByText('Connection lost');
 first.unmount();mount();fireEvent.click(await screen.findByRole('button',{name:'Retry saved scoring action'}));
 await screen.findByRole('status');expect(bodies).toHaveLength(2);expect(bodies[0]).toBe(bodies[1]);
 expect(sessionStorage.getItem(`hilltop.scoring-operation.v1.${actor}`)).toBeNull();
});
it('only received jobs offer model-free completion and malformed acknowledgement stays pending',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({event:{}})}:{json:async()=>({...snapshot,jobs:[{...snapshot.jobs[0],state:'received'}]})});
 mount();fireEvent.click(await screen.findByRole('button',{name:'Finish saved scoring response'}));
 await screen.findByRole('button',{name:'Retry saved scoring action'});expect(screen.queryByRole('status')).toBeNull();
 const saved=JSON.parse(sessionStorage.getItem(`hilltop.scoring-operation.v1.${actor}`)!);expect(saved.action).toBe('complete_received');expect(saved.job_id).toBe(job);
});
it('hides controls and performs no request for non-administrators',async()=>{
 mocks.admin=false;mount();await waitFor(()=>expect(mocks.fetch).not.toHaveBeenCalled());
});
const evidence={job:{id:job,lead_id:actor,state:'submitted',requested_model:'claude-fixture',model_version:null,prompt_version:'daily-list-score-v1',model_receipt:null,input_hash:'a'.repeat(64),input_snapshot:{property:{address:'SYNTHETIC ADDRESS'}},assessment:null,error_code:null,created_at:'2026-10-12',claimed_at:'2026-10-12',received_at:null,completed_at:null},freshness:{current:false,blocked:null,input_hash:'b'.repeat(64),changed_sections:['score_threshold']},evaluation:null,outreach_authorized:false};
it('inspects evidence on demand without mutating or redispatching a held job',async()=>{
 mocks.fetch.mockImplementation(async(path:string)=>({json:async()=>path.includes('/jobs/')?evidence:snapshot}));
 mount();await screen.findByText('1 unresolved scoring jobs');expect(mocks.fetch).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Inspect scoring evidence'}));
 await screen.findByText(/Provider outcome is unconfirmed/);expect(screen.getByText(/Changed: score threshold/)).toBeTruthy();
 expect(screen.getByText(/SYNTHETIC ADDRESS/)).toBeTruthy();
 expect(mocks.fetch.mock.calls.every(call=>call[1]===undefined)).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Close scoring evidence'}));expect(screen.queryByRole('region',{name:'Scoring evidence'})).toBeNull();
});
it('rejects mismatched job evidence instead of displaying another lead',async()=>{
 mocks.fetch.mockImplementation(async(path:string)=>({json:async()=>path.includes('/jobs/')?{...evidence,job:{...evidence.job,id:actor}}:snapshot}));
 mount();fireEvent.click(await screen.findByRole('button',{name:'Inspect scoring evidence'}));
 await screen.findByText(/Scoring evidence belongs to another job/);expect(screen.queryByText(/SYNTHETIC ADDRESS/)).toBeNull();
});
it('renders rejected model text as escaped content with no active HTML',async()=>{
 const malicious='<img src=x onerror=alert(1)>';
 mocks.fetch.mockImplementation(async(path:string)=>({json:async()=>path.includes('/jobs/')?{...evidence,job:{...evidence.job,state:'review',error_code:'equity_unknown',assessment:{reason:malicious}}}:snapshot}));
 const view=mount();fireEvent.click(await screen.findByRole('button',{name:'Inspect scoring evidence'}));
 await screen.findByText(/Validation issue: equity unknown/);expect(screen.getByText(/<img src=x/)).toBeTruthy();expect(view.container.querySelector('img')).toBeNull();
});
