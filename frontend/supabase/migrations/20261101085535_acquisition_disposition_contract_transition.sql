-- Controlled title_review -> disposition_review, with exact original approvals.
-- No legal-title claim, buyer distribution, assignment execution or closing.
-- Existing request signature/fingerprint and historical exact retries are retained.
-- Compensation: pause acquisition or revoke/withdraw authority; preserve status,
-- original decisions and immutable audit. Corrections need controlled exceptions.
BEGIN;
ALTER TABLE public.deals DROP CONSTRAINT acquisition_deal_shape;
ALTER TABLE public.deals ADD CONSTRAINT acquisition_deal_shape CHECK(
 (workspace_id IS NULL AND acquisition_status IS NULL AND acquisition_version IS NULL AND acquisition_property_id IS NULL AND acquisition_owner_relationship_id IS NULL AND acquisition_offer_id IS NULL AND acquisition_offer_sequence IS NULL) OR
 (workspace_id IS NOT NULL AND acquisition_status IN ('draft','pending_signature','executed','title_review','disposition_review') AND acquisition_status IS NOT NULL AND acquisition_version BETWEEN 1 AND 2147483647 AND acquisition_version IS NOT NULL
 AND acquisition_property_id IS NOT NULL AND acquisition_owner_relationship_id IS NOT NULL AND acquisition_offer_id IS NOT NULL AND acquisition_offer_sequence>0 AND acquisition_offer_sequence IS NOT NULL
 AND stage='offer_made' AND contract_price IS NULL AND buyer_id IS NULL AND contract_date IS NULL AND closing_date IS NULL AND actual_close_date IS NULL AND psa_doc_url IS NULL AND assignment_doc_url IS NULL));

CREATE OR REPLACE FUNCTION private.protect_acquisition_contract() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean:=false; function_owner text;
BEGIN
 IF TG_TABLE_NAME='acquisition_contract_versions' THEN scoped:=true;
 ELSE
  IF TG_OP<>'INSERT' THEN scoped:=OLD.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id); END IF;
  IF TG_OP<>'DELETE' THEN scoped:=scoped OR NEW.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=NEW.lead_id); END IF;
 END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.protect_acquisition_contract()'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use controlled contract functions' USING ERRCODE='42501'; END IF;
 IF TG_OP='INSERT' THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND TG_TABLE_NAME='deals' THEN
  IF OLD.workspace_id IS NOT NULL AND OLD.acquisition_status='draft' AND NEW.acquisition_version=OLD.acquisition_version+1
   AND (to_jsonb(NEW)-'acquisition_version'-'updated_at')=(to_jsonb(OLD)-'acquisition_version'-'updated_at')
   AND EXISTS(SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=NEW.workspace_id AND deal_id=NEW.id AND version=NEW.acquisition_version) THEN RETURN NEW; END IF;
  IF OLD.workspace_id IS NOT NULL AND ((OLD.acquisition_status='draft' AND NEW.acquisition_status='pending_signature') OR (OLD.acquisition_status='pending_signature' AND NEW.acquisition_status='executed') OR (OLD.acquisition_status='executed' AND NEW.acquisition_status='title_review') OR (OLD.acquisition_status='title_review' AND NEW.acquisition_status='disposition_review'))
   AND (to_jsonb(NEW)-'acquisition_status'-'updated_at')=(to_jsonb(OLD)-'acquisition_status'-'updated_at')
   AND EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=NEW.workspace_id AND contract_id=NEW.id
    AND contract_version=NEW.acquisition_version AND previous_status=OLD.acquisition_status AND recorded_status=NEW.acquisition_status AND sequence=CASE NEW.acquisition_status WHEN 'disposition_review' THEN 4 WHEN 'title_review' THEN 3 WHEN 'executed' THEN 2 ELSE 1 END) THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Immutable contract history and controlled version advancement required' USING ERRCODE='42501';
END $$;
CREATE OR REPLACE FUNCTION private.deadline_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; original_source public.acquisition_contract_term_sources%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='deadline_resolution';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='deadline_resolution'
   AND deadline_term=review.deadline_term ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  JOIN public.workspaces w ON w.id=d.workspace_id AND w.status='active'
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='deadline_resolution'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed','title_review','disposition_review')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_deadline_resolution(review.deadline_resolution,review.contract_version)
  OR prepared->review.deadline_term->>'precision' IS DISTINCT FROM 'date'
  OR prepared->review.deadline_term->>'calendar_date' IS DISTINCT FROM review.deadline_resolution->>'calendar_date'
  OR jsonb_typeof(review.deadline_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.deadline_sources) NOT BETWEEN 1 AND 2 THEN RETURN false; END IF;
 -- The retained interpretation agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 SELECT * INTO original_source FROM public.acquisition_contract_term_sources
  WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version AND term=review.deadline_term;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=original_source.artifact_id::text AND item->>'source_version'=original_source.artifact_version::text
  AND item->>'verification_id'=original_source.verification_id::text AND item->>'sha256'=original_source.sha256) THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.deadline_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
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
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed','title_review','disposition_review')) THEN RETURN false; END IF;
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
CREATE OR REPLACE FUNCTION private.title_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
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
   AND d.acquisition_status IN ('title_review','disposition_review') AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin')
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
CREATE FUNCTION private.lock_disposition_handoff_authority(p_workspace uuid,p_contract uuid,p_version integer) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 executed public.acquisition_contract_reviews%ROWTYPE; original_execution public.acquisition_contract_transitions%ROWTYPE;
 originals jsonb; bound jsonb; checked timestamptz;
BEGIN
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR review.status<>'approved' THEN RAISE EXCEPTION 'Current approved disposition findings required' USING ERRCODE='55000'; END IF;
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=review.disposition_title_review_id AND kind='title_findings' AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Original approved title findings required' USING ERRCODE='55000'; END IF;
 SELECT * INTO original_execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=review.disposition_execution_id AND sequence=2 AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=review.disposition_title_entry_id AND sequence=3 AND recorded_status='title_review'
  AND execution_review_id=original_execution.execution_review_id) THEN
  RAISE EXCEPTION 'Exact recorded execution and title entry required' USING ERRCODE='55000'; END IF;
 SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=original_execution.execution_review_id AND kind='executed_contract' AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Original approved execution findings required' USING ERRCODE='55000'; END IF;
 originals:=coalesce(review.disposition_sources,'[]')||coalesce(title.title_sources,'[]')||coalesce(executed.execution_sources,'[]');
 -- Acquire all original artifact/byte locks before policy locks, in writer order.
 FOR bound IN SELECT jsonb_build_object('artifact_id',id,'sha256',expected_sha256) FROM public.acquisition_evidence_artifacts
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND id IN (
   SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)) ORDER BY id LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
 END LOOP;
 FOR bound IN SELECT DISTINCT value FROM jsonb_array_elements(originals) ORDER BY value LOOP
  PERFORM 1 FROM public.acquisition_evidence_artifacts a
   JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.artifact_id=a.id AND v.id=(bound->>'verification_id')::uuid
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=a.workspace_id AND rp.id=a.retention_policy_id
   JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
   JOIN public.workspace_memberships m ON m.workspace_id=v.workspace_id AND m.user_id=v.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=v.session_id
   WHERE a.workspace_id=p_workspace AND a.id=(bound->>'artifact_id')::uuid FOR SHARE OF rp,k,ks,m,profile,sess;
 END LOOP;
 PERFORM 1 FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace
  AND id IN (executed.policy_id,title.policy_id,review.policy_id) ORDER BY id FOR SHARE;
 PERFORM 1 FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=review.policy_id FOR SHARE;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
  JOIN auth.sessions sess ON sess.user_id=m.user_id WHERE m.workspace_id=p_workspace
  AND sess.id IN (executed.session_id,title.session_id,review.session_id) ORDER BY m.user_id,sess.id FOR SHARE OF m,profile,sess;
 PERFORM private.lock_execution_deadline_authority(p_workspace,p_contract,p_version,executed.execution_findings);
 checked:=clock_timestamp();
 -- Separate statement after all waits: no previously rendered choice is authority.
 IF NOT private.disposition_review_current(review.id,checked)
  OR NOT private.title_review_current(title.id,checked) OR NOT private.execution_review_current(executed.id,checked) THEN
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
 fingerprint text; seq integer; active boolean; current_review jsonb; duplicate boolean:=false;
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
   -- The contract lock serializes review withdrawal, references and lifecycle changes.
   -- Lock all retained originals in the same order used by the review writer.
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_expected_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1;
   IF executed.id IS NULL OR executed.status<>'approved' OR seq<>(CASE WHEN p_target_status='title_review' THEN 2 ELSE 1 END) THEN
    RAISE EXCEPTION 'Current executed agreement review required' USING ERRCODE='55000'; END IF;
   IF p_target_status='title_review' AND NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions t
    WHERE t.workspace_id=p_workspace AND t.contract_id=p_contract AND t.contract_version=p_expected_version
     AND t.sequence=2 AND t.recorded_status='executed' AND t.execution_review_id=executed.id) THEN
    RAISE EXCEPTION 'Original recorded execution review required' USING ERRCODE='55000'; END IF;
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
   signature_review_id,execution_review_id,execution_review_kind,actor_id,session_id,actor_membership_updated_at,reason,request_hash,
   disposition_review_id,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id)
  VALUES(p_id,p_workspace,p_contract,p_expected_version,seq+1,p_expected_status,p_target_status,release.id,executed.id,CASE WHEN executed.id IS NOT NULL THEN 'executed_contract' END,auth.uid(),
   (auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_reason,fingerprint,
   disposition.id,disposition.disposition_plan_id,disposition.disposition_exit_type,disposition.disposition_execution_id,disposition.disposition_title_entry_id,disposition.disposition_title_review_id) RETURNING * INTO saved;
  UPDATE public.deals SET acquisition_status=p_target_status WHERE id=p_contract AND workspace_id=p_workspace;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_transition',p_id::text,p_target_status,auth.uid()::text,p_workspace,
   jsonb_build_object('contract_id',p_contract,'contract_version',p_expected_version,'sequence',saved.sequence,
    'previous_status',p_expected_status,'recorded_status',p_target_status,'signature_review_id',release.id,'execution_review_id',executed.id,'disposition_review_id',disposition.id,'disposition_plan_id',disposition.disposition_plan_id,
    'disposition_exit_type',disposition.disposition_exit_type,'title_review_id',disposition.disposition_title_review_id,'execution_authorized',false));
 END IF;
 RETURN jsonb_build_object('workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'request_id',saved.id,
  'contract_version',saved.contract_version,'sequence',saved.sequence,'previous_status',saved.previous_status,'recorded_status',saved.recorded_status,
  'duplicate',duplicate,'transition_recorded',true,'execution_authorized',false);
END $$;
COMMIT;
