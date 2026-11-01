-- Scoped read-only renewal discovery; no approval, provider or transition action.
-- Existing review entities/RLS remain unchanged. Compensate by pausing acquisition.
BEGIN;
CREATE FUNCTION private.acquisition_effective_review_current(p_root uuid,p_kind text,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT CASE p_kind WHEN 'deadline_resolution' THEN private.deadline_review_effective_current(p_root,p_at)
  WHEN 'executed_contract' THEN private.execution_review_effective_current(p_root,p_at)
  WHEN 'title_findings' THEN private.title_review_effective_current(p_root,p_at)
  WHEN 'disposition_findings' THEN private.disposition_review_effective_current(p_root,p_at) ELSE false END
$$;
REVOKE ALL ON FUNCTION private.acquisition_effective_review_current(uuid,text,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_review_renewal_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); original public.acquisition_contract_reviews%ROWTYPE;
 prior public.acquisition_contract_reviews%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 scope private.acquisition_disposition_policy_scopes%ROWTYPE; plan public.acquisition_disposition_plans%ROWTYPE;
 dependencies jsonb; supports jsonb:='[]'; item jsonb; support public.acquisition_contract_reviews%ROWTYPE;
 snapshot jsonb; candidate jsonb:=NULL; current_review jsonb:=NULL; status_name text; until_at timestamptz; report_until timestamptz;
 sources_until timestamptz; reviewer_until timestamptz; seq integer;
BEGIN
 -- Existing read boundary verifies workspace, owner/admin, MFA and actual session.
 PERFORM private.signature_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=p_root AND renewal_root_id IS NULL AND status='approved'
  AND kind IN ('deadline_resolution','executed_contract','title_findings','disposition_findings');
 IF NOT FOUND THEN RAISE EXCEPTION 'Original renewal review unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(p_workspace,p_contract,p_version,p_root,checked);
 SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind=original.kind;
 IF prior.id IS NOT NULL THEN current_review:=jsonb_build_object('review_id',prior.id,'expires_at',prior.expires_at,
  'approval_current',private.acquisition_effective_review_current(p_root,original.kind,checked)); END IF;
 dependencies:=private.acquisition_review_dependency_heads(p_workspace,p_contract,p_version,p_root,checked);
 FOR item IN SELECT value FROM jsonb_array_elements(coalesce(dependencies,'[]')) LOOP
  SELECT * INTO support FROM public.acquisition_contract_reviews WHERE id=(item->>'review_id')::uuid;
  supports:=supports||jsonb_build_array(jsonb_build_object('root_review_id',item->>'root_id','review_id',support.id,
   'kind',support.kind,'deadline_term',support.deadline_term,'expires_at',support.expires_at,
   'approval_current',private.acquisition_effective_review_current((item->>'root_id')::uuid,support.kind,checked)));
 END LOOP;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies p WHERE p.workspace_id=p_workspace AND p.kind=original.kind
  AND p.purpose=original.purpose AND p.reviewer_id=auth.uid() AND p.revoked_at IS NULL AND p.valid_from<=checked AND checked<p.valid_until
  AND (original.kind<>'disposition_findings' OR EXISTS(SELECT 1 FROM private.acquisition_disposition_policy_scopes s
   WHERE s.workspace_id=p_workspace AND s.policy_id=p.id AND private.disposition_policy_current(p_workspace,p.id,auth.uid(),original.disposition_exit_type,
    checked,jsonb_build_object('reviewer',to_jsonb(p),'scope',to_jsonb(s))))) ORDER BY p.valid_from DESC,p.id DESC LIMIT 1;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version
  AND acquisition_status=ANY(CASE WHEN original.kind IN ('title_findings','disposition_findings') THEN ARRAY['title_review','disposition_review']
   ELSE ARRAY['pending_signature','executed','title_review','disposition_review'] END)) THEN status_name:='contract_unavailable';
 ELSIF prior.id IS NULL THEN status_name:='withdrawn_or_superseded';
 ELSIF seq>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSIF dependencies IS NULL OR EXISTS(SELECT 1 FROM jsonb_array_elements(supports) s WHERE s->>'approval_current' IS DISTINCT FROM 'true') THEN
  status_name:='supporting_review_required';
 ELSE
  BEGIN
   snapshot:=private.acquisition_renewal_snapshot(p_workspace,p_contract,p_version,p_root,policy.id,checked);
  EXCEPTION WHEN object_not_in_prerequisite_state THEN status_name:='evidence_review_required';
  END;
  IF snapshot IS NOT NULL THEN
   SELECT min((value->>'expires_at')::timestamptz) INTO sources_until FROM jsonb_array_elements(snapshot->'sources');
   SELECT not_after INTO reviewer_until FROM auth.sessions WHERE id=(auth.jwt()->>'session_id')::uuid AND user_id=auth.uid();
   until_at:=least(policy.valid_until,checked+make_interval(secs=>policy.max_review_seconds),sources_until,reviewer_until);
   FOR item IN SELECT value FROM jsonb_array_elements(supports) LOOP until_at:=least(until_at,(item->>'expires_at')::timestamptz); END LOOP;
   IF original.kind='title_findings' THEN
    report_until:=private.title_report_fresh_until(original.title_findings->'report_as_of',policy,checked);
    IF report_until IS NULL OR report_until<=checked THEN status_name:='report_review_required';
    ELSE until_at:=least(until_at,report_until); END IF;
   ELSIF original.kind='disposition_findings' THEN
    SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
    SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=policy.id;
    IF plan.id IS DISTINCT FROM original.disposition_plan_id OR plan.status IS DISTINCT FROM 'proposed'
     OR plan.exit_type IS DISTINCT FROM original.disposition_exit_type THEN status_name:='purchase_path_changed';
    ELSIF original.disposition_exit_type='wholesale_assignment' AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(original.disposition_findings->'assignment'->'legal_basis'->'sources') s
     WHERE s->>'artifact_id'=scope.legal_source_id::text) THEN status_name:='legal_evidence_required'; END IF;
    until_at:=least(until_at,scope.valid_until);
   END IF;
   IF status_name IS NULL THEN
    IF until_at IS NULL OR until_at<=checked THEN status_name:='evidence_review_required';
    ELSE
     status_name:='ready_for_human_review';
     candidate:=jsonb_build_object('expected_sequence',seq,'previous_review_id',prior.id,'policy_id',policy.id,
      'expected_snapshot_sha256',snapshot->>'sha256','max_expires_at',until_at,'sources',snapshot->'sources');
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'root_review_id',p_root,'kind',original.kind,'deadline_term',original.deadline_term,'status',status_name,'candidate',candidate,
  'original',jsonb_build_object('created_at',original.created_at,'expires_at',original.expires_at,
   'findings',CASE original.kind WHEN 'deadline_resolution' THEN original.deadline_resolution WHEN 'executed_contract' THEN original.execution_findings
    WHEN 'title_findings' THEN original.title_findings WHEN 'disposition_findings' THEN original.disposition_findings END),
  'current_review',current_review,'dependencies',supports,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_renewal_candidate(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
