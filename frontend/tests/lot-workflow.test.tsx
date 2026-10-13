import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
const actor='00000000-0000-4000-8000-000000000001',lead='00000000-0000-4000-8000-000000000002',evaluation='00000000-0000-4000-8000-000000000003',handoff='00000000-0000-4000-8000-000000000004',land='00000000-0000-4000-8000-000000000005',task='00000000-0000-4000-8000-000000000006';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),limit:vi.fn(),admin:true,approved:true}));
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),apiFetch:mocks.fetch}));
vi.mock('@/lib/supabase',()=>({supabase:{from:()=>({select:()=>({eq:()=>({order:()=>({limit:mocks.limit})})})})}}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({profile:{id:actor},isAdmin:mocks.admin,isApproved:mocks.approved})}));
import {LotOperations} from '@/components/lists/LotOperations';
import {LotInbox} from '@/components/land/LotInbox';
const candidate={id:land,lead_id:lead,address_std:'SYNTHETIC LOT',city:'Dallas',county:'Dallas',parcel_id:'SYNTHETIC PARCEL',is_vacant_lot:null,input_hash:'a'.repeat(64),blocked:null,evaluation_id:evaluation,route:'underwrite_lot',score_current:false};
const received={id:handoff,lead_id:lead,land_lead_id:land,task_id:task,evaluation_id:evaluation,operator_id:actor,assigned_to:actor,created_at:'2026-10-12',acknowledged_by:null,acknowledged_at:null,address_std:'SYNTHETIC LOT',county:'Dallas',current:true,evidence_url:'https://example.invalid/parcel',review_notes:'Reviewed official parcel',score:75,reasons:{needs_to_sell:'unknown'},flags:['equity_unknown'],scoring_input:{property:{address:'SYNTHETIC LOT'}}};
const mount=(content:React.ReactNode)=><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}>{content}</QueryClientProvider>;
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();mocks.admin=true;mocks.approved=true;mocks.limit.mockResolvedValue({data:[],error:null});mocks.fetch.mockResolvedValue({json:async()=>({count:1,candidates:[candidate]})});});
async function reviewForm(){
 fireEvent.change(await screen.findByLabelText('Reviewed classification for SYNTHETIC LOT'),{target:{value:'lot'}});
 fireEvent.change(screen.getByLabelText('Official lot evidence URL'),{target:{value:'https://example.invalid/parcel'}});
 fireEvent.change(screen.getByLabelText('Lot review notes'),{target:{value:'Reviewed official parcel'}});
 fireEvent.click(screen.getByRole('checkbox'));
}
it('requires explicit classification evidence and confirmation, then correlates its saved receipt',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>({count:1,candidates:[candidate]})};
  const body=JSON.parse(init.body as string);const {request_id,...fields}=body;
  return {json:async()=>({review:{id:request_id,operator_id:actor,...fields}})};
 });
 render(mount(<LotOperations/>));expect(await screen.findByRole('button',{name:'Save lot classification'})).toBeDisabled();
 await reviewForm();fireEvent.click(screen.getByRole('button',{name:'Save lot classification'}));await screen.findByRole('status');
 const request=JSON.parse(mocks.fetch.mock.calls.find(call=>call[1])![1].body);expect(request.lead_id).toBe(lead);expect(request.input_hash).toBe('a'.repeat(64));expect(request.is_vacant_lot).toBe(true);expect(request.operator_id).toBeUndefined();
 expect(screen.getByRole('button',{name:'Send to underwriting inbox'})).toBeDisabled();
});
it('retains the exact review after lost acknowledgement and remount',async()=>{
 const bodies:string[]=[];mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>({count:1,candidates:[candidate]})};bodies.push(init.body as string);
  if(bodies.length===1)throw new Error('Connection lost');const {request_id,...fields}=JSON.parse(init.body as string);
  return {json:async()=>({review:{id:request_id,operator_id:actor,...fields}})};
 });
 const first=render(mount(<LotOperations/>));await reviewForm();fireEvent.click(screen.getByRole('button',{name:'Save lot classification'}));await screen.findByText('Connection lost');first.unmount();
 render(mount(<LotOperations/>));fireEvent.click(await screen.findByRole('button',{name:'Retry saved lot action'}));await screen.findByRole('status');expect(bodies[0]).toBe(bodies[1]);expect(sessionStorage.getItem(`hilltop.lot-action.v1.${actor}`)).toBeNull();
});
it('routes only a current lot evaluation and keeps malformed handoff acknowledgement pending',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({handoff:{}})}:{json:async()=>({count:1,candidates:[{...candidate,is_vacant_lot:true,score_current:true}]})});
 render(mount(<LotOperations/>));fireEvent.click(await screen.findByRole('button',{name:'Send to underwriting inbox'}));await screen.findByRole('button',{name:'Retry saved lot action'});
 expect(screen.queryByRole('status')).toBeNull();const saved=JSON.parse(sessionStorage.getItem(`hilltop.lot-action.v1.${actor}`)!);expect(saved.body.evaluation_id).toBe(evaluation);expect(saved.body.assigned_to).toBe(actor);
});
it('does not fetch administrator controls for a regular operator',async()=>{
 mocks.admin=false;render(mount(<LotOperations/>));await waitFor(()=>expect(mocks.fetch).not.toHaveBeenCalled());expect(mocks.limit).not.toHaveBeenCalled();
});
it('requires opening the exact destination and confirming receipt, with no completed-underwriting claim',async()=>{
 const open=vi.fn().mockResolvedValue(undefined);mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({handoff:{...received,acknowledged_by:actor,acknowledged_at:'2026-10-12T18:00:00Z'},outreach_authorized:false})}:{json:async()=>({count:1,handoffs:[received]})});
 mocks.admin=false;render(mount(<LotInbox onOpen={open}/>));const ack=await screen.findByRole('button',{name:'Acknowledge underwriting receipt'});expect(ack).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Open linked land record'}));await waitFor(()=>expect(screen.getByRole('checkbox')).toBeEnabled());expect(open).toHaveBeenCalledWith(land,lead);
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(ack);await screen.findByText(/Underwriting remains pending/);
 const post=mocks.fetch.mock.calls.find(call=>call[1]);expect(post![0]).toBe(`/api/land-underwriting/handoffs/${handoff}/acknowledge`);expect(post![1].body).toBeUndefined();
});
it('failed destination opening cannot enable receipt acknowledgement',async()=>{
 mocks.fetch.mockResolvedValue({json:async()=>({count:1,handoffs:[received]})});const open=vi.fn().mockRejectedValue(new Error('Destination missing'));
 render(mount(<LotInbox onOpen={open}/>));fireEvent.click(await screen.findByRole('button',{name:'Open linked land record'}));await screen.findByText('Destination missing');expect(screen.getByRole('button',{name:'Acknowledge underwriting receipt'})).toBeDisabled();
});
it('acknowledgement for a different destination stays unconfirmed',async()=>{
 const action={kind:'acknowledge',id:handoff,lead_id:lead,land_lead_id:land,task_id:task};sessionStorage.setItem(`hilltop.lot-action.v1.${actor}`,JSON.stringify(action));
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({handoff:{...received,land_lead_id:actor,acknowledged_by:actor,acknowledged_at:'2026-10-12'},outreach_authorized:false})}:{json:async()=>({count:1,handoffs:[received]})});
 render(mount(<LotInbox onOpen={vi.fn()}/>));fireEvent.click(await screen.findByRole('button',{name:'Retry saved lot action'}));await screen.findByText('Receiving acknowledgement is unconfirmed.');expect(sessionStorage.getItem(`hilltop.lot-action.v1.${actor}`)).not.toBeNull();expect(screen.queryByRole('status')).toBeNull();
});
it('accepts and acknowledges a worker handoff without attributing initiation to a human',async()=>{
 const automatic={...received,operator_id:null,initiation:'worker'};
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({handoff:{...automatic,acknowledged_by:actor,acknowledged_at:'2026-10-12T21:00:00Z'},outreach_authorized:false})}:{json:async()=>({count:1,handoffs:[automatic]})});
 const onOpen=vi.fn().mockResolvedValue(undefined);render(mount(<LotInbox onOpen={onOpen}/>));
 await screen.findByText('Automatically routed after administrator lot review.');
 fireEvent.click(screen.getByRole('button',{name:'Open linked land record'}));
 await waitFor(()=>expect(screen.getByRole('checkbox')).toBeEnabled());fireEvent.click(screen.getByRole('checkbox'));
 fireEvent.click(screen.getByRole('button',{name:'Acknowledge underwriting receipt'}));
 expect(await screen.findByRole('status')).toHaveTextContent('Underwriting remains pending');
 expect(onOpen).toHaveBeenCalledWith(land,lead);
});
