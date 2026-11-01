-- Bounded authenticated buyer projections. No raw table exposure, export,
-- verification, matching or contact authority.
BEGIN;
CREATE FUNCTION private.lock_acquisition_buyer_reader(p_workspace uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE expires timestamptz;
BEGIN
 IF p_workspace IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
  OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Buyer workspace authority required' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT s.not_after INTO expires FROM public.workspace_memberships m
 JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin')
  AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer workspace authority changed' USING ERRCODE='42501'; END IF;
 RETURN expires;
END $$;
REVOKE ALL ON FUNCTION private.lock_acquisition_buyer_reader(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_buyer_index(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE expires timestamptz; rows jsonb; items jsonb; next_id uuid; enabled boolean;
BEGIN
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Bounded buyer page required' USING ERRCODE='22023'; END IF;
 expires:=private.lock_acquisition_buyer_reader(p_workspace);
 SELECT coalesce(jsonb_agg(to_jsonb(page) ORDER BY page.buyer_id),'[]') INTO rows FROM (
  SELECT b.id AS buyer_id,b.acquisition_revision AS revision,v.details->>'first_name' AS first_name,
   v.details->>'last_name' AS last_name,v.details->>'company' AS company,(v.details->>'active')::boolean AS active,
   false AS buyer_verified
  FROM public.buyers b JOIN private.acquisition_buyer_versions v ON v.workspace_id=b.workspace_id AND v.buyer_id=b.id AND v.revision=b.acquisition_revision
  WHERE b.workspace_id=p_workspace AND (p_after IS NULL OR b.id>p_after) ORDER BY b.id LIMIT p_limit+1
 ) page;
 SELECT coalesce(jsonb_agg(value ORDER BY ordinality),'[]') INTO items FROM jsonb_array_elements(rows) WITH ORDINALITY WHERE ordinality<=p_limit;
 IF jsonb_array_length(rows)>p_limit THEN next_id:=(items->(p_limit-1)->>'buyer_id')::uuid; END IF;
 SELECT a.enabled INTO enabled FROM private.acquisition_activation a WHERE singleton;
 IF expires IS NOT NULL AND expires<=clock_timestamp() THEN RAISE EXCEPTION 'Buyer session expired' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'items',items,'next_cursor',next_id,'checked_at',clock_timestamp(),
  'can_save',coalesce(enabled,false),'contact_authorized',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_buyer_index(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_buyer_index(uuid,uuid,integer) TO authenticated;

CREATE FUNCTION private.acquisition_buyer_profile(p_workspace uuid,p_buyer uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE expires timestamptz; result jsonb; enabled boolean;
BEGIN
 IF p_buyer IS NULL THEN RAISE EXCEPTION 'Buyer identity required' USING ERRCODE='22023'; END IF;
 expires:=private.lock_acquisition_buyer_reader(p_workspace);
 SELECT a.enabled INTO enabled FROM private.acquisition_activation a WHERE singleton;
 SELECT jsonb_build_object('workspace_id',b.workspace_id,'buyer_id',b.id,'revision',b.acquisition_revision,'details',v.details,
  'checked_at',clock_timestamp(),'can_save',coalesce(enabled,false),'buyer_verified',false,'contact_authorized',false,'execution_authorized',false)
 INTO result FROM public.buyers b JOIN private.acquisition_buyer_versions v
  ON v.workspace_id=b.workspace_id AND v.buyer_id=b.id AND v.revision=b.acquisition_revision
 WHERE b.workspace_id=p_workspace AND b.id=p_buyer;
 IF expires IS NOT NULL AND expires<=clock_timestamp() THEN RAISE EXCEPTION 'Buyer session expired' USING ERRCODE='42501'; END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_buyer_profile(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_buyer_profile(uuid,uuid) TO authenticated;

CREATE FUNCTION public.acquisition_buyer_index(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 25)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_buyer_index(p_workspace,p_after,p_limit) $$;
CREATE FUNCTION public.acquisition_buyer_profile(p_workspace uuid,p_buyer uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_buyer_profile(p_workspace,p_buyer) $$;
REVOKE ALL ON FUNCTION public.acquisition_buyer_index(uuid,uuid,integer),public.acquisition_buyer_profile(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_buyer_index(uuid,uuid,integer),public.acquisition_buyer_profile(uuid,uuid) TO authenticated;
COMMIT;
