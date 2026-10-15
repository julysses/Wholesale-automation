import {z} from 'zod';
const uuid=z.string().uuid();
const money=z.number().finite().min(0).max(9999999999.99).multipleOf(0.01);
const pastDate=z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value=>{
 const parsed=new Date(value+'T00:00:00Z');
 const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
 const part=(type:string)=>parts.find(p=>p.type===type)?.value;
 return Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===value&&value<=`${part('year')}-${part('month')}-${part('day')}`;
},'Date must be valid and cannot be in the future');
export const valuationInputSchema=z.object({
 direct_comp_details:z.array(z.object({address:z.string().trim().min(1).max(500),price:money.positive(),sqft:z.number().finite().positive().max(1e12).nullable(),date:pastDate.nullable(),distance_mi:z.number().finite().min(0).max(10000).nullable(),source_url:z.string().url().startsWith('https://').max(2000).nullable()}).strict()).max(50),
 avg_house_arv:money.positive().nullable(),house_comp_count:z.number().int().min(1).max(10000).nullable(),
 tav:money.nullable(),tav_source:z.enum(['county','xleads','manual']),tav_assessment_date:pastDate.nullable(),comp_notes:z.string().max(10000),
}).strict().superRefine((value,ctx)=>{
 if((value.avg_house_arv===null)!==(value.house_comp_count===null))ctx.addIssue({code:'custom',message:'Provide house ARV and comp count together'});
 if(value.tav===null&&value.tav_assessment_date!==null)ctx.addIssue({code:'custom',message:'Assessment date requires a tax value'});
 if(!value.direct_comp_details.length&&value.avg_house_arv===null&&value.tav===null)ctx.addIssue({code:'custom',message:'Enter at least one valuation input'});
});
export type ValuationInput=z.infer<typeof valuationInputSchema>;
export const valuationSnapshotSchema=z.object({land_lead_id:uuid,snapshot_hash:z.string().regex(/^[a-f0-9]{64}$/),record_count:z.number().int().nonnegative(),property_address:z.string(),reference_tav:z.number().nullable(),comp:z.object({id:uuid,land_lead_id:uuid,revision:z.number().int().nonnegative(),direct_comp_details:z.array(z.object({address:z.string(),price:z.number(),sqft:z.number().nullable().optional(),date:z.string().nullable().optional(),distance_mi:z.number().nullable().optional(),source_url:z.string().nullable().optional()}).passthrough()).nullable().optional()}).passthrough().nullable(),outreach_authorized:z.literal(false)});
export const valuationRequestSchema=z.object({land_lead_id:uuid,body:z.object({request_id:uuid,expected_hash:z.string().regex(/^[a-f0-9]{64}$/),payload:valuationInputSchema}).strict()}).strict();
export const valuationEventSchema=z.object({id:uuid,operator_id:uuid,land_lead_id:uuid,comp_id:uuid,expected_hash:z.string(),payload:valuationInputSchema,saved_snapshot:valuationSnapshotSchema});
