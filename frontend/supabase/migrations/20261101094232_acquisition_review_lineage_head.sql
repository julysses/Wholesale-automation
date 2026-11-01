-- Private identity resolution only: no expiry, evidence or execution authority.
-- Future callers must independently evaluate current policy/source/dependencies.
-- Compensation: retain history and leave renewal writers unavailable.
BEGIN;
CREATE FUNCTION private.acquisition_review_lineage_head(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_at timestamptz)
RETURNS uuid LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE root public.acquisition_contract_reviews%ROWTYPE;
 head public.acquisition_contract_reviews%ROWTYPE; cursor_row public.acquisition_contract_reviews%ROWTYPE;
 parent public.acquisition_contract_reviews%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN NULL; END IF;
 SELECT * INTO root FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace
  AND contract_id=p_contract AND contract_version=p_version AND id=p_root;
 IF root.id IS NULL OR root.status<>'approved' OR root.renewal_root_id IS NOT NULL OR root.created_at>p_at
  OR root.kind NOT IN ('deadline_resolution','executed_contract','title_findings','disposition_findings') THEN RETURN NULL; END IF;
 -- Do not filter latest by time or status: that could resurrect withdrawn history.
 SELECT * INTO head FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace
  AND contract_id=p_contract AND contract_version=p_version AND kind=root.kind
  AND deadline_term IS NOT DISTINCT FROM root.deadline_term ORDER BY sequence DESC LIMIT 1;
 IF head.id IS NULL OR head.status<>'approved' OR head.created_at>p_at
  OR coalesce(head.renewal_root_id,head.id)<>root.id THEN RETURN NULL; END IF;
 cursor_row:=head;
 WHILE cursor_row.id<>root.id LOOP
  IF cursor_row.renewal_root_id IS DISTINCT FROM root.id OR cursor_row.renewal_previous_id IS NULL THEN RETURN NULL; END IF;
  SELECT * INTO parent FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace
   AND contract_id=p_contract AND contract_version=p_version AND kind=root.kind
   AND deadline_term IS NOT DISTINCT FROM root.deadline_term AND id=cursor_row.renewal_previous_id;
  IF parent.id IS NULL OR parent.status<>'approved' OR parent.sequence>=cursor_row.sequence
   OR parent.created_at>cursor_row.created_at OR coalesce(parent.renewal_root_id,parent.id)<>root.id THEN RETURN NULL; END IF;
  cursor_row:=parent;
 END LOOP;
 RETURN head.id;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_lineage_head(uuid,uuid,integer,uuid,timestamptz)
 FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
