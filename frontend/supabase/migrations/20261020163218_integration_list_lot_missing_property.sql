-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261013030331_list_lot_missing_property.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
-- Preserve visibility of the original reviewed handoff when its property link is lost.
CREATE OR REPLACE FUNCTION public.list_lot_handoffs(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE admin boolean;
BEGIN
 SELECT role='admin' INTO admin FROM public.profiles WHERE id=p_operator AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('count',(SELECT count(*) FROM wholesale_ingest.lot_handoffs WHERE admin OR assigned_to=p_operator),
 'handoffs',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.created_at DESC,h.id DESC),'[]') FROM (
 SELECT h.*,coalesce(p.address_std,r.property_snapshot->>'address_std') AS address_std,coalesce(p.county,r.property_snapshot->>'county','Unknown') AS county,r.evidence_url,r.notes AS review_notes,e.score,e.reasons,e.flags,e.input_snapshot AS scoring_input,(state.value->>'current')::boolean AS current,state.value AS reconciliation
 FROM wholesale_ingest.lot_handoffs h LEFT JOIN wholesale_ingest.properties p ON p.lead_id=h.lead_id
 JOIN wholesale_ingest.lot_reviews r ON r.id=h.review_id JOIN wholesale_ingest.lead_evaluations e ON e.id=h.evaluation_id
 CROSS JOIN LATERAL (SELECT wholesale_ingest.lot_handoff_state(h.id) value) state
 WHERE admin OR h.assigned_to=p_operator ORDER BY h.created_at DESC,h.id DESC LIMIT 50 OFFSET p_offset) h));
END $$;

