-- Explicit, reversible reporting classification. No records or provider work are deleted.
CREATE TABLE public.lead_reporting_exclusions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 lead_id uuid NOT NULL REFERENCES public.leads(id),
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 10 AND 2000),
 recorded_by text NOT NULL CHECK(length(trim(recorded_by)) BETWEEN 1 AND 200),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 revoked_at timestamptz,
 CHECK(revoked_at IS NULL OR revoked_at>=recorded_at)
);
CREATE UNIQUE INDEX lead_reporting_exclusions_active ON public.lead_reporting_exclusions(lead_id) WHERE revoked_at IS NULL;
ALTER TABLE public.lead_reporting_exclusions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lead_reporting_exclusions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.lead_reporting_exclusions TO authenticated;
GRANT SELECT,INSERT,UPDATE ON public.lead_reporting_exclusions TO service_role;
CREATE POLICY approved_reporting_exclusion_read ON public.lead_reporting_exclusions FOR SELECT TO authenticated USING ((SELECT public.is_approved()));
COMMENT ON TABLE public.lead_reporting_exclusions IS 'Auditable internal QA exclusions from business reporting only. Does not alter consent, suppression, dispatch or operational record visibility. Revoke by timestamp rather than deleting audit history.';
INSERT INTO public.lead_reporting_exclusions(lead_id,reason,recorded_by)
 SELECT id,'Meta-generated dummy lead; literal dummy property address verified. Internal launch QA analyses, appointment and deal are retained for audit, not business conversions.','Codex launch verification'
 FROM public.leads WHERE id IN ('f44034c3-2a35-5b88-a028-ba038a408e1e','71d5bd6a-ea51-5aac-a666-9152ae7192a4')
 AND property_address='<test lead: dummy data for property_address>';
CREATE VIEW public.reportable_leads WITH(security_invoker=true) AS
 SELECT l.* FROM public.leads l WHERE NOT EXISTS(SELECT 1 FROM public.lead_reporting_exclusions q WHERE q.lead_id=l.id AND q.revoked_at IS NULL);
CREATE VIEW public.reportable_deals WITH(security_invoker=true) AS SELECT r.* FROM public.deals r JOIN public.reportable_leads l ON l.id=r.lead_id;
CREATE VIEW public.reportable_ai_call_records WITH(security_invoker=true) AS SELECT r.* FROM public.ai_call_records r JOIN public.reportable_leads l ON l.id=r.lead_id;
CREATE VIEW public.reportable_deal_analyses WITH(security_invoker=true) AS SELECT r.* FROM public.deal_analyses r JOIN public.reportable_leads l ON l.id=r.lead_id;
CREATE VIEW public.reportable_offer_recommendations WITH(security_invoker=true) AS SELECT r.* FROM public.offer_recommendations r JOIN public.reportable_leads l ON l.id=r.lead_id;
CREATE VIEW public.reportable_appointments WITH(security_invoker=true) AS SELECT r.* FROM public.appointments r JOIN public.reportable_leads l ON l.id=r.lead_id;
CREATE VIEW public.reportable_qualification_results WITH(security_invoker=true) AS SELECT r.* FROM public.qualification_results r JOIN public.reportable_leads l ON l.id=r.lead_id;
REVOKE ALL ON public.reportable_leads,public.reportable_deals,public.reportable_ai_call_records,public.reportable_deal_analyses,public.reportable_offer_recommendations,public.reportable_appointments,public.reportable_qualification_results FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.reportable_leads,public.reportable_deals,public.reportable_ai_call_records,public.reportable_deal_analyses,public.reportable_offer_recommendations,public.reportable_appointments,public.reportable_qualification_results TO authenticated,service_role;
CREATE VIEW public.business_funnel_metrics WITH(security_invoker=true) AS
 SELECT
 (SELECT count(*) FROM public.reportable_ai_call_records) AS total_calls,
 (SELECT count(*) FROM public.reportable_ai_call_records WHERE disposition NOT IN ('no_answer','voicemail','unknown','wrong_number')) AS conversations,
 (SELECT count(*) FROM public.reportable_ai_call_records WHERE disposition IN ('warm','hot','appointment_set','callback')) AS interested,
 (SELECT count(DISTINCT lead_id) FROM public.reportable_ai_call_records WHERE disposition IN ('warm','hot','appointment_set')) AS hot_leads,
 (SELECT count(*) FROM public.reportable_appointments WHERE status IN ('scheduled','confirmed','completed')) AS appointments,
 (SELECT count(*) FROM public.reportable_appointments WHERE status='completed') AS appointments_completed,
 (SELECT count(*) FROM public.reportable_deals WHERE stage='closed' AND actual_close_date IS NOT NULL) AS contracts_closed,
 (SELECT coalesce(sum(assignment_fee),0) FROM public.reportable_deals WHERE stage='closed' AND actual_close_date IS NOT NULL) AS closed_fees;
REVOKE ALL ON public.business_funnel_metrics FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.business_funnel_metrics TO authenticated,service_role;
-- No analysis join: repeated estimates must not multiply lead/import/conversion counts.
CREATE OR REPLACE VIEW public.precision_targeting_summary WITH(security_invoker=true) AS
 SELECT count(*) AS total_imported,
 count(*) FILTER(WHERE l.status IN ('suppressed','dnc')) AS total_suppressed,
 count(*) FILTER(WHERE l.precision_tier IS NOT NULL) AS total_prioritized,
 count(*) FILTER(WHERE l.precision_tier=1) AS tier_1_count,
 count(*) FILTER(WHERE l.precision_tier=2) AS tier_2_count,
 count(*) FILTER(WHERE l.precision_tier=3) AS tier_3_count,
 count(*) FILTER(WHERE l.priority_rank<=2000) AS top_2000_count,
 count(*) FILTER(WHERE l.status IN ('hot','appointment_set','contract')) AS total_converted,
 (SELECT round(avg(assignment_fee),-3) FROM public.reportable_deals WHERE stage='closed' AND actual_close_date IS NOT NULL) AS avg_assignment_fee
 FROM public.reportable_leads l;
CREATE OR REPLACE VIEW public.stack_analytics WITH(security_invoker=true) AS
 WITH lead_groups AS (
 SELECT coalesce(l.stack_name,'No Stack') AS stack_name,count(*) AS total_leads,
 count(*) FILTER(WHERE l.precision_tier=1) AS tier_1_leads,
 count(*) FILTER(WHERE l.status IN ('hot','appointment_set','contract')) AS converted_leads,
 round(count(*) FILTER(WHERE l.status IN ('hot','appointment_set','contract'))::numeric/nullif(count(*),0)*100,2) AS conversion_pct,
 round(avg(l.seller_score),1) AS avg_seller_score
 FROM public.reportable_leads l GROUP BY coalesce(l.stack_name,'No Stack')
 ), closed_fees AS (
 SELECT coalesce(l.stack_name,'No Stack') AS stack_name,round(avg(d.assignment_fee),-3) AS avg_assignment_fee
 FROM public.reportable_deals d JOIN public.reportable_leads l ON l.id=d.lead_id
 WHERE d.stage='closed' AND d.actual_close_date IS NOT NULL GROUP BY coalesce(l.stack_name,'No Stack')
 )
 SELECT g.stack_name,g.total_leads,g.tier_1_leads,g.converted_leads,g.conversion_pct,f.avg_assignment_fee,g.avg_seller_score
 FROM lead_groups g LEFT JOIN closed_fees f USING(stack_name)
 ORDER BY g.tier_1_leads DESC,g.total_leads DESC;
REVOKE ALL ON public.precision_targeting_summary,public.stack_analytics FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.precision_targeting_summary,public.stack_analytics TO authenticated,service_role;
