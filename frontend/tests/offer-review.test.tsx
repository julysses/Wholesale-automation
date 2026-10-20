vi.mock('@/components/offers/OfferHistory',()=>({OfferHistory:()=>null}));
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
import { pendingOffer,writeOffer,reconcileLegacyOffer,type OfferDecision } from '@/lib/offerReview';
const terms={price:'125000.00',closing_date:'2099-12-31',expires_at:'2099-10-01T00:00:00Z',recipient:'test@example.invalid',channel:'email' as const,conditions:'Subject to reviewed contract'};
const base={lead_id:lead,version:1,revision:{id:revision,lead_id:lead,operator_id:actor,action:'draft',expected_version:0,revision_id:revision,terms,created_at:'2026-10-12T00:00:00Z'},approval:null,approved:false,outbound_enabled:false,binding_valid:true,content:{revision_id:revision,property_snapshot:{property_address:'SYNTHETIC PROPERTY',city:'Dallas',state:'TX',zip_code:null},renderer_version:'offer-summary-v1',subject:'Offer terms',body:'SYNTHETIC PROPERTY — $125000.00',created_at:'2026-10-12T00:00:00Z'}};
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
 const decision:OfferDecision={request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve',reviewed_content_id:revision};
 mocks.fetch.mockResolvedValue({json:async()=>({event:{...base.revision,action:'approve',terms:null},current:base})});
 await expect(writeOffer(actor,lead,decision)).rejects.toThrow();expect(pendingOffer(actor,lead)?.request_id).toBe(decision.request_id);
});
it('definite conflict clears pending reference but never reports success',async()=>{
 mocks.fetch.mockRejectedValue(new ApiError('Conflict',409));
 const decision:OfferDecision={request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve',reviewed_content_id:revision};
 await expect(writeOffer(actor,lead,decision)).rejects.toThrow('Conflict');expect(pendingOffer(actor,lead)).toBeNull();
});
it('normalizes equivalent expiry timestamps without losing a confirmed draft receipt',async()=>{
 const id=crypto.randomUUID();
 const decision:OfferDecision={request_id:id,revision_id:id,expected_version:0,action:'draft',terms:{...terms,price:'00125000.00',expires_at:'2099-10-01T00:00:00.000Z'}};
 mocks.fetch.mockImplementation(async(_path:string,init:RequestInit)=>{
  const body=JSON.parse(init.body as string);
  const event={...base.revision,id,revision_id:id,terms:{...body.terms,expires_at:'2099-10-01T00:00:00Z'}};
  return {json:async()=>({event,current:{...base,revision:event,content:{...base.content,revision_id:id}}})};
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

it('shows immutable preview and blocks stale or unbound property approval',async()=>{
 mocks.fetch.mockResolvedValue({json:async()=>({...base,binding_valid:false})});
 render(<OfferReview leadId={lead}/>);
 await screen.findByText('SYNTHETIC PROPERTY — $125000.00');
 expect(screen.getByRole('button',{name:'Approve saved terms'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Save new revision'})).toBeEnabled();
 expect(screen.getByText(/Property details changed/)).toBeTruthy();
});


it('saves a typed calendar date with the exact draft and does not approve it',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>({...base,version:0,revision:null,content:null,binding_valid:false})};
  const body=JSON.parse(init.body as string);
  expect(body.action).toBe('draft');
  expect(body.terms.closing_date).toBe('2099-12-31');
  const event={...base.revision,id:body.request_id,revision_id:body.request_id,terms:body.terms};
  return {json:async()=>({event,current:{...base,revision:event,content:{...base.content,revision_id:body.request_id}}})};
 });
 render(<OfferReview leadId={lead}/>);
 await screen.findByText(/Review version 0/);
 for(const [label,value] of Object.entries({'Offer price':'100.00','Closing date':'2099-12-31','Expiry (include time zone)':'2099-10-01T00:00:00Z','Recipient':'Synthetic QA','Conditions':'Not a real offer'})){
  fireEvent.change(screen.getByLabelText(label),{target:{value}});
 }
 fireEvent.click(screen.getByRole('button',{name:'Save new revision'}));
 await screen.findByText(/Decision recorded/);
 expect(screen.getByText(/Review version 1 · Not approved/)).toBeTruthy();
 expect(screen.getByRole('button',{name:'Approve saved terms'})).toBeDisabled();
});

it.each(['2099-02-29','2099-04-31','12/31/2099',''])('rejects invalid or ambiguous closing date %s before posting',async value=>{
 render(<OfferReview leadId={lead}/>);await screen.findByText('$125000.00');
 fireEvent.change(screen.getByLabelText('Closing date'),{target:{value}});
 fireEvent.click(screen.getByRole('button',{name:'Save new revision'}));
 await screen.findByText('Enter a real closing date as YYYY-MM-DD.');
 expect(mocks.fetch.mock.calls.every(call=>!call[1])).toBe(true);
});


it('reconciles a legacy approval locally without resending or changing server history',async()=>{
 const old=JSON.stringify({request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve'});
 sessionStorage.setItem(`hilltop.offer-review.v1.${actor}.${lead}`,old);
 render(<OfferReview leadId={lead}/>);
 await screen.findByText('$125000.00');
 expect(screen.getByLabelText('Offer price')).toBeDisabled();
 expect(screen.getByRole('button',{name:'Approve saved terms'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Reload saved status and clear obsolete retry'}));
 await screen.findByText(/Obsolete local retry removed/);
 expect(pendingOffer(actor,lead)).toBeNull();
 expect(mocks.fetch.mock.calls.every(call=>!call[1])).toBe(true);
 expect(screen.getByLabelText('Offer price')).toBeEnabled();
 expect(screen.getByRole('button',{name:'Approve saved terms'})).toBeDisabled();
});

it('keeps a legacy retry if server reconciliation fails or local pending state changes',async()=>{
 const key=`hilltop.offer-review.v1.${actor}.${lead}`;
 const old=JSON.stringify({request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve'});
 sessionStorage.setItem(key,old);
 mocks.fetch.mockRejectedValueOnce(new Error('Offline'));
 await expect(reconcileLegacyOffer(actor,lead,old)).rejects.toThrow('Offline');
 expect(sessionStorage.getItem(key)).toBe(old);
 const replacement=JSON.stringify({request_id:crypto.randomUUID(),revision_id:revision,expected_version:1,action:'approve',reviewed_content_id:revision});
 mocks.fetch.mockImplementationOnce(async()=>{sessionStorage.setItem(key,replacement);return {json:async()=>base};});
 await expect(reconcileLegacyOffer(actor,lead,old)).rejects.toThrow('Pending decision changed');
 expect(sessionStorage.getItem(key)).toBe(replacement);
});
