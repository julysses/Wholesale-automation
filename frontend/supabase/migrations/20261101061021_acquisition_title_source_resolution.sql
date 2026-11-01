-- Internal source resolution for the forthcoming controlled title-review writer.
-- No application grants, review write, policy provisioning or clearance authority.
-- Compensation: keep the title writer unavailable; preserve evidence and history.
BEGIN;
CREATE FUNCTION private.resolve_title_review_sources(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_verification uuid,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE authority record; ref record; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 verification public.acquisition_evidence_verifications%ROWTYPE; citation jsonb; bound jsonb;
 citations jsonb:='[]'; sources jsonb:='[]'; name text; source_id uuid; source_deadline timestamptz;
 checked timestamptz; deadline timestamptz; active boolean;
BEGIN
 IF p_workspace IS NULL OR p_contract IS NULL OR p_artifact IS NULL OR p_verification IS NULL
  OR private.valid_title_findings(p_findings,p_version,false) IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Exact title findings and original report required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true OR NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract
  AND acquisition_version=p_version AND acquisition_status='title_review') THEN
  RAISE EXCEPTION 'Current active title-review context required' USING ERRCODE='55000'; END IF;
 IF p_findings->'report_as_of_source'<>'null'::jsonb THEN citations:=jsonb_build_array(p_findings->'report_as_of_source'); END IF;
 FOREACH name IN ARRAY ARRAY['ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'] LOOP
  citations:=citations||(p_findings->name->'sources');
 END LOOP;
 IF p_findings->'report_as_of_source'<>'null'::jsonb AND p_findings->'report_as_of_source'->>'artifact_id'<>p_artifact::text THEN
  RAISE EXCEPTION 'Cutoff must cite the selected original title report' USING ERRCODE='55000'; END IF;
 FOR source_id IN SELECT id FROM (SELECT p_artifact AS id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(citations)) originals ORDER BY id LOOP
  SELECT * INTO ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,source_id);
  IF NOT FOUND OR ref.link_revoked THEN RAISE EXCEPTION 'Current original title source reference required' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||source_id::text,0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=ref.source_version AND id=source_id AND campaign_id IS NULL;
  IF NOT FOUND OR (source_id=p_artifact AND artifact.purpose<>'title_report') THEN
   RAISE EXCEPTION 'Original title source unavailable' USING ERRCODE='55000'; END IF;
  FOR citation IN SELECT value FROM jsonb_array_elements(citations) WHERE value->>'artifact_id'=source_id::text LOOP
   IF (citation->>'artifact_version')::integer<>artifact.contract_version OR citation->>'sha256'<>artifact.expected_sha256 THEN
    RAISE EXCEPTION 'Original title citation changed' USING ERRCODE='55000'; END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
  SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=source_id
   ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND OR (source_id=p_artifact AND verification.id<>p_verification) THEN
   RAISE EXCEPTION 'Exact current title scan required' USING ERRCODE='55000'; END IF;
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after) INTO source_deadline
   FROM private.acquisition_evidence_verification_keys k
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=verification.session_id AND s.user_id=m.user_id
   WHERE k.id=verification.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,ks,rp,m,profile,s;
  IF source_deadline IS NULL THEN RAISE EXCEPTION 'Title source authority missing' USING ERRCODE='55000'; END IF;
  sources:=sources||jsonb_build_array(jsonb_build_object('artifact_id',source_id,'source_version',artifact.contract_version,
   'verification_id',verification.id,'sha256',artifact.expected_sha256,'purpose',artifact.purpose,'expires_at',source_deadline));
  deadline:=least(deadline,source_deadline);
 END LOOP;
 checked:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=checked THEN RAISE EXCEPTION 'Title session expired' USING ERRCODE='42501'; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
  IF (bound->>'expires_at')::timestamptz<=checked OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
   (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,
   bound->>'sha256',bound->>'purpose',checked) THEN
   RAISE EXCEPTION 'Title source authority changed while waiting' USING ERRCODE='55000'; END IF;
 END LOOP;
 -- The caller must recheck these exact sources after any subsequent waits and
 -- independently bind execution/deadline/reviewer/freshness policy authority.
 RETURN jsonb_build_object('sources',sources,'checked_at',checked,'expires_at',least(deadline,authority.session_expires),
  'legal_review_approved',false,'title_clearance_confirmed',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.resolve_title_review_sources(uuid,uuid,integer,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
