-- Handoffs use fresh complete renewal authority while retaining original roots.
-- No tables or client grants change. The existing immutable audit records the
-- exact root/head set used for each new handoff; historical transitions are untouched.
-- Compensation: pause acquisition and forward-correct; never rewrite ledger roots.
BEGIN;
CREATE OR REPLACE FUNCTION private.lock_disposition_handoff_authority(p_workspace uuid,p_contract uuid,p_version integer) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; original_execution public.acquisition_contract_transitions%ROWTYPE; root uuid; checked timestamptz;
BEGIN
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR review.status<>'approved' THEN RAISE EXCEPTION 'Current approved disposition findings required' USING ERRCODE='55000'; END IF;
 root:=coalesce(review.renewal_root_id,review.id);
 PERFORM private.lock_acquisition_renewal_authority(p_workspace,p_contract,p_version,root,review.policy_id);
 SELECT * INTO original_execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=review.disposition_execution_id AND sequence=2 AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=review.disposition_title_entry_id AND sequence=3 AND recorded_status='title_review'
  AND execution_review_id=original_execution.execution_review_id) THEN
  RAISE EXCEPTION 'Exact recorded execution and title entry required' USING ERRCODE='55000'; END IF;
 checked:=clock_timestamp();
 IF NOT private.disposition_review_current(review.id,checked) THEN
  RAISE EXCEPTION 'Disposition handoff authority changed' USING ERRCODE='55000'; END IF;
 RETURN review.id;
END $$;
REVOKE ALL ON FUNCTION private.lock_disposition_handoff_authority(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.record_contract_transition(p_id uuid,p_workspace uuid,p_contract uuid,p_expected_version integer,
 p_expected_sequence integer,p_expected_status text,p_target_status text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_transitions%ROWTYPE;
 release public.acquisition_signature_reviews%ROWTYPE; basis public.acquisition_contract_reviews%ROWTYPE;
 disposition public.acquisition_contract_reviews%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE; bound jsonb; checked timestamptz;
 fingerprint text; authority_reviews jsonb:='[]'; execution_root uuid; disposition_root uuid; seq integer; active boolean; current_review jsonb; duplicate boolean:=false;
BEGIN
 IF p_id IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR NOT ((p_expected_status IS NOT DISTINCT FROM 'draft' AND p_target_status IS NOT DISTINCT FROM 'pending_signature')
   OR (p_expected_status IS NOT DISTINCT FROM 'pending_signature' AND p_target_status IS NOT DISTINCT FROM 'executed')
   OR (p_expected_status IS NOT DISTINCT FROM 'executed' AND p_target_status IS NOT DISTINCT FROM 'title_review')
   OR (p_expected_status IS NOT DISTINCT FROM 'title_review' AND p_target_status IS NOT DISTINCT FROM 'disposition_review'))
  OR p_reason IS NULL OR length(trim(p_reason)) NOT BETWEEN 20 AND 4000 THEN
  RAISE EXCEPTION 'Supported exact lifecycle request required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_expected_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-transition:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_expected_version,p_expected_sequence,
  p_expected_status,p_target_status,p_reason,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Transition session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_transitions WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Lifecycle request conflict' USING ERRCODE='23505'; END IF;
  duplicate:=true;
 ELSE
  SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
  IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
  SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract;
  IF seq<>p_expected_sequence OR NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract
   AND acquisition_version=p_expected_version AND acquisition_status=p_expected_status) THEN
   RAISE EXCEPTION 'Lifecycle context changed' USING ERRCODE='40001'; END IF;
  IF p_target_status='pending_signature' THEN
  SELECT * INTO release FROM public.acquisition_signature_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_expected_version ORDER BY sequence DESC LIMIT 1;
  IF release.id IS NULL OR release.status<>'approved' THEN RAISE EXCEPTION 'Current signature review required' USING ERRCODE='55000'; END IF;
  SELECT * INTO basis FROM public.acquisition_contract_reviews WHERE id=release.basis_review_id AND workspace_id=p_workspace
   AND contract_id=p_contract AND contract_version=p_expected_version;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||basis.artifact_id::text,0));
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||basis.sha256,0));
  PERFORM 1 FROM private.acquisition_signature_policies WHERE id=release.policy_id FOR SHARE;
   PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id=basis.policy_id FOR SHARE;
   PERFORM 1 FROM public.acquisition_evidence_artifacts a
    JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.artifact_id=a.id AND v.id=basis.verification_id
    JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=a.workspace_id AND rp.id=a.retention_policy_id
    JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
    JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
    WHERE a.workspace_id=p_workspace AND a.id=basis.artifact_id FOR SHARE OF rp,k,ks;
   PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
    JOIN auth.sessions sess ON sess.user_id=m.user_id
    WHERE m.workspace_id=p_workspace AND (sess.id=release.session_id OR sess.id=basis.session_id OR sess.id=(SELECT session_id FROM public.acquisition_evidence_verifications WHERE id=basis.verification_id))
    ORDER BY m.user_id,sess.id FOR SHARE OF m,profile,sess;

  -- VOLATILE state read occurs after all source/policy/reviewer locks and uses
  -- clock_timestamp. A prior ready response or client-supplied evidence is ignored.
  current_review:=private.signature_review_state(p_workspace,p_contract,p_expected_version);
  IF current_review->>'review_id' IS DISTINCT FROM release.id::text OR current_review->>'approval_current' IS DISTINCT FROM 'true'
   OR (authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp()) THEN
   RAISE EXCEPTION 'Signature release authority changed' USING ERRCODE='55000'; END IF;
  ELSIF p_target_status='disposition_review' THEN
   IF seq<>3 THEN RAISE EXCEPTION 'Original title entry required' USING ERRCODE='55000'; END IF;
   disposition.id:=private.lock_disposition_handoff_authority(p_workspace,p_contract,p_expected_version);
   SELECT * INTO disposition FROM public.acquisition_contract_reviews r WHERE r.id=disposition.id;
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=(
    SELECT execution_review_id FROM public.acquisition_contract_transitions WHERE id=disposition.disposition_execution_id);
   checked:=clock_timestamp();
   IF (authority.session_expires IS NOT NULL AND authority.session_expires<=checked)
    OR NOT private.disposition_review_current(disposition.id,checked) THEN
    RAISE EXCEPTION 'Disposition transition authority expired' USING ERRCODE='55000'; END IF;
  ELSE
   -- Exact current head and complete transitive authority are locked together.
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_expected_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1;
   IF executed.id IS NULL OR executed.status<>'approved' OR seq<>(CASE WHEN p_target_status='title_review' THEN 2 ELSE 1 END) THEN
    RAISE EXCEPTION 'Current executed agreement review required' USING ERRCODE='55000'; END IF;
   execution_root:=coalesce(executed.renewal_root_id,executed.id);
   IF p_target_status='title_review' AND NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions t
    WHERE t.workspace_id=p_workspace AND t.contract_id=p_contract AND t.contract_version=p_expected_version
     AND t.sequence=2 AND t.recorded_status='executed' AND t.execution_review_id=execution_root) THEN
    RAISE EXCEPTION 'Original recorded execution review required' USING ERRCODE='55000'; END IF;
   PERFORM private.lock_acquisition_renewal_authority(p_workspace,p_contract,p_expected_version,execution_root,executed.policy_id);
   checked:=clock_timestamp();
   -- This separate statement sees changes committed while locks were awaited.
   -- The predicate checks the latest exact review, every saved scan/reference,
   -- source retention, reviewer/scanner authority and current matching terms.
   IF NOT private.execution_review_current(executed.id,checked)
    OR (authority.session_expires IS NOT NULL AND authority.session_expires<=checked) THEN
    RAISE EXCEPTION 'Execution review authority changed' USING ERRCODE='55000'; END IF;
  END IF;
  execution_root:=coalesce(executed.renewal_root_id,executed.id);
  disposition_root:=coalesce(disposition.renewal_root_id,disposition.id);
  IF execution_root IS NOT NULL THEN
   authority_reviews:=private.acquisition_renewal_review_set(p_workspace,p_contract,p_expected_version,
    coalesce(disposition_root,execution_root),checked);
   IF authority_reviews IS NULL THEN RAISE EXCEPTION 'Exact effective review snapshot required' USING ERRCODE='55000'; END IF;
  END IF;
  INSERT INTO public.acquisition_contract_transitions(id,workspace_id,contract_id,contract_version,sequence,previous_status,recorded_status,
   signature_review_id,execution_review_id,execution_review_kind,actor_id,session_id,actor_membership_updated_at,reason,request_hash,
   disposition_review_id,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id)
  VALUES(p_id,p_workspace,p_contract,p_expected_version,seq+1,p_expected_status,p_target_status,release.id,execution_root,CASE WHEN execution_root IS NOT NULL THEN 'executed_contract' END,auth.uid(),
   (auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_reason,fingerprint,
   disposition_root,disposition.disposition_plan_id,disposition.disposition_exit_type,disposition.disposition_execution_id,disposition.disposition_title_entry_id,disposition.disposition_title_review_id) RETURNING * INTO saved;
  UPDATE public.deals SET acquisition_status=p_target_status WHERE id=p_contract AND workspace_id=p_workspace;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_transition',p_id::text,p_target_status,auth.uid()::text,p_workspace,
   jsonb_build_object('contract_id',p_contract,'contract_version',p_expected_version,'sequence',saved.sequence,
    'previous_status',p_expected_status,'recorded_status',p_target_status,'signature_review_id',release.id,'execution_review_id',execution_root,'disposition_review_id',disposition_root,'disposition_plan_id',disposition.disposition_plan_id,
    'disposition_exit_type',disposition.disposition_exit_type,'title_review_id',disposition.disposition_title_review_id,'review_authority',authority_reviews,'authority_checked_at',coalesce(checked,clock_timestamp()),'execution_authorized',false));
 END IF;
 RETURN jsonb_build_object('workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'request_id',saved.id,
  'contract_version',saved.contract_version,'sequence',saved.sequence,'previous_status',saved.previous_status,'recorded_status',saved.recorded_status,
  'duplicate',duplicate,'transition_recorded',true,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.contract_transition_choice(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE review jsonb; disposition public.acquisition_contract_reviews%ROWTYPE; execution_id uuid; execution_root uuid; deal public.deals%ROWTYPE; seq integer; held text; choice jsonb:=NULL; checked timestamptz;
BEGIN
 -- Reuse exact workspace/owner/admin/MFA/live-session and historical-version access.
 review:=private.signature_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO deal FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract;
 SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_transitions
  WHERE workspace_id=p_workspace AND contract_id=p_contract;
 checked:=clock_timestamp();
 IF deal.acquisition_version<>p_version THEN held:='version_changed';
 ELSIF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN held:='paused';
 ELSIF deal.acquisition_status='disposition_review' AND seq=4 THEN held:='disposition_review_started';
 ELSIF deal.acquisition_status='title_review' AND seq=3 THEN
  review:=private.disposition_review_state(p_workspace,p_contract,p_version);
  checked:=clock_timestamp();
  IF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked
   OR NOT private.disposition_review_current((review->>'review_id')::uuid,checked) THEN held:='disposition_review_required';
  ELSE
   SELECT * INTO disposition FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND id=(review->>'review_id')::uuid AND kind='disposition_findings';
   SELECT execution_review_id INTO execution_id FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace
    AND contract_id=p_contract AND contract_version=p_version AND id=disposition.disposition_execution_id AND sequence=2 AND recorded_status='executed';
   IF disposition.id IS NULL OR execution_id IS NULL THEN held:='disposition_review_required';
   ELSE
    held:='ready_for_human_review';
    choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','title_review',
     'target_status','disposition_review','disposition_review_id',coalesce(disposition.renewal_root_id,disposition.id),'plan_id',disposition.disposition_plan_id,
     'exit_type',disposition.disposition_exit_type,'title_review_id',disposition.disposition_title_review_id,
     'execution_review_id',execution_id,'expires_at',review->>'expires_at');
   END IF;
  END IF;
 ELSIF deal.acquisition_status='executed' AND seq=2 THEN
  review:=private.execution_review_state(p_workspace,p_contract,p_version);
  SELECT coalesce(renewal_root_id,id) INTO execution_root FROM public.acquisition_contract_reviews
   WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version
    AND kind='executed_contract' AND id=(review->>'review_id')::uuid;
  checked:=clock_timestamp();
  IF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked
   OR NOT private.execution_review_current((review->>'review_id')::uuid,checked)
   OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions t
    WHERE t.workspace_id=p_workspace AND t.contract_id=p_contract AND t.contract_version=p_version
     AND t.sequence=2 AND t.recorded_status='executed' AND t.execution_review_id=execution_root)
   THEN held:='title_review_required';
  ELSE
   held:='ready_for_human_review';
   choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','executed',
    'target_status','title_review','execution_review_id',execution_root,'expires_at',review->>'expires_at');
  END IF;
 ELSIF deal.acquisition_status='pending_signature' AND seq=1 THEN
  review:=private.execution_review_state(p_workspace,p_contract,p_version);
  SELECT coalesce(renewal_root_id,id) INTO execution_root FROM public.acquisition_contract_reviews
   WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version
    AND kind='executed_contract' AND id=(review->>'review_id')::uuid;
  checked:=clock_timestamp();
  IF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked
   OR NOT private.execution_review_current((review->>'review_id')::uuid,checked) THEN held:='execution_review_required';
  ELSE
   held:='ready_for_human_review';
   choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','pending_signature',
    'target_status','executed','execution_review_id',execution_root,'expires_at',review->>'expires_at');
  END IF;
 ELSIF deal.acquisition_status IS DISTINCT FROM 'draft' OR seq<>0 THEN held:='history_requires_review';
 ELSIF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked THEN held:='signature_review_required';
 ELSE
  held:='ready_for_human_review';
  choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','draft',
   'target_status','pending_signature','signature_review_id',review->>'review_id','expires_at',review->>'expires_at');
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'current_version',deal.acquisition_version,'current_status',deal.acquisition_status,'sequence',seq,
  'status',held,'candidate',choice,'checked_at',checked,'execution_authorized',false);
END $$;
COMMIT;
