-- Additive filtered queue. Preserve v1 for callers not yet upgraded.
BEGIN;
CREATE FUNCTION private.acquisition_inbound_request_queue_v2(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20,
 p_status text DEFAULT 'all',p_assignment text DEFAULT 'all')
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE rows jsonb; more boolean; cursor_id uuid;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Inbound queue read denied' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 OR p_status IS NULL
  OR p_status NOT IN ('all','open','pending_review','assigned','on_hold','review_complete','requires_review','unassigned')
  OR p_assignment IS NULL OR p_assignment NOT IN ('all','mine','unassigned') THEN
  RAISE EXCEPTION 'Invalid queue bounds or filters' USING ERRCODE='22023'; END IF;
 WITH candidates AS MATERIALIZED (
  SELECT t.id,t.acquisition_integration_id AS integration_id,t.acquisition_call_id AS call_id,
   t.acquisition_request_kind AS request_kind,t.acquisition_revision AS revision,t.created_at,
   review.value->>'status' AS review_status,(review.value->>'sequence')::integer AS review_sequence,
   (review.value->>'review_current')::boolean AS review_current,(review.value->>'assigned_user_id')::uuid AS assigned_user_id
  FROM public.tasks t
  CROSS JOIN LATERAL (SELECT private.acquisition_inbound_request_state(p_workspace,t.id) AS value OFFSET 0) review
  WHERE t.workspace_id=p_workspace AND (p_after IS NULL OR t.id>p_after)
   AND NOT EXISTS(SELECT 1 FROM public.tasks newer WHERE newer.workspace_id=p_workspace
    AND newer.acquisition_integration_id=t.acquisition_integration_id AND newer.acquisition_call_id=t.acquisition_call_id
    AND newer.acquisition_request_kind=t.acquisition_request_kind AND newer.acquisition_revision>t.acquisition_revision)
   AND (p_status='all' OR p_status='open' AND review.value->>'status'<>'review_complete' OR review.value->>'status'=p_status)
   AND (p_assignment='all' OR p_assignment='mine' AND (review.value->>'assigned_user_id')::uuid=auth.uid()
    OR p_assignment='unassigned' AND review.value->>'assigned_user_id' IS NULL)
  ORDER BY t.id LIMIT p_limit+1
 ), page AS (SELECT * FROM candidates ORDER BY id LIMIT p_limit)
 SELECT coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY id) FROM page),'[]'::jsonb),
  (SELECT count(*)>p_limit FROM candidates),(SELECT id FROM page ORDER BY id DESC LIMIT 1)
 INTO rows,more,cursor_id;
 RETURN jsonb_build_object('workspace_id',p_workspace,'items',rows,'next_after',CASE WHEN more THEN cursor_id ELSE NULL END,
  'checked_at',statement_timestamp(),'revision_scope','latest_per_call_and_kind_at_read','review_status_available',true,
  'filters',jsonb_build_object('status',p_status,'assignment',p_assignment),'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_request_queue_v2(uuid,uuid,integer,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inbound_request_queue_v2(uuid,uuid,integer,text,text) TO authenticated;
CREATE FUNCTION public.acquisition_inbound_request_queue_v2(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20,p_status text DEFAULT 'all',p_assignment text DEFAULT 'all')
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_inbound_request_queue_v2(p_workspace,p_after,p_limit,p_status,p_assignment) $$;
REVOKE ALL ON FUNCTION public.acquisition_inbound_request_queue_v2(uuid,uuid,integer,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_inbound_request_queue_v2(uuid,uuid,integer,text,text) TO authenticated;
COMMIT;
