-- Stable, service-only pagination of immutable human decisions.
CREATE UNIQUE INDEX offer_review_event_version ON offer_review.events(lead_id,expected_version);
CREATE FUNCTION public.offer_review_history(p_lead uuid,p_operator uuid,p_before integer DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE items jsonb; more boolean; cursor_version integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_before IS NOT NULL AND p_before<0 THEN RAISE EXCEPTION 'Invalid history cursor'; END IF;
 WITH candidates AS MATERIALIZED (
  SELECT * FROM offer_review.events WHERE lead_id=p_lead AND (p_before IS NULL OR expected_version<p_before)
  ORDER BY expected_version DESC LIMIT 51
 ), page AS (SELECT * FROM candidates ORDER BY expected_version DESC LIMIT 50)
 SELECT coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.expected_version DESC) FROM page p),'[]'::jsonb),
  (SELECT count(*)>50 FROM candidates),(SELECT min(expected_version) FROM page)
 INTO items,more,cursor_version;
 RETURN jsonb_build_object('lead_id',p_lead,'events',items,'next_before',CASE WHEN more THEN cursor_version ELSE NULL END);
END $$;
REVOKE ALL ON FUNCTION public.offer_review_history(uuid,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.offer_review_history(uuid,uuid,integer) TO service_role;
