import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
const actor='00000000-0000-4000-8000-000000000001';
const lead='00000000-0000-4000-8000-000000000002';
const revision='00000000-0000-4000-8000-000000000003';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({profile:{id:actor},isAdmin:mocks.admin,loading:false,error:null})}));
import { OfferReview } from '@/components/offers/OfferReview';
import { pendingOffer,writeOffer,type OfferDecision } from '@/lib/offerReview';
const terms={price:'125000.00',closing_date:'2099-12-31',expires_at:'2099-10-01T00:00:00Z',recipient:'test@example.invalid',channel:'email' as const,conditions:'Subject to reviewed contract'};
const base={lead_id:lead,version:1,revision:{id:revision,lead_id:lead,operator_id:actor,action:'draft',expected_version:0,revision_id:revision,terms,created_at:'2026-10-12T00:00:00Z'},approval:null,approved:false,outbound_enabled:false};
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks();mocks.admin=true;mocks.fetch.mockResolvedValue({json:async()=>base});});
it('requires exact saved-term acknowledgement and blocks approval during edits',async()=>{
 render(<OfferReview leadId={lead}/>);
 await screen.findByText('$125000.00');
 const approve=screen.getByRole('button',{name:'Approve saved terms'});
 expect(approve).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox'));
 expect(approve).toBeEnabled();
 fireEvent.change(screen.getByLabelText('Offer price'),{target:{value:'130000'}});
 expect(approve).toBeDisabled();
 expect(screen.getByText(/Unsaved edits cannot be approved/)).toBeTruthy();
});
it('records approval only after exact receipt, with no send control',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>base};
  const body=JSON.parse(init.body as string);
  const event={id:body.request_id,lead_id:lead,operator_id:actor,action:body.action,expected_version:1,revision_id:revision,terms:null,created_at:'2026-10-12T00:00:00Z'};
  return {json:async()=>({event,current:{...base,version:2,approval:event,approved:true}})};
 });
 render(<OfferReview leadId={lead}/>);await screen.findByText('$125000.00');
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Approve saved terms'}));
 await screen.findByText(/Review version 2 · Approved/);
 expect(screen.getByRole('button',{name:'Revoke approval'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:/Send offer/})).toBeNull();
});
it('retains exact identity across lost acknowledgement and remount',async()=>{
 let attempts=0;const seen:string[]=[];
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>base};
  const body=JSON.parse(init.body as string);seen.push(body.request_id);attempts++;
  if(attempts===1)throw new Error('Connection lost');
  const event={id:body.request_id,lead_id:lead,operator_id:actor,action:'approve',expected_version:1,revision_id:revision,terms:null,created_at:'2026-10-12T00:00:00Z'};
  return {json:async()=>({event,current:{...base,version:2,approval:event,approved:true}})};
 });
 const first=render(<OfferReview leadId={lead}/>);await screen.findByText('$125000.00');
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Approve saved terms'}));
 await screen.findByText('Connection lost');first.unmount();
 render(<OfferReview leadId={lead}/>);await screen.findByRole('button',{name:'Retry exact decision'});
 expect(screen.getByLabelText('Offer price')).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Retry exact decision'}));
 await screen.findByText(/Review version 2 · Approved/);expect(seen[0]).toBe(seen[1]);
 expect(pendingOffer(actor,lead)).toBeNull();
});
it('non-admin cannot load or approve offers',()=>{mocks.admin=false;render(<OfferReview leadId={lead}/>);expect(mocks.fetch).not.toHaveBeenCalled();});
it('rejects mismatched receipts and preserves recovery reference',async()=>{
 const decision:OfferDecision={request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve'};
 mocks.fetch.mockResolvedValue({json:async()=>({event:{...base.revision,action:'approve',terms:null},current:base})});
 await expect(writeOffer(actor,lead,decision)).rejects.toThrow();expect(pendingOffer(actor,lead)?.request_id).toBe(decision.request_id);
});
it('definite conflict clears pending reference but never reports success',async()=>{
 mocks.fetch.mockRejectedValue(new ApiError('Conflict',409));
 const decision:OfferDecision={request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve'};
 await expect(writeOffer(actor,lead,decision)).rejects.toThrow('Conflict');expect(pendingOffer(actor,lead)).toBeNull();
});
it('normalizes equivalent expiry timestamps without losing a confirmed draft receipt',async()=>{
 const id=crypto.randomUUID();
 const decision:OfferDecision={request_id:id,revision_id:id,expected_version:0,action:'draft',terms:{...terms,price:'00125000.00',expires_at:'2099-10-01T00:00:00.000Z'}};
 mocks.fetch.mockImplementation(async(_path:string,init:RequestInit)=>{
  const body=JSON.parse(init.body as string);
  const event={...base.revision,id,revision_id:id,terms:{...body.terms,expires_at:'2099-10-01T00:00:00Z'}};
  return {json:async()=>({event,current:{...base,revision:event}})};
 });
 const saved=await writeOffer(actor,lead,decision);
 expect(saved.revision?.terms?.price).toBe('125000.00');expect(pendingOffer(actor,lead)).toBeNull();
});
it('revocation receipt removes approved status without sending',async()=>{
 const approval={...base.revision,id:crypto.randomUUID(),action:'approve',terms:null};
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>({...base,version:2,approval,approved:true})};
  const body=JSON.parse(init.body as string);
  const event={...approval,id:body.request_id,action:'revoke',expected_version:2};
  return {json:async()=>({event,current:{...base,version:3}})};
 });
 render(<OfferReview leadId={lead}/>);await screen.findByText(/Review version 2 · Approved/);
 fireEvent.click(screen.getByRole('button',{name:'Revoke approval'}));
 await screen.findByText(/Review version 3 · Not approved/);
 expect(screen.getByRole('button',{name:'Revoke approval'})).toBeDisabled();
});
