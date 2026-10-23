import {z} from 'zod';
import {apiFetch} from '@/lib/api';
const uuid=z.string().uuid();
const secureUrl=z.string().url().refine(value=>value.startsWith('https://'));
export const lotActionSchema=z.discriminatedUnion('kind',[
 z.object({kind:z.literal('review'),body:z.object({request_id:uuid,lead_id:uuid,input_hash:z.string().regex(/^[a-f0-9]{64}$/),is_vacant_lot:z.boolean(),evidence_url:secureUrl,notes:z.string().trim().min(1).max(2000)})}),
 z.object({kind:z.literal('handoff'),lead_id:uuid,body:z.object({request_id:uuid,evaluation_id:uuid,assigned_to:uuid})}),
 z.object({kind:z.literal('reconcile'),body:z.object({request_id:uuid,handoff_id:uuid,expected_version:z.number().int().nonnegative(),action:z.enum(['hold','reaffirm']),evidence_hash:z.string().regex(/^[a-f0-9]{64}$/),notes:z.string().trim().min(1).max(2000)})}),
 z.object({kind:z.literal('acknowledge'),id:uuid,lead_id:uuid,land_lead_id:uuid,task_id:uuid}),
]);
export type LotAction=z.infer<typeof lotActionSchema>;
export const handoffSchema=z.object({id:uuid,lead_id:uuid,land_lead_id:uuid,task_id:uuid,evaluation_id:uuid,operator_id:uuid.nullable(),initiation:z.enum(['operator','worker']).default('operator'),assigned_to:uuid,created_at:z.string(),acknowledged_by:uuid.nullable(),acknowledged_at:z.string().nullable()});
export const reconciliationSchema=z.object({version:z.number().int().nonnegative(),evidence_hash:z.string().regex(/^[a-f0-9]{64}$/),current:z.boolean(),reaffirmable:z.boolean(),reasons:z.array(z.string()),last_decision:z.record(z.string(),z.unknown()).nullable(),latest_evaluation:z.record(z.string(),z.unknown()).nullable(),latest_review:z.record(z.string(),z.unknown()).nullable(),property:z.record(z.string(),z.unknown()).nullable(),destination:z.record(z.string(),z.unknown())});
export const inboxSchema=z.object({count:z.number().int().nonnegative(),handoffs:z.array(handoffSchema.extend({address_std:z.string().nullable(),county:z.string(),current:z.boolean(),evidence_url:secureUrl,review_notes:z.string(),score:z.number().int().min(0).max(100),reasons:z.record(z.string(),z.unknown()),flags:z.array(z.string()),scoring_input:z.record(z.string(),z.unknown()),reconciliation:reconciliationSchema.optional()})).max(50)});
export async function writeLotAction(actor:string,action:LotAction){
 const path=action.kind==='acknowledge'?`/api/land-underwriting/handoffs/${action.id}/acknowledge`:`/api/operations/lists/lots/${action.kind}`;
 const value=await(await apiFetch(path,{method:'POST',headers:{'Content-Type':'application/json'},...(action.kind==='acknowledge'?{}:{body:JSON.stringify(action.body)})})).json();
 if(action.kind==='reconcile'){
  const event=z.object({id:uuid,handoff_id:uuid,operator_id:uuid,version:z.number().int(),action:z.enum(['hold','reaffirm']),evidence_hash:z.string(),notes:z.string()}).parse(value.event);
  const {request_id,expected_version,...fields}=action.body;
  if(value.outreach_authorized!==false||event.id!==request_id||event.operator_id!==actor||event.version!==expected_version+1||Object.entries(fields).some(([key,v])=>event[key as keyof typeof event]!==v))throw new Error('Lot reconciliation acknowledgement does not match the saved decision.');
  return `Reconciliation decision ${event.version} recorded (${event.action}). The refreshed inbox shows current status; this receipt does not complete underwriting.`;
 }
 if(action.kind==='review'){
  const review=z.object({id:uuid,operator_id:uuid,lead_id:uuid,input_hash:z.string(),is_vacant_lot:z.boolean(),evidence_url:z.string(),notes:z.string()}).parse(value.review);
  const {request_id,...payload}=action.body;
  if(review.id!==request_id||review.operator_id!==actor||Object.entries(payload).some(([key,v])=>review[key as keyof typeof review]!==v))throw new Error('Lot review acknowledgement does not match the saved evidence.');
  return `Lot classification saved. Review ${review.id}. A current qualifying score is required before handoff.`;
 }
 const handoff=handoffSchema.parse(value.handoff);
 if(value.outreach_authorized!==false||handoff.lead_id!==action.lead_id)throw new Error('Lot handoff acknowledgement is unconfirmed.');
 if(action.kind==='handoff'){
  if(handoff.id!==action.body.request_id||handoff.evaluation_id!==action.body.evaluation_id||handoff.assigned_to!==action.body.assigned_to||handoff.operator_id!==actor||handoff.initiation!=='operator')throw new Error('Lot handoff does not match the saved request.');
  return `Handoff saved. Land record ${handoff.land_lead_id}; assigned task ${handoff.task_id}. Receiver acknowledgement is separate.`;
 }
 if(handoff.id!==action.id||handoff.land_lead_id!==action.land_lead_id||handoff.task_id!==action.task_id||!handoff.acknowledged_at||!handoff.acknowledged_by)throw new Error('Receiving acknowledgement is unconfirmed.');
 return `Receipt acknowledged by ${handoff.acknowledged_by} at ${handoff.acknowledged_at}. Underwriting remains pending.`;
}
