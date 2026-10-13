import { z } from 'zod';
import { ApiError, apiFetch } from './api';
const termsSchema = z.object({ price:z.string().regex(/^\d+(\.\d{1,2})?$/).transform(v=>v.replace(/^0+(?=\d)/,'')), closing_date:z.string(), expires_at:z.string().datetime({offset:true}).transform(v=>new Date(v).toISOString()), recipient:z.string(), channel:z.enum(['manual','email','sms']), conditions:z.string() });
const eventSchema = z.object({id:z.string().uuid(),lead_id:z.string().uuid(),operator_id:z.string().uuid(),action:z.enum(['draft','approve','revoke']),expected_version:z.number().int().nonnegative(),revision_id:z.string().uuid(),terms:termsSchema.nullable(),created_at:z.string()});
const contentSchema=z.object({revision_id:z.string().uuid(),property_snapshot:z.object({property_address:z.string(),city:z.string(),state:z.string().nullable(),zip_code:z.string().nullable()}),renderer_version:z.literal('offer-summary-v1'),subject:z.string(),body:z.string(),created_at:z.string()});
const snapshotSchema = z.object({lead_id:z.string().uuid(),version:z.number().int().nonnegative(),revision:eventSchema.nullable(),approval:eventSchema.nullable(),approved:z.boolean(),outbound_enabled:z.literal(false),content:contentSchema.nullable(),binding_valid:z.boolean()}).superRefine((v,ctx)=>{
 if((v.content&&v.content.revision_id!==v.revision?.id)||(v.binding_valid&&!v.content)||(v.approved&&!v.binding_valid))ctx.addIssue({code:'custom',message:'Offer content binding could not be confirmed'});
 if((v.version>0&&!v.revision)||(v.revision&&(v.revision.action!=='draft'||v.revision.lead_id!==v.lead_id||v.revision.id!==v.revision.revision_id||!v.revision.terms))||(v.approved&&!v.approval)||(v.approval&&(v.approval.action!=='approve'||v.approval.lead_id!==v.lead_id||v.approval.revision_id!==v.revision?.id)))ctx.addIssue({code:'custom',message:'Inconsistent offer review snapshot'});
});
const decisionSchema = z.object({request_id:z.string().uuid(),revision_id:z.string().uuid(),expected_version:z.number().int().nonnegative(),action:z.enum(['draft','approve','revoke']),terms:termsSchema.optional(),reviewed_content_id:z.string().uuid().optional()}).superRefine((v,ctx)=>{if((v.action==='approve'&&v.reviewed_content_id!==v.revision_id)||(v.action!=='approve'&&v.reviewed_content_id!==undefined))ctx.addIssue({code:'custom',message:'Review the saved content before approving'});});
export type OfferTerms=z.infer<typeof termsSchema>;
export type OfferSnapshot=z.infer<typeof snapshotSchema>;
export type OfferDecision=z.infer<typeof decisionSchema>;
const key=(actor:string,lead:string)=>`hilltop.offer-review.v1.${actor}.${lead}`;
export function pendingOffer(actor:string,lead:string):OfferDecision|null {
 const raw=sessionStorage.getItem(key(actor,lead));
 return raw ? decisionSchema.parse(JSON.parse(raw)) : null;
}
// Older approval retries lack the displayed-content reference required by v2.
// Never upgrade or resend them automatically; reconcile server state first.
const legacyApprovalSchema=z.object({request_id:z.string().uuid(),revision_id:z.string().uuid(),expected_version:z.number().int().nonnegative(),action:z.literal('approve')}).strict();
export function legacyOfferApproval(actor:string,lead:string):string|null {
 const raw=sessionStorage.getItem(key(actor,lead));
 if(!raw)return null;
 try{return legacyApprovalSchema.safeParse(JSON.parse(raw)).success?raw:null;}catch{return null;}
}
export async function reconcileLegacyOffer(actor:string,lead:string,expectedRaw:string):Promise<OfferSnapshot>{
 if(legacyOfferApproval(actor,lead)!==expectedRaw)throw new Error('Pending decision changed. Refresh before recovering.');
 const current=await readOffer(lead);
 if(legacyOfferApproval(actor,lead)!==expectedRaw)throw new Error('Pending decision changed. Refresh before recovering.');
 sessionStorage.removeItem(key(actor,lead));
 return current;
}
export async function readOffer(lead:string):Promise<OfferSnapshot> {
 const value=snapshotSchema.parse(await (await apiFetch(`/api/operations/offers/${lead}`)).json());
 if(value.lead_id!==lead)throw new Error('Offer readback returned a different lead.');
 return value;
}
export async function writeOffer(actor:string,lead:string,decision:OfferDecision):Promise<OfferSnapshot> {
 const existing=pendingOffer(actor,lead);
 if(existing && JSON.stringify(existing)!==JSON.stringify(decisionSchema.parse(decision)))throw new Error('Recover the pending decision before making another change.');
 const body=decisionSchema.parse(decision);
 sessionStorage.setItem(key(actor,lead),JSON.stringify(body));
 let value;
 try {
  value=await (await apiFetch(`/api/operations/offers/${lead}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 } catch(error) {
  // These API responses definitively reject the transaction. Uncertain outcomes retain identity.
  if(error instanceof ApiError && [404,409,422].includes(error.status))sessionStorage.removeItem(key(actor,lead));
  throw error;
 }
 const event=eventSchema.parse(value?.event), current=snapshotSchema.parse(value?.current);
 if(event.id!==body.request_id || event.operator_id!==actor || event.lead_id!==lead || event.action!==body.action || event.revision_id!==body.revision_id || event.expected_version!==body.expected_version || JSON.stringify(event.terms)!==JSON.stringify(body.terms??null) || current.lead_id!==lead || current.version<body.expected_version+1)throw new Error('Offer acknowledgement is unconfirmed. Retry the same decision.');
 sessionStorage.removeItem(key(actor,lead));
 return current;
}

const historySchema=z.object({lead_id:z.string().uuid(),events:z.array(eventSchema).max(50),next_before:z.number().int().nonnegative().nullable()});
export type OfferHistoryPage=z.infer<typeof historySchema>;
export async function readOfferHistory(lead:string,before:number|null=null):Promise<OfferHistoryPage>{
 const page=historySchema.parse(await(await apiFetch(`/api/operations/offers/${lead}/history${before===null?'':`?before=${before}`}`)).json());
 let previous=before;
 if(page.lead_id!==lead)throw new Error('Offer history returned a different lead.');
 for(const event of page.events){
  if(event.lead_id!==lead||(previous!==null&&event.expected_version>=previous))throw new Error('Offer history order could not be confirmed.');
  previous=event.expected_version;
 }
 if(page.next_before!==null&&(page.events.length!==50||page.next_before!==previous))throw new Error('Offer history cursor could not be confirmed.');
 return page;
}
