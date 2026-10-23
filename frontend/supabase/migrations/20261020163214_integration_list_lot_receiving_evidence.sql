-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261013004341_list_lot_receiving_evidence.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
CREATE OR REPLACE FUNCTION public.list_lot_handoffs(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE admin boolean;
BEGIN
 SELECT role='admin' INTO admin FROM public.profiles WHERE id=p_operator AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('count',(SELECT count(*) FROM wholesale_ingest.lot_handoffs WHERE admin OR assigned_to=p_operator),
 'handoffs',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.created_at DESC,h.id DESC),'[]') FROM (
 SELECT h.*,p.address_std,p.county,r.evidence_url,r.notes AS review_notes,e.score,e.reasons,e.flags,e.input_snapshot AS scoring_input,coalesce(h.input_hash=public.list_scoring_input(h.lead_id)->>'input_hash',false) AS current
 FROM wholesale_ingest.lot_handoffs h JOIN wholesale_ingest.properties p ON p.lead_id=h.lead_id
 JOIN wholesale_ingest.lot_reviews r ON r.id=h.review_id JOIN wholesale_ingest.lead_evaluations e ON e.id=h.evaluation_id
 WHERE admin OR h.assigned_to=p_operator ORDER BY h.created_at DESC,h.id DESC LIMIT 50 OFFSET p_offset) h));
END $$;
