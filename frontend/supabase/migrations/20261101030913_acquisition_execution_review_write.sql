-- Exact execution review in the existing immutable ledger. No lifecycle change,
-- signature dispatch, policy provisioning or service-role fallback.
-- Compensation: pause acquisition/revoke execution policy authority; preserve history.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN execution_sources jsonb,
 ADD CONSTRAINT acquisition_execution_sources_shape CHECK(
  (kind='executed_contract' AND status='approved' AND execution_sources IS NOT NULL
   AND jsonb_typeof(execution_sources)='array' AND jsonb_array_length(execution_sources) BETWEEN 1 AND 7)
  OR ((kind<>'executed_contract' OR status='withdrawn') AND execution_sources IS NULL));

CREATE FUNCTION private.execution_terms_match(value jsonb,prepared jsonb,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; previous jsonb; current_value jsonb; effective timestamptz; inspection timestamptz; closing timestamptz;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR NOT private.valid_contract_terms(value) OR NOT private.valid_contract_terms(prepared) THEN RETURN false; END IF;
 FOREACH name IN ARRAY ARRAY['purchase_price_cents','earnest_money_cents','assignment_allowed','assignment_provisions'] LOOP
  IF value->name='null'::jsonb OR (prepared->name<>'null'::jsonb AND prepared->name IS DISTINCT FROM value->name) THEN RETURN false; END IF;
 END LOOP;
 IF (value->>'earnest_money_cents')::numeric>(value->>'purchase_price_cents')::numeric THEN RETURN false; END IF;
 FOREACH name IN ARRAY ARRAY['effective','inspection_deadline','closing_deadline'] LOOP
  previous:=prepared->name; current_value:=value->name;
  IF current_value->>'precision'<>'instant' THEN RETURN false; END IF;
  IF previous->>'precision'<>'unknown' THEN
   IF previous->>'precision'<>'instant' OR (previous->>'instant')::timestamptz IS DISTINCT FROM (current_value->>'instant')::timestamptz THEN RETURN false; END IF;
  END IF;
 END LOOP;
 effective:=(value->'effective'->>'instant')::timestamptz;
 inspection:=(value->'inspection_deadline'->>'instant')::timestamptz;
 closing:=(value->'closing_deadline'->>'instant')::timestamptz;
 RETURN effective<=p_at AND effective<=inspection AND inspection<=closing AND effective<closing AND p_at<closing;
END $$;
REVOKE ALL ON FUNCTION private.execution_terms_match(jsonb,jsonb,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.record_execution_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
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
  IF NOT private.execution_terms_match(p_findings->'terms',prepared,clock_timestamp()) THEN
   RAISE EXCEPTION 'Current matching complete execution terms required' USING ERRCODE='55000'; END IF;
  -- Lock every original in deterministic identity order before rechecking all of
  -- them at one final time. The main returned agreement is included independently
  -- of which documents supplied monetary/deadline clauses.
  FOR source_id IN SELECT id FROM (
   SELECT p_artifact AS id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(p_findings->'terms'->'sources')) originals ORDER BY id LOOP
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
  stamped:=clock_timestamp();
  IF policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
   OR p_expires<=stamped OR p_expires>policy.valid_until OR p_expires>stamped+make_interval(secs=>policy.max_review_seconds)
   OR NOT private.execution_terms_match(p_findings->'terms',prepared,stamped) THEN
   RAISE EXCEPTION 'Current bounded execution review required' USING ERRCODE='55000'; END IF;
  FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
   IF p_expires>(bound->>'expires_at')::timestamptz OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
    (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,
    bound->>'sha256',bound->>'purpose',stamped) THEN
    RAISE EXCEPTION 'Execution source authority changed while waiting' USING ERRCODE='55000'; END IF;
  END LOOP;
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
REVOKE ALL ON FUNCTION private.record_execution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_execution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;
CREATE FUNCTION public.record_execution_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_execution_review(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note,p_findings)
$$;
REVOKE ALL ON FUNCTION public.record_execution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_execution_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;
COMMIT;
