import { z } from 'zod';

export const id = z.string().uuid();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const date = z.string().refine(v => /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v)));
const version = z.number().int().min(1).max(1000000000);
const scope = { workspace_id: id, campaign_id: id };
export const template = z.object({ ...scope, id, acquisition_template_id: id, acquisition_template_version: version, name: z.string(), primary_text: z.string().min(1).max(20000), acquisition_mail_format: z.enum(['letter', 'postcard']), acquisition_tracking_mode: z.enum(['phone', 'landing_page']), status: z.literal('draft') });
export const destination = z.object({ ...scope, id, destination_id: id, version, action: z.enum(['approved', 'withdrawn']), mode: z.enum(['phone', 'landing_page']), value: z.string().min(1).max(2048) });
export const history = z.object({ ...scope, id, content_id: id, version, action: z.enum(['approved', 'withdrawn']), creative_id: id, destination_review_id: id, company_name: z.string().min(1).max(200), created_at: date });
export const preparation = z.object({ status: z.literal('content_prepared'), execution_authorized: z.literal(false), content_approved: z.literal(false), preparation_hash: hash, checked_at: date, destination_valid_until: date,
  snapshot: z.object({ ...scope, renderer_version: z.literal('acquisition-mail-render-v1'), company_name: z.string().min(1).max(200),
    template: z.object({ creative_id: id, template_id: id, version, format: z.enum(['letter', 'postcard']), tracking_mode: z.enum(['phone', 'landing_page']), body: z.string().min(1).max(20000) }),
    destination: z.object({ review_id: id, destination_id: id, version, mode: z.enum(['phone', 'landing_page']), value: z.string().min(1).max(2048) }) })
}).refine(p => Date.parse(p.checked_at) < Date.parse(p.destination_valid_until) && p.snapshot.template.tracking_mode === p.snapshot.destination.mode);
export type Preparation = z.infer<typeof preparation>;
const record = history.extend({ renderer_version: z.literal('acquisition-mail-render-v1'), preparation_hash: hash, evidence_ref: id, evidence_hash: hash, expires_at: date });
export const state = z.object({ ...scope, content_id: id, version: z.number().int().min(0).max(1000000000), latest_review: record.nullable(), status: z.enum(['pending_review', 'approved', 'withdrawn', 'requires_review']), review_current: z.boolean(), execution_authorized: z.literal(false), checked_at: date, preparation: preparation.nullable() }).superRefine((s, ctx) => {
  const r = s.latest_review, p = s.preparation;
  const invalid = s.review_current !== (s.status === 'approved') || (s.version === 0 ? r !== null || s.status !== 'pending_review' || p !== null
    : !r || r.version !== s.version || r.content_id !== s.content_id || r.workspace_id !== s.workspace_id || r.campaign_id !== s.campaign_id || s.status === 'pending_review' || (r.action === 'withdrawn') !== (s.status === 'withdrawn'))
    || (s.review_current ? !r || !p || Date.parse(r.expires_at) <= Date.parse(s.checked_at) || Date.parse(r.created_at) > Date.parse(s.checked_at)
      || p.checked_at !== s.checked_at || p.preparation_hash !== r.preparation_hash || p.snapshot.workspace_id !== s.workspace_id || p.snapshot.campaign_id !== s.campaign_id
      || p.snapshot.template.creative_id !== r.creative_id || p.snapshot.destination.review_id !== r.destination_review_id || p.snapshot.company_name !== r.company_name : p !== null);
  if (invalid) ctx.addIssue({ code: 'custom', message: 'Inconsistent current review' });
});
const common = { id, expected_version: z.number().int().min(0).max(999999999), note: z.string().max(2000).refine(v => v.trim().length >= 20) };
export const review = z.discriminatedUnion('action', [
  z.object({ ...common, action: z.literal('approved'), creative_id: id, destination_review_id: id, company_name: z.string().min(1).max(200), preparation_hash: hash, evidence_ref: id, evidence_hash: hash, expires_at: date }).strict(),
  z.object({ ...common, action: z.literal('withdrawn') }).strict()
]);
export const pendingSchema = z.object({ content_id: id, review }).strict();
export type Pending = z.infer<typeof pendingSchema>;
export const proof = z.object({ ...scope, status: z.literal('proof_prepared'), execution_authorized: z.literal(false), renderer_version: z.literal('acquisition-mail-render-v1'), proof_loader_version: z.literal('acquisition-mail-proof-loader-v1'), proof_kind: z.literal('internal_content_preview'), tracking_id_kind: z.literal('preview_only'), content_id: id, content_version: version, lead_id: id, property_id: id, review_id: id, preparation_hash: hash, text: z.string().min(1).max(100000), source_checked_at: date, prepared_at: date, content_valid_until: date, postal_verified: z.literal(false), recipient_authorized: z.literal(false), vendor_proof: z.literal(false) });
export type Proof = z.infer<typeof proof>;
export function scoped<T extends { workspace_id: string; campaign_id: string }>(value: T, workspace: string, campaign: string): T {
  if (value.workspace_id !== workspace || value.campaign_id !== campaign) throw new Error('Scope mismatch');
  return value;
}
export function page<T extends { id: string; workspace_id: string; campaign_id: string }>(raw: unknown, schema: z.ZodType<T>, workspace: string, campaign: string, after: string | null) {
  const p = z.object({ items: z.array(schema).max(20), next_after: id.nullable() }).parse(raw);
  p.items.forEach(row => scoped(row, workspace, campaign));
  if (p.next_after && (p.next_after !== p.items.at(-1)?.id || p.next_after === after)) throw new Error('Invalid cursor');
  return p;
}
