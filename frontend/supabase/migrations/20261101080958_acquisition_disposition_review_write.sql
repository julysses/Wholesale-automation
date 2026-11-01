-- Original post-execution disposition findings. No live policy is provisioned.
-- No transition, marketing, assignment execution or closing is performed.
-- Compensation: withdraw the original decision or revoke authority; retain history.
BEGIN;
CREATE FUNCTION private.disposition_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 plan public.acquisition_disposition_plans%ROWTYPE; execution public.acquisition_contract_transitions%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 bound jsonb;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='disposition_findings';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.disposition_policy_snapshot IS NULL OR review.id IS DISTINCT FROM (
   SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
    AND contract_version=review.contract_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1)
  OR NOT private.disposition_policy_current(review.workspace_id,review.policy_id,review.actor_id,
   review.disposition_exit_type,p_at,review.disposition_policy_snapshot) THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=review.policy_id;
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE policy_id=review.policy_id;
 IF policy.valid_from>review.created_at OR scope.valid_from>review.created_at
  OR review.expires_at>least(policy.valid_until,scope.valid_until,review.created_at+make_interval(secs=>policy.max_review_seconds))
  OR NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
   JOIN public.workspaces w ON w.id=m.workspace_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=review.session_id
   WHERE m.workspace_id=review.workspace_id AND m.user_id=review.actor_id AND w.status='active' AND m.status='active'
    AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
    AND (sess.not_after IS NULL OR (p_at<sess.not_after AND review.expires_at<=sess.not_after))) THEN RETURN false; END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR plan.id<>review.disposition_plan_id OR plan.status<>'proposed' OR plan.exit_type<>review.disposition_exit_type
  OR plan.execution_transition_id<>review.disposition_execution_id OR plan.title_entry_id<>review.disposition_title_entry_id THEN RETURN false; END IF;
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR title.id<>review.disposition_title_review_id OR title.title_execution_transition_id<>plan.execution_transition_id
  OR NOT private.title_review_current(title.id,p_at) OR review.expires_at>title.expires_at THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=plan.execution_transition_id;
 IF NOT FOUND OR NOT private.execution_review_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id) THEN RETURN false; END IF;
 IF private.valid_disposition_findings(review.disposition_findings,review.contract_version,true,plan.exit_type) IS DISTINCT FROM true
  OR private.valid_disposition_source_journal(review.disposition_findings,review.disposition_sources,review.contract_version,
   review.artifact_id,review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 IF plan.exit_type='wholesale_assignment' AND (NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_findings->'assignment'->'legal_basis'->'sources') c
    WHERE c->>'artifact_id'=scope.legal_source_id::text) OR NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_sources) c WHERE c->>'artifact_id'=scope.legal_source_id::text)) THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.disposition_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(
   SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.disposition_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_disposition_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_plan uuid,p_original_review uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 title public.acquisition_contract_reviews%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; plan public.acquisition_disposition_plans%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 resolved jsonb; sources jsonb; bound jsonb; originals jsonb; snapshot jsonb; fingerprint text; seq integer; stamped timestamptz;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('approved','requires_resolution','withdrawn') OR p_plan IS NULL OR p_policy IS NULL
  OR p_personally_reviewed IS NULL OR p_note IS NULL OR length(btrim(p_note,E' \t\n\r\f\v'))<20 OR length(p_note)>4000
  OR (p_status<>'withdrawn' AND (NOT p_personally_reviewed OR p_original_review IS NOT NULL
   OR private.valid_disposition_findings(p_findings,p_version,p_status='approved',p_findings->>'exit_type') IS DISTINCT FROM true))
  OR (p_status='approved' AND (p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='requires_resolution' AND p_expires IS NOT NULL)
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL OR p_findings IS NOT NULL
   OR p_original_review IS NULL OR p_original_review=p_id OR p_expected_sequence<1)) THEN
  RAISE EXCEPTION 'Exact human disposition review required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,'disposition_findings',p_expected_sequence,
  p_status,p_plan,p_original_review,p_policy,p_expires,p_personally_reviewed,p_note,p_findings,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Disposition request conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Disposition sequence changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS DISTINCT FROM p_original_review OR prior.status NOT IN ('approved','requires_resolution')
    OR prior.actor_id<>auth.uid() OR prior.policy_id<>p_policy OR prior.disposition_plan_id<>p_plan THEN
    RAISE EXCEPTION 'Original personal disposition decision required' USING ERRCODE='55000'; END IF;
   plan.id:=prior.disposition_plan_id;plan.exit_type:=prior.disposition_exit_type;
   plan.execution_transition_id:=prior.disposition_execution_id;plan.title_entry_id:=prior.disposition_title_entry_id;
   title.id:=prior.disposition_title_review_id;title.status:=prior.disposition_title_status;
   resolved:=jsonb_build_object('artifact_id',prior.artifact_id,'verification_id',prior.verification_id,'source_version',prior.source_version,'sha256',prior.sha256);
  ELSE
   SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND id=p_plan AND status='proposed';
   IF NOT FOUND THEN RAISE EXCEPTION 'Original disposition proposal required' USING ERRCODE='55000'; END IF;
   SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=plan.execution_transition_id;
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id;
   SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
   IF NOT FOUND OR title.status NOT IN ('approved','requires_resolution') OR title.title_execution_transition_id<>plan.execution_transition_id THEN
    RAISE EXCEPTION 'Record original title findings before disposition review' USING ERRCODE='55000'; END IF;
   originals:=private.disposition_citations(p_findings)||coalesce(executed.execution_sources,'[]')||coalesce(title.title_sources,'[]');
   FOR bound IN SELECT jsonb_build_object('artifact_id',id,'sha256',expected_sha256) FROM public.acquisition_evidence_artifacts
    WHERE workspace_id=p_workspace AND contract_id=p_contract AND id IN (
     SELECT executed.artifact_id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)) ORDER BY id LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
   END LOOP;
   resolved:=private.resolve_disposition_review_sources(p_workspace,p_contract,p_version,p_plan,p_findings);sources:=resolved->'sources';
   IF p_status='approved' THEN
    FOR bound IN SELECT DISTINCT value FROM jsonb_array_elements(executed.execution_sources||title.title_sources) ORDER BY value LOOP
     PERFORM 1 FROM public.acquisition_evidence_artifacts a
      JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.artifact_id=a.id AND v.id=(bound->>'verification_id')::uuid
      JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=a.workspace_id AND rp.id=a.retention_policy_id
      JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
      JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
      JOIN public.workspace_memberships m ON m.workspace_id=v.workspace_id AND m.user_id=v.actor_id
      JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=v.session_id
      WHERE a.workspace_id=p_workspace AND a.id=(bound->>'artifact_id')::uuid FOR SHARE OF rp,k,ks,m,profile,sess;
    END LOOP;
    PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id=executed.policy_id AND workspace_id=p_workspace FOR SHARE;
    PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
     JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=executed.session_id
     WHERE m.workspace_id=p_workspace AND m.user_id=executed.actor_id FOR SHARE OF m,profile,sess;
    PERFORM private.lock_execution_deadline_authority(p_workspace,p_contract,p_version,executed.execution_findings);
    PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id=title.policy_id AND workspace_id=p_workspace FOR SHARE;
    PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
     JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=title.session_id
     WHERE m.workspace_id=p_workspace AND m.user_id=title.actor_id FOR SHARE OF m,profile,sess;
   END IF;
   SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy
    AND kind='disposition_findings' AND purpose='purchase_contract' AND reviewer_id=auth.uid() FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed disposition policy required' USING ERRCODE='42501'; END IF;
   SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=p_policy
    AND reviewer_id=auth.uid() AND exit_type=plan.exit_type FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed exit-specific policy required' USING ERRCODE='42501'; END IF;
   snapshot:=jsonb_build_object('reviewer',to_jsonb(policy),'scope',to_jsonb(scope));stamped:=clock_timestamp();
   IF NOT private.disposition_policy_current(p_workspace,p_policy,auth.uid(),plan.exit_type,stamped,snapshot) THEN
    RAISE EXCEPTION 'Disposition policy unavailable' USING ERRCODE='55000'; END IF;
   IF plan.exit_type='wholesale_assignment' AND (p_status='approved' OR p_findings->'assignment'->'legal_basis'->>'finding'='satisfactory') AND (NOT EXISTS(
    SELECT 1 FROM jsonb_array_elements(p_findings->'assignment'->'legal_basis'->'sources') c WHERE c->>'artifact_id'=scope.legal_source_id::text)
    OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(sources) c WHERE c->>'artifact_id'=scope.legal_source_id::text)) THEN
    RAISE EXCEPTION 'Policy-bound original legal evidence required' USING ERRCODE='55000'; END IF;
   IF p_status='approved' AND (p_expires<=stamped OR p_expires>least(policy.valid_until,scope.valid_until,
    stamped+make_interval(secs=>policy.max_review_seconds),(resolved->>'expires_at')::timestamptz,executed.expires_at,title.expires_at)
    OR NOT private.title_review_current(title.id,stamped) OR NOT private.execution_review_current(executed.id,stamped)) THEN
    RAISE EXCEPTION 'Current bounded title, execution and disposition authority required' USING ERRCODE='55000'; END IF;
   FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
    IF (bound->>'expires_at')::timestamptz<=stamped OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
     (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',stamped) THEN
     RAISE EXCEPTION 'Disposition source changed while waiting' USING ERRCODE='55000'; END IF;
   END LOOP;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN
   RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,
   purpose,sha256,policy_id,actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,
   disposition_findings,disposition_sources,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,
   disposition_title_review_id,disposition_title_status,disposition_original_review_id,disposition_original_status,disposition_policy_snapshot)
  VALUES(p_id,p_workspace,p_contract,p_version,'disposition_findings',seq+1,p_status,(resolved->>'artifact_id')::uuid,(resolved->>'verification_id')::uuid,
   'purchase_contract',resolved->>'sha256',p_policy,auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,
   p_expires,fingerprint,stamped,(resolved->>'source_version')::integer,p_findings,sources,plan.id,plan.exit_type,plan.execution_transition_id,plan.title_entry_id,
   title.id,title.status,CASE WHEN p_status='withdrawn' THEN prior.id END,CASE WHEN p_status='withdrawn' THEN prior.status END,snapshot) RETURNING * INTO saved;
  IF p_status='approved' AND NOT private.disposition_review_current(saved.id,clock_timestamp()) THEN
   RAISE EXCEPTION 'Disposition authority changed before save' USING ERRCODE='55000'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,
   'contract_version',p_version,'kind','disposition_findings','sequence',saved.sequence,'plan_id',plan.id,'exit_type',plan.exit_type,
   'title_review_id',title.id,'original_review_id',saved.disposition_original_review_id,'sources',sources,'policy_id',p_policy,
   'expires_at',p_expires,'execution_authorized',false));
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_disposition_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_disposition_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;
CREATE FUNCTION public.record_disposition_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_plan uuid,p_original_review uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_disposition_review(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_plan,p_original_review,p_policy,p_expires,p_personally_reviewed,p_note,p_findings)
$$;
REVOKE ALL ON FUNCTION public.record_disposition_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_disposition_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;

-- Read current authority separately from a non-executing historical receipt.
CREATE FUNCTION private.disposition_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_contract_reviews%ROWTYPE; current_review boolean:=false;
 checked timestamptz:=statement_timestamp(); status_name text;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
   SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Disposition review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
 IF latest.id IS NOT NULL THEN current_review:=private.disposition_review_current(latest.id,checked); END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status IN ('withdrawn','requires_resolution') THEN latest.status
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind','disposition_findings',
  'sequence',coalesce(latest.sequence,0),'review_id',latest.id,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.disposition_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.disposition_review_state(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.disposition_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.disposition_review_state(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.disposition_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.disposition_review_state(uuid,uuid,integer) TO authenticated;
COMMIT;
