-- Preserve legacy column names and types while applying the audited business cohort.
-- Completed appointments are activity, never proof of a closed contract.
CREATE OR REPLACE VIEW public.funnel_metrics WITH (security_invoker = true) AS
SELECT
 count(*) AS total_leads,
 count(*) FILTER (WHERE priority_tier = 'A') AS tier_a,
 count(*) FILTER (WHERE priority_tier = 'B') AS tier_b,
 count(*) FILTER (WHERE priority_tier = 'C') AS tier_c,
 count(*) FILTER (WHERE priority_tier = 'D') AS tier_d,
 count(*) FILTER (WHERE seller_score >= 70) AS calling_eligible,
 (SELECT total_calls FROM public.business_funnel_metrics) AS total_calls,
 (SELECT conversations FROM public.business_funnel_metrics) AS conversations,
 (SELECT interested FROM public.business_funnel_metrics) AS interested,
 (SELECT count(DISTINCT lead_id) FROM public.reportable_qualification_results WHERE classification = 'WARM') AS warm_leads,
 (SELECT count(DISTINCT lead_id) FROM public.reportable_ai_call_records WHERE disposition = 'hot') AS hot_leads,
 (SELECT appointments FROM public.business_funnel_metrics) AS appointments,
 (SELECT contracts_closed FROM public.business_funnel_metrics) AS contracts_closed
FROM public.reportable_leads;
REVOKE ALL ON public.funnel_metrics FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.funnel_metrics TO authenticated, service_role;
COMMENT ON VIEW public.funnel_metrics IS 'Legacy-compatible business totals. Confirmed internal QA excluded; unique qualified leads; active/completed appointments; contracts require recorded closed deal and actual closing date.';
