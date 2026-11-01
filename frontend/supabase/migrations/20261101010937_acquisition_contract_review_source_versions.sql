-- Preserve original review rows/hashes/receipts while binding new decisions to
-- the target version and the original retained source version separately.
-- Compensation: pause acquisition / revoke review policy authority. Preserve history;
-- never downgrade evidence FKs after cross-version decisions have been recorded.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews
 ADD COLUMN evidence_version integer CHECK(evidence_version>0 AND evidence_version<=contract_version),
 ADD COLUMN source_version integer GENERATED ALWAYS AS (coalesce(evidence_version,contract_version)) STORED NOT NULL;
DO $$
DECLARE names text[]; name text;
BEGIN
 SELECT array_agg(conname ORDER BY conname) INTO names FROM pg_catalog.pg_constraint
 WHERE conrelid='public.acquisition_contract_reviews'::regclass AND contype='f'
  AND confrelid IN ('public.acquisition_evidence_artifacts'::regclass,'public.acquisition_evidence_verifications'::regclass);
 IF coalesce(array_length(names,1),0)<>2 THEN RAISE EXCEPTION 'Expected exact review evidence foreign keys'; END IF;
 FOREACH name IN ARRAY names LOOP
  EXECUTE format('ALTER TABLE public.acquisition_contract_reviews DROP CONSTRAINT %I',name);
 END LOOP;
END $$;
ALTER TABLE public.acquisition_contract_reviews
 ADD CONSTRAINT contract_review_original_artifact FOREIGN KEY(workspace_id,contract_id,source_version,artifact_id,purpose)
  REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id,purpose),
 ADD CONSTRAINT contract_review_original_verification FOREIGN KEY(workspace_id,contract_id,source_version,artifact_id,verification_id)
  REFERENCES public.acquisition_evidence_verifications(workspace_id,contract_id,contract_version,artifact_id,id);
-- Wire request/response shapes and fingerprint calculation intentionally remain unchanged.
-- Artifact IDs are immutable, globally unique, and resolved only through same-contract
-- target references. All public wrappers and existing grants remain unchanged.
CREATE OR REPLACE FUNCTION private.record_contract_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; verification public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; authority record; source_ref record;
 fingerprint text; stamped timestamptz; deadline timestamptz; active boolean; seq integer;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_kind IS NULL OR p_kind NOT IN ('contract_review','title_review','assignment_basis')
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
  'expires',p_expires,'personally_reviewed',p_personally_reviewed,'note',p_note,'actor',auth.uid(),'session',auth.jwt()->>'session_id')::text,'UTF8')),'hex');
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
    AND acquisition_status NOT IN ('closed','cancelled','expired')) THEN
   RAISE EXCEPTION 'Current contract version required' USING ERRCODE='55000'; END IF;
  SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
  IF NOT FOUND OR source_ref.link_revoked THEN RAISE EXCEPTION 'Current original document reference required' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=source_ref.source_version AND id=p_artifact;
  IF NOT FOUND THEN RAISE EXCEPTION 'Contract review artifact unavailable' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
  SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact AND id=p_verification;
  IF NOT FOUND THEN RAISE EXCEPTION 'Contract review scan unavailable' USING ERRCODE='55000'; END IF;
  SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=p_policy AND workspace_id=p_workspace
   AND kind=p_kind AND purpose=artifact.purpose AND reviewer_id=auth.uid() FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed human authority required' USING ERRCODE='42501'; END IF;
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after,policy.valid_until,authority.session_expires)
   INTO deadline FROM private.acquisition_evidence_verification_keys k
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=verification.session_id AND s.user_id=m.user_id
   WHERE k.id=verification.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,ks,rp,m,profile,s;
  stamped:=clock_timestamp();
  IF policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
   OR deadline IS NULL OR p_expires<=stamped OR p_expires>deadline OR p_expires>stamped+make_interval(secs=>policy.max_review_seconds)
   OR NOT private.contract_review_evidence_current(p_workspace,p_contract,artifact.contract_version,p_artifact,p_verification,artifact.expected_sha256,artifact.purpose,stamped) THEN
   RAISE EXCEPTION 'Current reviewed evidence and deadline required' USING ERRCODE='55000'; END IF;
 END IF;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,purpose,sha256,policy_id,
  actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version)
 VALUES(p_id,p_workspace,p_contract,p_version,p_kind,seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
  auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped,artifact.contract_version);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,'artifact_id',p_artifact,'verification_id',p_verification,
   'policy_id',p_policy,'source_version',artifact.contract_version,'expires_at',p_expires,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,
  'status',p_status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.contract_review_state(p_workspace uuid,p_contract uuid,p_version integer,p_kind text)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_contract_reviews%ROWTYPE; current_review boolean:=false;
 checked timestamptz:=statement_timestamp(); status_name text;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Contract review access denied' USING ERRCODE='42501'; END IF;
 IF p_kind IS NULL OR p_kind NOT IN ('contract_review','title_review','assignment_basis') OR NOT EXISTS(
  SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Contract review target unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind=p_kind ORDER BY sequence DESC LIMIT 1;
 IF latest.status='approved' AND latest.created_at<=checked AND checked<latest.expires_at THEN
  SELECT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
   JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=latest.actor_id
   JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.id=latest.session_id AND s.user_id=m.user_id
   JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=p_contract
   WHERE policy.id=latest.policy_id AND policy.workspace_id=p_workspace AND policy.kind=p_kind
    AND policy.purpose=latest.purpose AND policy.reviewer_id=latest.actor_id AND policy.revoked_at IS NULL
    AND policy.valid_from<=latest.created_at AND checked<policy.valid_until
    AND latest.expires_at<=latest.created_at+make_interval(secs=>policy.max_review_seconds)
    AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=latest.actor_membership_updated_at
    AND p.status='approved' AND (s.not_after IS NULL OR checked<s.not_after)
    AND d.acquisition_version=p_version AND d.acquisition_status NOT IN ('closed','cancelled','expired'))
   AND EXISTS(SELECT 1 FROM private.contract_document_reference(p_workspace,p_contract,p_version,latest.artifact_id) ref
    WHERE ref.source_version=latest.source_version AND NOT ref.link_revoked)
   AND private.contract_review_evidence_current(p_workspace,p_contract,latest.source_version,latest.artifact_id,latest.verification_id,latest.sha256,latest.purpose,checked)
  INTO current_review;
 END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status='withdrawn' THEN 'withdrawn'
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,
  'sequence',coalesce(latest.sequence,0),'review_id',latest.id,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.contract_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; purpose_name text; status_name text; source_ref record;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; scan public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 deadline timestamptz; candidate jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 -- Reuse owner/admin MFA, live membership/session and retained-version access.
 state:=private.contract_review_state(p_workspace,p_contract,p_version,p_kind);
 purpose_name:=CASE WHEN p_kind='title_review' THEN 'title_report' ELSE 'purchase_contract' END;
 SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
 IF NOT FOUND THEN RAISE EXCEPTION 'Review document reference unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=source_ref.source_version
   AND id=p_artifact AND purpose=purpose_name AND campaign_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Review document unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO prior FROM public.acquisition_contract_reviews
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND kind=p_kind
  ORDER BY sequence DESC LIMIT 1;
 IF prior.status='approved' AND prior.actor_id=auth.uid() AND prior.artifact_id=p_artifact THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'artifact_id',prior.artifact_id,
   'verification_id',prior.verification_id,'policy_id',prior.policy_id,'expected_sequence',prior.sequence);
 END IF;
 SELECT * INTO scan FROM public.acquisition_evidence_verifications
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=source_ref.source_version AND artifact_id=p_artifact
  ORDER BY created_at DESC,id DESC LIMIT 1;
 -- A deterministic most-recent reviewed policy; never creates or activates policy.
 SELECT * INTO policy FROM private.acquisition_contract_review_policies
  WHERE workspace_id=p_workspace AND kind=p_kind AND purpose=purpose_name AND reviewer_id=auth.uid()
   AND revoked_at IS NULL AND valid_from<=checked AND checked<valid_until
  ORDER BY valid_from DESC,id DESC LIMIT 1;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE id=p_contract AND workspace_id=p_workspace AND acquisition_version=p_version
   AND acquisition_status NOT IN ('closed','cancelled','expired')) THEN status_name:='contract_unavailable';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSIF source_ref.link_revoked OR scan.id IS NULL OR NOT private.contract_review_evidence_current(p_workspace,p_contract,source_ref.source_version,p_artifact,scan.id,artifact.expected_sha256,purpose_name,checked)
  THEN status_name:='evidence_review_required';
 ELSE
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,scanner_session.not_after,
    reviewer_session.not_after,policy.valid_until,checked+make_interval(secs=>policy.max_review_seconds)) INTO deadline
   FROM private.acquisition_evidence_verification_keys k
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=purpose_name
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
   JOIN auth.sessions scanner_session ON scanner_session.id=scan.session_id AND scanner_session.user_id=scan.actor_id
   JOIN auth.sessions reviewer_session ON reviewer_session.id=(auth.jwt()->>'session_id')::uuid AND reviewer_session.user_id=auth.uid()
   WHERE k.workspace_id=p_workspace AND k.id=scan.key_id;
  IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
  ELSE
   status_name:='ready_for_human_review';
   candidate:=jsonb_build_object('artifact_id',p_artifact,'verification_id',scan.id,'sha256',artifact.expected_sha256,
    'policy_id',policy.id,'max_expires_at',deadline,'expected_sequence',(state->>'sequence')::integer);
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,
  'artifact_id',p_artifact,'purpose',purpose_name,'status',status_name,'candidate',candidate,'withdrawal',withdrawal,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
COMMIT;
