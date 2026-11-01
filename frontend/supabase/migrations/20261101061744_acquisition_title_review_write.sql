-- Exact title findings, source/execution binding and historical recovery.
-- No policy is provisioned; no signing, marketing, assignment or closing occurs.
-- Compensation: pause acquisition/revoke policy; retain immutable history.
BEGIN;
ALTER TABLE private.acquisition_contract_review_policies
 ADD COLUMN title_report_max_age_seconds integer,
 ADD COLUMN title_report_max_age_days integer,
 ADD COLUMN title_report_timezone text,
 ADD CONSTRAINT acquisition_title_report_policy_shape CHECK(
  (title_report_max_age_seconds IS NULL OR (kind='title_findings' AND title_report_max_age_seconds BETWEEN 1 AND 31536000))
  AND (title_report_max_age_days IS NULL OR (kind='title_findings' AND title_report_max_age_days BETWEEN 0 AND 365))
  AND ((title_report_max_age_days IS NULL AND title_report_timezone IS NULL)
   OR (kind='title_findings' AND title_report_max_age_days IS NOT NULL AND title_report_timezone IS NOT NULL
    AND length(trim(title_report_timezone)) BETWEEN 1 AND 100)));
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN title_policy_snapshot jsonb,
 ADD CONSTRAINT acquisition_title_policy_snapshot_shape CHECK(title_policy_snapshot IS NULL
  OR (kind='title_findings' AND status IN ('approved','requires_resolution') AND jsonb_typeof(title_policy_snapshot)='object'));

-- A policy explicitly chooses calendar-day age in a named zone or exact elapsed
-- seconds. Original report fields are never rewritten to an inferred midnight.
CREATE FUNCTION private.title_report_fresh_until(p_report jsonb,p_policy private.acquisition_contract_review_policies,p_at timestamptz)
RETURNS timestamptz LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE cutoff timestamptz; report_day date; local_day date;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR p_policy.kind IS DISTINCT FROM 'title_findings'
  OR private.valid_title_report_date(p_report) IS DISTINCT FROM true THEN RETURN NULL; END IF;
 IF p_report->>'precision'='instant' AND p_policy.title_report_max_age_seconds IS NOT NULL THEN
  cutoff:=(p_report->>'instant')::timestamptz;
  IF cutoff>p_at THEN RETURN NULL; END IF;
  cutoff:=cutoff+make_interval(secs=>p_policy.title_report_max_age_seconds);
 ELSIF p_report->>'precision'='date' AND p_policy.title_report_max_age_days IS NOT NULL
  AND EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=p_policy.title_report_timezone) THEN
  report_day:=(p_report->>'calendar_date')::date; local_day:=(p_at AT TIME ZONE p_policy.title_report_timezone)::date;
  IF report_day>local_day OR local_day-report_day>p_policy.title_report_max_age_days THEN RETURN NULL; END IF;
  cutoff:=(report_day+p_policy.title_report_max_age_days+1)::timestamp AT TIME ZONE p_policy.title_report_timezone;
 ELSE RETURN NULL;
 END IF;
 RETURN CASE WHEN p_at<cutoff THEN cutoff ELSE NULL END;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow OR invalid_parameter_value THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION private.title_report_fresh_until(jsonb,private.acquisition_contract_review_policies,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.title_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; bound jsonb; fresh_until timestamptz;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='title_findings';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.title_policy_snapshot IS NULL OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=review.workspace_id AND id=review.policy_id;
 IF NOT FOUND OR to_jsonb(policy) IS DISTINCT FROM review.title_policy_snapshot OR policy.revoked_at IS NOT NULL
  OR policy.kind<>'title_findings' OR policy.purpose<>'title_report' OR policy.reviewer_id<>review.actor_id
  OR policy.valid_from>review.created_at OR policy.valid_until<=p_at OR review.expires_at>policy.valid_until
  OR review.expires_at>review.created_at+make_interval(secs=>policy.max_review_seconds) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.deals d JOIN public.workspaces w ON w.id=d.workspace_id
  JOIN public.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.user_id=m.user_id AND s.id=review.session_id
  WHERE d.workspace_id=review.workspace_id AND d.id=review.contract_id AND d.acquisition_version=review.contract_version
   AND d.acquisition_status='title_review' AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin')
   AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
   AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))) THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=review.title_execution_transition_id
  AND workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version
  AND sequence=2 AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=review.workspace_id
  AND contract_id=review.contract_id AND contract_version=review.contract_version AND sequence=3 AND recorded_status='title_review'
  AND execution_review_id=execution.execution_review_id)
  OR NOT private.execution_review_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id) THEN RETURN false; END IF;
 IF private.valid_title_findings(review.title_findings,review.contract_version,true) IS DISTINCT FROM true
  OR private.valid_title_source_journal(review.title_findings,review.title_sources,review.contract_version,review.artifact_id,
   review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 fresh_until:=private.title_report_fresh_until(review.title_findings->'report_as_of',policy,p_at);
 IF fresh_until IS NULL OR review.expires_at>fresh_until THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.title_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(
    review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.title_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_title_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 sources jsonb; resolved jsonb; bound jsonb; originals jsonb:='[]'; name text; fingerprint text;
 seq integer; stamped timestamptz; fresh_until timestamptz;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('approved','requires_resolution','withdrawn')
  OR p_artifact IS NULL OR p_verification IS NULL OR p_policy IS NULL OR p_personally_reviewed IS NULL
  OR p_note IS NULL OR length(btrim(p_note,E' \t\n\r\f\v'))<20 OR length(p_note)>4000
  OR (p_status<>'withdrawn' AND (NOT p_personally_reviewed OR private.valid_title_findings(p_findings,p_version,p_status='approved') IS DISTINCT FROM true))
  OR (p_status='approved' AND (p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='requires_resolution' AND p_expires IS NOT NULL)
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL OR p_findings IS NOT NULL)) THEN
  RAISE EXCEPTION 'Exact human title review required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,'title_findings',p_expected_sequence,
  p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note,p_findings,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Title request conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Title review sequence changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS NULL OR prior.status NOT IN ('approved','requires_resolution') OR prior.actor_id<>auth.uid()
    OR prior.policy_id<>p_policy OR prior.artifact_id<>p_artifact OR prior.verification_id<>p_verification THEN
    RAISE EXCEPTION 'Original title decision required for withdrawal' USING ERRCODE='55000'; END IF;
   artifact.purpose:=prior.purpose;artifact.expected_sha256:=prior.sha256;artifact.contract_version:=prior.source_version;
   execution.id:=prior.title_execution_transition_id;
  ELSE
   SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=2 AND recorded_status='executed';
   IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=3 AND recorded_status='title_review' AND execution_review_id=execution.execution_review_id) THEN
    RAISE EXCEPTION 'Exact recorded execution and title entry required' USING ERRCODE='55000'; END IF;
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id;
   -- Lock the combined original set before acquiring scanner/policy locks. The
   -- contract context serializes reference edits, review withdrawals and stages.
   IF p_findings->'report_as_of_source'<>'null'::jsonb THEN originals:=jsonb_build_array(p_findings->'report_as_of_source'); END IF;
   FOREACH name IN ARRAY ARRAY['ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'] LOOP originals:=originals||(p_findings->name->'sources'); END LOOP;
   FOR bound IN SELECT jsonb_build_object('artifact_id',id,'sha256',expected_sha256) FROM public.acquisition_evidence_artifacts
    WHERE workspace_id=p_workspace AND contract_id=p_contract AND id IN (
     SELECT p_artifact UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)
     UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(executed.execution_sources)) ORDER BY id LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
   END LOOP;
   resolved:=private.resolve_title_review_sources(p_workspace,p_contract,p_version,p_artifact,p_verification,p_findings);
   sources:=resolved->'sources';
   IF p_status='approved' THEN
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
   PERFORM private.lock_execution_deadline_authority(p_workspace,p_contract,p_version,executed.execution_findings);
   END IF;
   SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy
    AND kind='title_findings' AND purpose='title_report' AND reviewer_id=auth.uid() FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed title authority required' USING ERRCODE='42501'; END IF;
   stamped:=clock_timestamp();
   IF policy.revoked_at IS NOT NULL OR policy.valid_from>stamped OR policy.valid_until<=stamped THEN RAISE EXCEPTION 'Title policy unavailable' USING ERRCODE='55000'; END IF;
   IF p_status='approved' THEN
    fresh_until:=private.title_report_fresh_until(p_findings->'report_as_of',policy,stamped);
    IF fresh_until IS NULL OR p_expires<=stamped OR p_expires>least(fresh_until,policy.valid_until,
      stamped+make_interval(secs=>policy.max_review_seconds),(resolved->>'expires_at')::timestamptz,executed.expires_at)
     OR NOT private.execution_review_current(executed.id,stamped) THEN
     RAISE EXCEPTION 'Current bounded title and execution review required' USING ERRCODE='55000'; END IF;
   END IF;
   FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
    IF (bound->>'expires_at')::timestamptz<=stamped OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
     (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',stamped) THEN
     RAISE EXCEPTION 'Title source changed while waiting' USING ERRCODE='55000'; END IF;
   END LOOP;
   SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND id=p_artifact;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN
   RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,
   purpose,sha256,policy_id,actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,
   title_findings,title_sources,title_execution_transition_id,title_original_review_id,title_original_status,title_policy_snapshot)
  VALUES(p_id,p_workspace,p_contract,p_version,'title_findings',seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
   auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped,artifact.contract_version,
   p_findings,sources,execution.id,CASE WHEN p_status='withdrawn' THEN prior.id END,CASE WHEN p_status='withdrawn' THEN prior.status END,
   CASE WHEN p_status<>'withdrawn' THEN to_jsonb(policy) END) RETURNING * INTO saved;
  -- A separate statement checks the exact persisted snapshot at final write time.
  IF p_status='approved' AND NOT private.title_review_current(saved.id,clock_timestamp()) THEN
   RAISE EXCEPTION 'Title approval authority changed before save' USING ERRCODE='55000'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,
   'contract_version',p_version,'kind','title_findings','sequence',saved.sequence,'execution_transition_id',execution.id,
   'original_review_id',saved.title_original_review_id,'sources',sources,'policy_id',p_policy,'expires_at',p_expires,'execution_authorized',false));
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_title_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_title_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;
CREATE FUNCTION public.record_title_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_title_review(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note,p_findings)
$$;
REVOKE ALL ON FUNCTION public.record_title_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_title_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,uuid,timestamptz,boolean,text,jsonb) TO authenticated;

-- Read current authority separately from a non-executing historical receipt.
CREATE FUNCTION private.title_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_contract_reviews%ROWTYPE; current_review boolean:=false;
 checked timestamptz:=statement_timestamp(); status_name text;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
   SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Title review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 IF latest.id IS NOT NULL THEN current_review:=private.title_review_current(latest.id,checked); END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status IN ('withdrawn','requires_resolution') THEN latest.status
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind','title_findings',
  'sequence',coalesce(latest.sequence,0),'review_id',latest.id,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.title_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.title_review_state(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.title_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.title_review_state(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.title_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.title_review_state(uuid,uuid,integer) TO authenticated;
COMMIT;
