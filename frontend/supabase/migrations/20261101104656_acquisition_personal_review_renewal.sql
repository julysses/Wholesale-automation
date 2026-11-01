-- Controlled personal renewal of immutable original findings.
-- Private only until current choices, API and guided operator flow are integrated.
-- Compensation: pause/revoke authority; preserve ledger and use forward corrections.
BEGIN;
CREATE FUNCTION private.acquisition_renewal_snapshot(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_policy uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 a public.acquisition_evidence_artifacts%ROWTYPE; v public.acquisition_evidence_verifications%ROWTYPE;
 originals jsonb; item jsonb; sources jsonb:='[]'; supports jsonb; support_rows jsonb; snapshot jsonb;
 source_expiry timestamptz; seq integer;
BEGIN
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=p_root AND status='approved' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Original renewal decision unavailable' USING ERRCODE='55000'; END IF;
 supports:=private.acquisition_renewal_review_set(p_workspace,p_contract,p_version,p_root,p_at);
 IF supports IS NULL THEN RAISE EXCEPTION 'Original renewal support unavailable' USING ERRCODE='55000'; END IF;
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(p_workspace,p_contract,p_version,p_root,p_at);
 SELECT max(sequence) INTO seq FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind=original.kind;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy;
 IF NOT FOUND OR policy.kind<>original.kind OR policy.purpose<>original.purpose THEN
  RAISE EXCEPTION 'Matching renewal policy required' USING ERRCODE='55000'; END IF;
 originals:=coalesce(original.deadline_sources,'[]')||coalesce(original.execution_sources,'[]')||coalesce(original.title_sources,'[]')||coalesce(original.disposition_sources,'[]');
 FOR item IN SELECT DISTINCT value FROM jsonb_array_elements(originals) ORDER BY value LOOP
  SELECT * INTO a FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND id=(item->>'artifact_id')::uuid AND contract_version=(item->>'source_version')::integer
   AND expected_sha256=item->>'sha256' AND purpose=item->>'purpose';
  IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(p_workspace,p_contract,p_version,a.id) ref
   WHERE ref.source_version=a.contract_version AND NOT ref.link_revoked) THEN
   RAISE EXCEPTION 'Unchanged retained renewal source required' USING ERRCODE='55000'; END IF;
  SELECT * INTO v FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=a.id ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND OR NOT private.contract_review_evidence_current(p_workspace,p_contract,a.contract_version,a.id,v.id,a.expected_sha256,a.purpose,p_at) THEN
   RAISE EXCEPTION 'Current retained renewal source verification required' USING ERRCODE='55000'; END IF;
  SELECT least(a.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after) INTO source_expiry
   FROM private.acquisition_evidence_policies rp JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=rp.workspace_id AND k.id=v.key_id
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
   JOIN auth.sessions s ON s.id=v.session_id AND s.user_id=v.actor_id WHERE rp.workspace_id=p_workspace AND rp.id=a.retention_policy_id;
  IF source_expiry IS NULL OR source_expiry<=p_at THEN RAISE EXCEPTION 'Bounded renewal source authority required' USING ERRCODE='55000'; END IF;
  sources:=sources||jsonb_build_array(jsonb_build_object('artifact_id',a.id,'source_version',a.contract_version,'verification_id',v.id,
   'sha256',a.expected_sha256,'purpose',a.purpose,'expires_at',source_expiry));
 END LOOP;
 SELECT jsonb_agg(value ORDER BY value->>'artifact_id') INTO sources FROM jsonb_array_elements(sources);
 SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) INTO support_rows FROM public.acquisition_contract_reviews r
  WHERE r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version
   AND r.id IN (SELECT (value->>'review_id')::uuid FROM jsonb_array_elements(supports));
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=p_policy;
 snapshot:=jsonb_build_object('version','personal-review-renewal-v1','original',to_jsonb(original),'previous',to_jsonb(prior),
  'expected_sequence',seq,'policy',to_jsonb(policy),'disposition_scope',CASE WHEN original.kind='disposition_findings' THEN to_jsonb(scope) ELSE NULL END,
  'sources',sources,'supports',supports,'support_rows',support_rows);
 RETURN snapshot||jsonb_build_object('sha256',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex'));
END $$;
REVOKE ALL ON FUNCTION private.acquisition_renewal_snapshot(uuid,uuid,integer,uuid,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_acquisition_review_renewal(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_term text,
 p_expected_sequence integer,p_root uuid,p_previous uuid,p_policy uuid,p_snapshot text,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contract_reviews%ROWTYPE; renewed public.acquisition_contract_reviews%ROWTYPE;
 authority record; snapshot jsonb; policy private.acquisition_contract_review_policies%ROWTYPE;
 fingerprint text; checked timestamptz; active boolean; duplicate boolean:=false; valid boolean;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_kind IS NULL OR p_kind NOT IN ('deadline_resolution','executed_contract','title_findings','disposition_findings')
  OR (p_kind='deadline_resolution' AND (p_term IS NULL OR p_term NOT IN ('effective','inspection_deadline','closing_deadline')))
  OR (p_kind<>'deadline_resolution' AND p_term IS NOT NULL) OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 1 AND 2147483646
  OR p_root IS NULL OR p_previous IS NULL OR p_policy IS NULL OR p_id IN (p_root,p_previous)
  OR p_snapshot IS NULL OR p_snapshot !~ '^[0-9a-f]{64}$' OR p_expires IS NULL OR NOT isfinite(p_expires)
  OR p_personally_reviewed IS DISTINCT FROM true OR p_note IS NULL OR length(btrim(p_note,E' \t\n\r\f\v'))<20 OR length(p_note)>4000 THEN
  RAISE EXCEPTION 'Exact personal renewal request required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array('personal-review-renewal-v1',p_id,p_workspace,p_contract,p_version,p_kind,p_term,
  p_expected_sequence,p_root,p_previous,p_policy,p_snapshot,p_expires,p_personally_reviewed,p_note,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Renewal request conflict' USING ERRCODE='23505'; END IF;
  duplicate:=true;
 ELSE
  SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
  IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
  PERFORM private.lock_acquisition_renewal_authority(p_workspace,p_contract,p_version,p_root,p_policy);
  checked:=clock_timestamp();
  snapshot:=private.acquisition_renewal_snapshot(p_workspace,p_contract,p_version,p_root,p_policy,checked);
  IF snapshot->>'sha256' IS DISTINCT FROM p_snapshot OR (snapshot->>'expected_sequence')::integer<>p_expected_sequence
   OR snapshot->'previous'->>'id' IS DISTINCT FROM p_previous::text OR snapshot->'original'->>'kind' IS DISTINCT FROM p_kind
   OR snapshot->'original'->>'deadline_term' IS DISTINCT FROM p_term THEN
   RAISE EXCEPTION 'Renewal context changed; review the current snapshot' USING ERRCODE='40001'; END IF;
  SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy;
  IF policy.reviewer_id IS DISTINCT FROM auth.uid() OR policy.revoked_at IS NOT NULL OR policy.valid_from>checked
   OR policy.valid_until<=checked OR p_expires<=checked OR p_expires>policy.valid_until
   OR p_expires>checked+make_interval(secs=>policy.max_review_seconds) THEN
   RAISE EXCEPTION 'Current bounded personal renewal policy required' USING ERRCODE='55000'; END IF;
  IF authority.session_expires IS NOT NULL AND (authority.session_expires<=checked OR p_expires>authority.session_expires) THEN
   RAISE EXCEPTION 'Renewal session expired' USING ERRCODE='42501'; END IF;
  SELECT * INTO renewed FROM public.acquisition_contract_reviews WHERE id=p_root;
  renewed.id:=p_id;renewed.sequence:=p_expected_sequence+1;renewed.policy_id:=p_policy;
  renewed.actor_id:=auth.uid();renewed.session_id:=(auth.jwt()->>'session_id')::uuid;renewed.actor_membership_updated_at:=authority.actor_updated;
  renewed.personally_reviewed:=true;renewed.note:=p_note;renewed.expires_at:=p_expires;renewed.created_at:=checked;renewed.request_hash:=fingerprint;
  renewed.renewal_root_id:=p_root;renewed.renewal_previous_id:=p_previous;renewed.renewal_dependencies:=NULL;
  SELECT (value->>'verification_id')::uuid INTO renewed.verification_id FROM jsonb_array_elements(snapshot->'sources') WHERE value->>'artifact_id'=renewed.artifact_id::text;
  CASE p_kind
   WHEN 'deadline_resolution' THEN renewed.deadline_sources:=snapshot->'sources';
   WHEN 'executed_contract' THEN renewed.execution_sources:=snapshot->'sources';
   WHEN 'title_findings' THEN renewed.title_sources:=snapshot->'sources';renewed.title_policy_snapshot:=to_jsonb(policy);
   WHEN 'disposition_findings' THEN renewed.disposition_sources:=snapshot->'sources';
    renewed.disposition_policy_snapshot:=jsonb_build_object('reviewer',to_jsonb(policy),'scope',snapshot->'disposition_scope');
  END CASE;
  INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,purpose,sha256,policy_id,actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,execution_findings,execution_sources,deadline_term,deadline_resolution,deadline_original_review_id,deadline_sources,title_findings,title_sources,title_execution_transition_id,title_original_review_id,title_original_status,title_policy_snapshot,disposition_findings,disposition_sources,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id,disposition_title_status,disposition_original_review_id,disposition_original_status,disposition_policy_snapshot,renewal_root_id,renewal_previous_id,renewal_dependencies)
  VALUES(renewed.id,renewed.workspace_id,renewed.contract_id,renewed.contract_version,renewed.kind,renewed.sequence,renewed.status,renewed.artifact_id,renewed.verification_id,renewed.purpose,renewed.sha256,renewed.policy_id,renewed.actor_id,renewed.session_id,renewed.actor_membership_updated_at,renewed.personally_reviewed,renewed.note,renewed.expires_at,renewed.request_hash,renewed.created_at,renewed.evidence_version,renewed.execution_findings,renewed.execution_sources,renewed.deadline_term,renewed.deadline_resolution,renewed.deadline_original_review_id,renewed.deadline_sources,renewed.title_findings,renewed.title_sources,renewed.title_execution_transition_id,renewed.title_original_review_id,renewed.title_original_status,renewed.title_policy_snapshot,renewed.disposition_findings,renewed.disposition_sources,renewed.disposition_plan_id,renewed.disposition_exit_type,renewed.disposition_execution_id,renewed.disposition_title_entry_id,renewed.disposition_title_review_id,renewed.disposition_title_status,renewed.disposition_original_review_id,renewed.disposition_original_status,renewed.disposition_policy_snapshot,renewed.renewal_root_id,renewed.renewal_previous_id,renewed.renewal_dependencies) RETURNING * INTO saved;
  -- Validation uses the appended row and server-derived dependency binding; any
  -- stale fact/support/policy/expiry aborts the entire insert and audit transaction.
  checked:=clock_timestamp();
  valid:=CASE p_kind
   WHEN 'deadline_resolution' THEN private.deadline_review_effective_current(p_root,checked)
   WHEN 'executed_contract' THEN private.execution_review_effective_current(p_root,checked)
   WHEN 'title_findings' THEN private.title_review_effective_current(p_root,checked)
   WHEN 'disposition_findings' THEN private.disposition_review_effective_current(p_root,checked) END;
  IF valid IS DISTINCT FROM true THEN RAISE EXCEPTION 'Renewal authority or supporting reviews changed' USING ERRCODE='55000'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_review',p_id::text,'renewed',auth.uid()::text,p_workspace,
   jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'deadline_term',p_term,'sequence',saved.sequence,
    'root_review_id',p_root,'previous_review_id',p_previous,'policy_id',p_policy,'snapshot_sha256',p_snapshot,
    'expires_at',p_expires,'sources',snapshot->'sources','renewal_dependencies',saved.renewal_dependencies,'execution_authorized',false));
 END IF;
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Renewal session expired' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'kind',saved.kind,'deadline_term',saved.deadline_term,'review_id',saved.id,'root_review_id',saved.renewal_root_id,
  'previous_review_id',saved.renewal_previous_id,'sequence',saved.sequence,'duplicate',duplicate,
  'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_review_renewal(uuid,uuid,uuid,integer,text,text,integer,uuid,uuid,uuid,text,timestamptz,boolean,text)
 FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
