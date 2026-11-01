-- Bind exact human deadline interpretations into execution atomically.
-- Preserve original dates, signatures, request fingerprints and historical retries.
-- Compensation: pause acquisition/revoke policies; retain immutable review/status history.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews DROP CONSTRAINT acquisition_execution_sources_shape,
 ADD CONSTRAINT acquisition_execution_sources_shape CHECK(
  (kind='executed_contract' AND status='approved' AND execution_sources IS NOT NULL
   AND jsonb_typeof(execution_sources)='array' AND jsonb_array_length(execution_sources) BETWEEN 1 AND 13)
  OR ((kind<>'executed_contract' OR status='withdrawn') AND execution_sources IS NULL));

-- Called only after the complete source union is locked by the existing writer or
-- transition. The contract context lock serializes review replacement/withdrawal.
CREATE FUNCTION private.lock_execution_deadline_authority(p_workspace uuid,p_contract uuid,p_version integer,p_findings jsonb)
RETURNS timestamptz LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE binding jsonb; review public.acquisition_contract_reviews%ROWTYPE; deadline timestamptz:='infinity';
BEGIN
 FOR binding IN SELECT value FROM jsonb_array_elements(coalesce(p_findings->'deadline_reviews','[]'::jsonb)) ORDER BY value->>'review_id' LOOP
  SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=(binding->>'review_id')::uuid
   AND workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version
   AND kind='deadline_resolution' AND status='approved' AND deadline_term=binding->>'term';
  IF NOT FOUND THEN RAISE EXCEPTION 'Exact deadline interpretation required' USING ERRCODE='55000'; END IF;
  PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id=review.policy_id AND workspace_id=p_workspace FOR SHARE;
  PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
   JOIN auth.sessions s ON s.user_id=m.user_id AND s.id=review.session_id
   WHERE m.workspace_id=p_workspace AND m.user_id=review.actor_id FOR SHARE OF m,profile,s;
  deadline:=least(deadline,review.expires_at);
 END LOOP;
 RETURN deadline;
END $$;
REVOKE ALL ON FUNCTION private.lock_execution_deadline_authority(uuid,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.record_execution_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; verification public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; authority record; source_ref record;
 p_kind constant text:='executed_contract'; prepared jsonb; source jsonb; bound jsonb; sources jsonb:='[]'::jsonb; source_deadline timestamptz; source_id uuid;
 fingerprint text; stamped timestamptz; deadline timestamptz; active boolean; seq integer;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR (p_status='approved' AND NOT private.valid_execution_findings(p_findings,p_version)) OR (p_status='withdrawn' AND p_findings IS NOT NULL)
  OR p_expected_sequence IS NULL OR p_expected_sequence<0 OR p_expected_sequence>=2147483647
  OR p_status IS NULL OR p_status NOT IN ('approved','withdrawn') OR p_artifact IS NULL OR p_verification IS NULL OR p_policy IS NULL
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 4000 OR p_personally_reviewed IS NULL
  OR (p_status='approved' AND (NOT p_personally_reviewed OR p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL)) THEN
  RAISE EXCEPTION 'Exact human review request required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_object('workspace',p_workspace,'contract',p_contract,'version',p_version,'kind',p_kind,
  'expected_sequence',p_expected_sequence,'status',p_status,'artifact',p_artifact,'verification',p_verification,'policy',p_policy,
  'execution_findings',p_findings,'expires',p_expires,'personally_reviewed',p_personally_reviewed,'note',p_note,'actor',auth.uid(),'session',auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Review request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND kind=p_kind ORDER BY sequence DESC LIMIT 1;
 seq:=coalesce(prior.sequence,0);
 IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Review sequence changed' USING ERRCODE='40001'; END IF;
 IF p_status='withdrawn' THEN
  IF prior.id IS NULL OR prior.status<>'approved' OR prior.actor_id<>auth.uid() OR prior.policy_id<>p_policy
   OR prior.artifact_id<>p_artifact OR prior.verification_id<>p_verification THEN
   RAISE EXCEPTION 'Original approved review required for withdrawal' USING ERRCODE='55000'; END IF;
  -- Withdrawal can reduce authority even after policy/activation/evidence expiry.
  artifact.purpose:=prior.purpose; artifact.expected_sha256:=prior.sha256; artifact.contract_version:=prior.source_version;
 ELSE
  SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
  IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.deals WHERE id=p_contract AND workspace_id=p_workspace AND acquisition_version=p_version
    AND acquisition_status='pending_signature') THEN
   RAISE EXCEPTION 'Current contract version required' USING ERRCODE='55000'; END IF;
  SELECT terms INTO prepared FROM public.acquisition_contract_versions
   WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
  IF NOT private.execution_findings_match(p_workspace,p_contract,p_version,p_findings,prepared,clock_timestamp()) THEN
   RAISE EXCEPTION 'Current matching complete execution terms required' USING ERRCODE='55000'; END IF;
  -- Lock every original in deterministic identity order before rechecking all of
  -- them at one final time. The main returned agreement is included independently
  -- of which documents supplied monetary/deadline clauses.
  FOR source_id IN SELECT id FROM (
   SELECT p_artifact AS id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(p_findings->'terms'->'sources')
   UNION SELECT (item->>'artifact_id')::uuid FROM jsonb_array_elements(coalesce(p_findings->'deadline_reviews','[]'::jsonb)) b
    JOIN public.acquisition_contract_reviews r ON r.id=(b->>'review_id')::uuid
     AND r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version
     AND r.kind='deadline_resolution' AND r.deadline_term=b->>'term'
    CROSS JOIN LATERAL jsonb_array_elements(r.deadline_sources) item) originals ORDER BY id LOOP
   SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,source_id);
   IF NOT FOUND OR source_ref.link_revoked THEN RAISE EXCEPTION 'Current original source reference required' USING ERRCODE='55000'; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||source_id::text,0));
   SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=source_ref.source_version AND id=source_id AND campaign_id IS NULL;
   IF NOT FOUND OR (source_id=p_artifact AND artifact.purpose<>'purchase_contract') THEN
    RAISE EXCEPTION 'Exact execution source unavailable' USING ERRCODE='55000'; END IF;
   FOR source IN SELECT value FROM jsonb_array_elements(p_findings->'terms'->'sources') WHERE (value->>'artifact_id')::uuid=source_id LOOP
    IF (source->>'artifact_version')::integer<>artifact.contract_version OR source->>'sha256'<>artifact.expected_sha256 THEN
     RAISE EXCEPTION 'Original execution source identity changed' USING ERRCODE='55000'; END IF;
   END LOOP;
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
   SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=source_id
    ORDER BY created_at DESC,id DESC LIMIT 1;
   IF NOT FOUND OR (source_id=p_artifact AND verification.id<>p_verification) THEN
    RAISE EXCEPTION 'Exact current execution source scan required' USING ERRCODE='55000'; END IF;
   SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after)
    INTO source_deadline FROM private.acquisition_evidence_verification_keys k
    JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
    JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
    JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
    JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=verification.session_id AND s.user_id=m.user_id
    WHERE k.id=verification.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,ks,rp,m,profile,s;
   IF source_deadline IS NULL THEN RAISE EXCEPTION 'Execution source authority missing' USING ERRCODE='55000'; END IF;
   sources:=sources||jsonb_build_array(jsonb_build_object('artifact_id',source_id,'source_version',artifact.contract_version,
    'verification_id',verification.id,'sha256',artifact.expected_sha256,'purpose',artifact.purpose,'expires_at',source_deadline));
  END LOOP;
  SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=p_policy AND workspace_id=p_workspace
   AND kind=p_kind AND purpose='purchase_contract' AND reviewer_id=auth.uid() FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed human execution authority required' USING ERRCODE='42501'; END IF;
  deadline:=private.lock_execution_deadline_authority(p_workspace,p_contract,p_version,p_findings);
  stamped:=clock_timestamp();
  IF p_expires>deadline OR policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
   OR p_expires<=stamped OR p_expires>policy.valid_until OR p_expires>stamped+make_interval(secs=>policy.max_review_seconds)
   OR NOT private.execution_findings_match(p_workspace,p_contract,p_version,p_findings,prepared,stamped) THEN
   RAISE EXCEPTION 'Current bounded execution review required' USING ERRCODE='55000'; END IF;
  FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
   IF p_expires>(bound->>'expires_at')::timestamptz OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
    (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,
    bound->>'sha256',bound->>'purpose',stamped) THEN
    RAISE EXCEPTION 'Execution source authority changed while waiting' USING ERRCODE='55000'; END IF;
  END LOOP;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(coalesce(p_findings->'deadline_reviews','[]'::jsonb)) b
   JOIN public.acquisition_contract_reviews r ON r.id=(b->>'review_id')::uuid
   CROSS JOIN LATERAL jsonb_array_elements(r.deadline_sources) item
   WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(sources) retained WHERE
    retained->>'artifact_id'=item->>'artifact_id' AND retained->>'source_version'=item->>'source_version'
    AND retained->>'verification_id'=item->>'verification_id' AND retained->>'sha256'=item->>'sha256'
    AND retained->>'purpose'=item->>'purpose')) THEN
   RAISE EXCEPTION 'Deadline source identity changed' USING ERRCODE='55000'; END IF;
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE id=p_artifact;
 END IF;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,purpose,sha256,policy_id,
  actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,execution_findings,execution_sources)
 VALUES(p_id,p_workspace,p_contract,p_version,p_kind,seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
  auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped,artifact.contract_version,p_findings,CASE WHEN p_status='approved' THEN sources ELSE NULL END);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,'artifact_id',p_artifact,'verification_id',p_verification,
   'policy_id',p_policy,'source_version',artifact.contract_version,'expires_at',p_expires,'execution_sources',CASE WHEN p_status='approved' THEN sources ELSE NULL END,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,
  'status',p_status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION private.execution_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; source jsonb; binding jsonb; interpretation public.acquisition_contract_reviews%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='executed_contract';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='executed_contract'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status NOT IN ('draft','closed','cancelled','expired')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_execution_findings(review.execution_findings,review.contract_version)
  OR NOT private.execution_findings_match(review.workspace_id,review.contract_id,review.contract_version,review.execution_findings,prepared,p_at)
  OR jsonb_typeof(review.execution_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.execution_sources) NOT BETWEEN 1 AND 13 THEN RETURN false; END IF;
 -- The retained main agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 FOR source IN SELECT value FROM jsonb_array_elements(review.execution_findings->'terms'->'sources') LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
   item->>'artifact_id'=source->>'artifact_id' AND item->>'source_version'=source->>'artifact_version'
   AND item->>'sha256'=source->>'sha256') THEN RETURN false; END IF;
 END LOOP;
 FOR binding IN SELECT value FROM jsonb_array_elements(coalesce(review.execution_findings->'deadline_reviews','[]'::jsonb)) LOOP
  SELECT * INTO interpretation FROM public.acquisition_contract_reviews WHERE id=(binding->>'review_id')::uuid
   AND workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version
   AND kind='deadline_resolution' AND deadline_term=binding->>'term';
  IF NOT FOUND OR review.expires_at>interpretation.expires_at THEN RETURN false; END IF;
  FOR source IN SELECT value FROM jsonb_array_elements(interpretation.deadline_sources) LOOP
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
    item->>'artifact_id'=source->>'artifact_id' AND item->>'source_version'=source->>'source_version'
    AND item->>'verification_id'=source->>'verification_id' AND item->>'sha256'=source->>'sha256'
    AND item->>'purpose'=source->>'purpose') THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.execution_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;

CREATE OR REPLACE FUNCTION private.record_contract_transition(p_id uuid,p_workspace uuid,p_contract uuid,p_expected_version integer,
 p_expected_sequence integer,p_expected_status text,p_target_status text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_transitions%ROWTYPE;
 release public.acquisition_signature_reviews%ROWTYPE; basis public.acquisition_contract_reviews%ROWTYPE;
 executed public.acquisition_contract_reviews%ROWTYPE; bound jsonb; checked timestamptz;
 fingerprint text; seq integer; active boolean; current_review jsonb; duplicate boolean:=false;
BEGIN
 IF p_id IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR NOT ((p_expected_status IS NOT DISTINCT FROM 'draft' AND p_target_status IS NOT DISTINCT FROM 'pending_signature')
   OR (p_expected_status IS NOT DISTINCT FROM 'pending_signature' AND p_target_status IS NOT DISTINCT FROM 'executed'))
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
  ELSE
   -- The contract lock serializes review withdrawal, references and lifecycle changes.
   -- Lock all retained originals in the same order used by the review writer.
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_expected_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1;
   IF executed.id IS NULL OR executed.status<>'approved' OR seq<>1 THEN
    RAISE EXCEPTION 'Current executed agreement review required' USING ERRCODE='55000'; END IF;
   FOR bound IN SELECT value FROM jsonb_array_elements(executed.execution_sources) ORDER BY value->>'artifact_id' LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
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
   PERFORM private.lock_execution_deadline_authority(p_workspace,p_contract,p_expected_version,executed.execution_findings);
   checked:=clock_timestamp();
   -- This separate statement sees changes committed while locks were awaited.
   -- The predicate checks the latest exact review, every saved scan/reference,
   -- source retention, reviewer/scanner authority and current matching terms.
   IF NOT private.execution_review_current(executed.id,checked)
    OR (authority.session_expires IS NOT NULL AND authority.session_expires<=checked) THEN
    RAISE EXCEPTION 'Execution review authority changed' USING ERRCODE='55000'; END IF;
  END IF;
  INSERT INTO public.acquisition_contract_transitions(id,workspace_id,contract_id,contract_version,sequence,previous_status,recorded_status,
   signature_review_id,execution_review_id,execution_review_kind,actor_id,session_id,actor_membership_updated_at,reason,request_hash)
  VALUES(p_id,p_workspace,p_contract,p_expected_version,seq+1,p_expected_status,p_target_status,release.id,executed.id,CASE WHEN executed.id IS NOT NULL THEN 'executed_contract' END,auth.uid(),
   (auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_reason,fingerprint) RETURNING * INTO saved;
  UPDATE public.deals SET acquisition_status=p_target_status WHERE id=p_contract AND workspace_id=p_workspace;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_transition',p_id::text,p_target_status,auth.uid()::text,p_workspace,
   jsonb_build_object('contract_id',p_contract,'contract_version',p_expected_version,'sequence',saved.sequence,
    'previous_status',p_expected_status,'recorded_status',p_target_status,'signature_review_id',release.id,'execution_review_id',executed.id,'execution_authorized',false));
 END IF;
 RETURN jsonb_build_object('workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'request_id',saved.id,
  'contract_version',saved.contract_version,'sequence',saved.sequence,'previous_status',saved.previous_status,'recorded_status',saved.recorded_status,
  'duplicate',duplicate,'transition_recorded',true,'execution_authorized',false);
END $$;
COMMIT;
