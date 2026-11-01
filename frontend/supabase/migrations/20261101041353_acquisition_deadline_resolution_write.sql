-- Source-bound human interpretation of a preserved calendar date. No lifecycle
-- transition, signing, policy provisioning or automatic execution permission.
-- Compensation: pause/revoke policy authority; preserve reviews and exact receipts.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN deadline_sources jsonb,
 ADD CONSTRAINT acquisition_deadline_sources_shape CHECK(
  (kind='deadline_resolution' AND status='approved' AND deadline_sources IS NOT NULL
   AND jsonb_typeof(deadline_sources)='array' AND jsonb_array_length(deadline_sources) BETWEEN 1 AND 2)
  OR ((kind<>'deadline_resolution' OR status='withdrawn') AND deadline_sources IS NULL));
CREATE FUNCTION private.record_deadline_resolution_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_term text,p_resolution jsonb,p_original uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; verification public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; authority record; source_ref record;
 p_kind constant text:='deadline_resolution'; prepared jsonb; original_source public.acquisition_contract_term_sources%ROWTYPE; bound jsonb; sources jsonb:='[]'::jsonb; source_deadline timestamptz; source_id uuid;
 fingerprint text; stamped timestamptz; active boolean; seq integer;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_term IS NULL OR p_term NOT IN ('effective','inspection_deadline','closing_deadline')
  OR (p_status='approved' AND (NOT private.valid_deadline_resolution(p_resolution,p_version) OR p_original IS NOT NULL
   OR p_resolution->>'term' IS DISTINCT FROM p_term OR (p_resolution->'source'->>'artifact_id')::uuid IS DISTINCT FROM p_artifact))
  OR (p_status='withdrawn' AND (p_resolution IS NOT NULL OR p_original IS NULL OR p_original=p_id))
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
  'deadline_term',p_term,'deadline_resolution',p_resolution,'original_review_id',p_original,'expires',p_expires,'personally_reviewed',p_personally_reviewed,'note',p_note,'actor',auth.uid(),'session',auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Review request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'term',saved.deadline_term,'interpretation_review_id',coalesce(saved.deadline_original_review_id,saved.id),'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_reviews
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND kind=p_kind;
 IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Review sequence changed' USING ERRCODE='40001'; END IF;
 IF p_status='withdrawn' THEN
  SELECT * INTO prior FROM public.acquisition_contract_reviews
   WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND kind=p_kind
    AND deadline_term=p_term ORDER BY sequence DESC LIMIT 1;
  IF prior.id IS NULL OR prior.id<>p_original OR prior.status<>'approved' OR prior.actor_id<>auth.uid() OR prior.policy_id<>p_policy
   OR prior.artifact_id<>p_artifact OR prior.verification_id<>p_verification THEN
   RAISE EXCEPTION 'Original approved interpretation required for withdrawal' USING ERRCODE='55000'; END IF;
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
  IF prepared->p_term->>'precision' IS DISTINCT FROM 'date'
   OR prepared->p_term->>'calendar_date' IS DISTINCT FROM p_resolution->>'calendar_date' THEN
   RAISE EXCEPTION 'Preserve the exact original calendar date; changed dates require amendment' USING ERRCODE='55000'; END IF;
  SELECT * INTO original_source FROM public.acquisition_contract_term_sources
   WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND term=p_term;
  IF NOT FOUND THEN RAISE EXCEPTION 'Original calendar term source required' USING ERRCODE='55000'; END IF;
  -- Bind both the original calendar clause and the proposed interpretation. Their
  -- original scans remain exact; a later scan cannot silently replace either.
  FOR source_id IN SELECT id FROM (SELECT p_artifact AS id UNION SELECT original_source.artifact_id) originals ORDER BY id LOOP
   SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,source_id);
   IF NOT FOUND OR source_ref.link_revoked THEN RAISE EXCEPTION 'Current original source reference required' USING ERRCODE='55000'; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||source_id::text,0));
   SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=source_ref.source_version AND id=source_id AND campaign_id IS NULL;
   IF NOT FOUND OR (source_id=p_artifact AND artifact.purpose<>'purchase_contract') THEN
    RAISE EXCEPTION 'Exact deadline source unavailable' USING ERRCODE='55000'; END IF;
   IF (source_id=p_artifact AND ((p_resolution->'source'->>'artifact_version')::integer<>artifact.contract_version
      OR p_resolution->'source'->>'sha256'<>artifact.expected_sha256))
    OR (source_id=original_source.artifact_id AND (original_source.artifact_version<>artifact.contract_version
      OR original_source.sha256<>artifact.expected_sha256)) THEN
    RAISE EXCEPTION 'Original deadline source identity changed' USING ERRCODE='55000'; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
   SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=source_id
    ORDER BY created_at DESC,id DESC LIMIT 1;
   IF NOT FOUND OR (source_id=p_artifact AND verification.id<>p_verification)
    OR (source_id=original_source.artifact_id AND verification.id<>original_source.verification_id) THEN
    RAISE EXCEPTION 'Exact current deadline source scan required' USING ERRCODE='55000'; END IF;
   SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after)
    INTO source_deadline FROM private.acquisition_evidence_verification_keys k
    JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
    JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
    JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
    JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=verification.session_id AND s.user_id=m.user_id
    WHERE k.id=verification.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,ks,rp,m,profile,s;
   IF source_deadline IS NULL THEN RAISE EXCEPTION 'Deadline source authority missing' USING ERRCODE='55000'; END IF;
   sources:=sources||jsonb_build_array(jsonb_build_object('artifact_id',source_id,'source_version',artifact.contract_version,
    'verification_id',verification.id,'sha256',artifact.expected_sha256,'purpose',artifact.purpose,'expires_at',source_deadline));
  END LOOP;
  SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=p_policy AND workspace_id=p_workspace
   AND kind=p_kind AND purpose='purchase_contract' AND reviewer_id=auth.uid() FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed human deadline interpretation authority required' USING ERRCODE='42501'; END IF;
  stamped:=clock_timestamp();
  IF policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
   OR p_expires<=stamped OR p_expires>policy.valid_until OR p_expires>stamped+make_interval(secs=>policy.max_review_seconds)
   OR prepared->p_term->>'calendar_date' IS DISTINCT FROM p_resolution->>'calendar_date' THEN
   RAISE EXCEPTION 'Current bounded deadline interpretation review required' USING ERRCODE='55000'; END IF;
  FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
   IF p_expires>(bound->>'expires_at')::timestamptz OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
    (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,
    bound->>'sha256',bound->>'purpose',stamped) THEN
    RAISE EXCEPTION 'Deadline source authority changed while waiting' USING ERRCODE='55000'; END IF;
  END LOOP;
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE id=p_artifact;
 END IF;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,purpose,sha256,policy_id,
  actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,deadline_term,deadline_resolution,deadline_original_review_id,deadline_sources)
 VALUES(p_id,p_workspace,p_contract,p_version,p_kind,seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
  auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped,artifact.contract_version,p_term,p_resolution,p_original,CASE WHEN p_status='approved' THEN sources ELSE NULL END);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,'artifact_id',p_artifact,'verification_id',p_verification,
   'policy_id',p_policy,'source_version',artifact.contract_version,'expires_at',p_expires,'deadline_term',p_term,'original_review_id',p_original,'deadline_sources',CASE WHEN p_status='approved' THEN sources ELSE NULL END,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,
  'status',p_status,'term',p_term,'interpretation_review_id',coalesce(p_original,p_id),'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_deadline_resolution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,text,jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_deadline_resolution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,text,jsonb,uuid) TO authenticated;
CREATE FUNCTION public.record_deadline_resolution_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_term text,p_resolution jsonb,p_original uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_deadline_resolution_review(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note,p_term,p_resolution,p_original)
$$;
REVOKE ALL ON FUNCTION public.record_deadline_resolution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,text,jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_deadline_resolution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,text,jsonb,uuid) TO authenticated;
COMMIT;
