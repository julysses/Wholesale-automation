-- Immutable human decisions bound to exact retained contract evidence.
-- No policies are seeded. Compensation: revoke policy authority / pause activation;
-- preserve decisions, withdrawals and audits. No signing or disposition execution.
BEGIN;
CREATE TABLE private.acquisition_contract_review_policies (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 kind text NOT NULL CHECK(kind IN ('contract_review','title_review','assignment_basis')),
 purpose text NOT NULL, reviewer_id uuid NOT NULL REFERENCES public.profiles(id),
 max_review_seconds integer NOT NULL CHECK(max_review_seconds BETWEEN 1 AND 86400),
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)), valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 revoked_at timestamptz CHECK(isfinite(revoked_at)), reviewed_by uuid NOT NULL REFERENCES public.profiles(id),
 approval_ref uuid NOT NULL,
 CHECK(valid_from<valid_until),
 CHECK((kind IN ('contract_review','assignment_basis') AND purpose='purchase_contract') OR (kind='title_review' AND purpose='title_report')),
 UNIQUE(workspace_id,id,kind,purpose,reviewer_id)
);
ALTER TABLE private.acquisition_contract_review_policies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_contract_review_policies FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE public.acquisition_contract_reviews (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 kind text NOT NULL, sequence integer NOT NULL CHECK(sequence>0), status text NOT NULL CHECK(status IN ('approved','withdrawn')),
 artifact_id uuid NOT NULL, verification_id uuid NOT NULL, purpose text NOT NULL,
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), policy_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 actor_membership_updated_at timestamptz NOT NULL, personally_reviewed boolean NOT NULL,
 note text NOT NULL CHECK(length(trim(note)) BETWEEN 20 AND 4000), expires_at timestamptz,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((status='approved' AND personally_reviewed AND expires_at IS NOT NULL AND isfinite(expires_at) AND expires_at>created_at)
  OR (status='withdrawn' AND NOT personally_reviewed AND expires_at IS NULL)),
 UNIQUE(workspace_id,contract_id,contract_version,kind,sequence),
 FOREIGN KEY(workspace_id,contract_id,contract_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 FOREIGN KEY(workspace_id,contract_id,contract_version,artifact_id,purpose) REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id,purpose),
 FOREIGN KEY(workspace_id,contract_id,contract_version,artifact_id,verification_id) REFERENCES public.acquisition_evidence_verifications(workspace_id,contract_id,contract_version,artifact_id,id),
 FOREIGN KEY(workspace_id,policy_id,kind,purpose,actor_id) REFERENCES private.acquisition_contract_review_policies(workspace_id,id,kind,purpose,reviewer_id)
);
ALTER TABLE public.acquisition_contract_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contract_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contract_reviews TO authenticated;
CREATE POLICY acquisition_contract_review_read ON public.acquisition_contract_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin') AND auth.jwt()->>'aal'='aal2');
CREATE TRIGGER acquisition_contract_review_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contract_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE FUNCTION private.contract_review_evidence_current(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_verification uuid,p_hash text,p_purpose text,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.acquisition_evidence_artifacts a
  JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.contract_id=a.contract_id
   AND v.contract_version=a.contract_version AND v.artifact_id=a.id AND v.contract_purpose=a.purpose AND v.id=p_verification
  JOIN private.acquisition_evidence_policies policy ON policy.workspace_id=a.workspace_id AND policy.id=a.retention_policy_id
  JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
  JOIN public.workspace_memberships m ON m.workspace_id=v.workspace_id AND m.user_id=v.actor_id
  JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.id=v.session_id AND s.user_id=v.actor_id
  WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.contract_version=p_version AND a.id=p_artifact
   AND a.purpose=p_purpose AND a.expected_sha256=p_hash AND a.created_at<=p_at AND a.retain_until>p_at
   AND policy.purpose=a.purpose AND policy.revoked_at IS NULL AND policy.valid_from<=p_at AND p_at<policy.valid_until
   AND v.scan_status='no_detection' AND v.created_at<=p_at
   AND v.id=(SELECT id FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1)
   AND k.revoked_at IS NULL AND k.valid_from<=p_at AND p_at<k.valid_until
   AND k.valid_from<=(v.observation->>'checked_at')::timestamptz
   AND k.scanner_version=v.observation->>'scanner_version' AND k.scan_policy_version=v.observation->>'scan_policy_version'
   AND ks.revoked_at IS NULL AND ks.valid_from<=p_at AND p_at<ks.valid_until
   AND ks.valid_from<=(v.observation->>'checked_at')::timestamptz
   AND m.status='active' AND m.role IN ('owner','admin','operator') AND m.updated_at=v.actor_membership_updated_at
   AND p.status='approved' AND (s.not_after IS NULL OR s.not_after>p_at)
   AND NOT EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations WHERE workspace_id=p_workspace AND artifact_id=p_artifact)
   AND NOT EXISTS(SELECT 1 FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND scan_status='detected' AND observation->>'sha256'=p_hash))
$$;
REVOKE ALL ON FUNCTION private.contract_review_evidence_current(uuid,uuid,integer,uuid,uuid,text,text,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.record_contract_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; verification public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; authority record;
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
  artifact.purpose:=prior.purpose; artifact.expected_sha256:=prior.sha256;
 ELSE
  SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
  IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.deals WHERE id=p_contract AND workspace_id=p_workspace AND acquisition_version=p_version
    AND acquisition_status NOT IN ('closed','cancelled','expired')) THEN
   RAISE EXCEPTION 'Current contract version required' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND id=p_artifact;
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
   OR NOT private.contract_review_evidence_current(p_workspace,p_contract,p_version,p_artifact,p_verification,artifact.expected_sha256,artifact.purpose,stamped) THEN
   RAISE EXCEPTION 'Current reviewed evidence and deadline required' USING ERRCODE='55000'; END IF;
 END IF;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,purpose,sha256,policy_id,
  actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at)
 VALUES(p_id,p_workspace,p_contract,p_version,p_kind,seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
  auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,'artifact_id',p_artifact,'verification_id',p_verification,
   'policy_id',p_policy,'expires_at',p_expires,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,'sequence',seq+1,
  'status',p_status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.record_contract_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_contract_review(p_id,p_workspace,p_contract,p_version,p_kind,p_expected_sequence,p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note)
$$;
REVOKE ALL ON FUNCTION private.record_contract_review(uuid,uuid,uuid,integer,text,integer,text,uuid,uuid,uuid,timestamptz,boolean,text),
 public.record_contract_review(uuid,uuid,uuid,integer,text,integer,text,uuid,uuid,uuid,timestamptz,boolean,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_contract_review(uuid,uuid,uuid,integer,text,integer,text,uuid,uuid,uuid,timestamptz,boolean,text),
 public.record_contract_review(uuid,uuid,uuid,integer,text,integer,text,uuid,uuid,uuid,timestamptz,boolean,text) TO authenticated;
CREATE FUNCTION private.contract_review_state(p_workspace uuid,p_contract uuid,p_version integer,p_kind text)
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
   AND private.contract_review_evidence_current(p_workspace,p_contract,p_version,latest.artifact_id,latest.verification_id,latest.sha256,latest.purpose,checked)
  INTO current_review;
 END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status='withdrawn' THEN 'withdrawn'
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind',p_kind,
  'sequence',coalesce(latest.sequence,0),'review_id',latest.id,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
CREATE FUNCTION public.contract_review_state(p_workspace uuid,p_contract uuid,p_version integer,p_kind text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.contract_review_state(p_workspace,p_contract,p_version,p_kind)
$$;
REVOKE ALL ON FUNCTION private.contract_review_state(uuid,uuid,integer,text),public.contract_review_state(uuid,uuid,integer,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.contract_review_state(uuid,uuid,integer,text),public.contract_review_state(uuid,uuid,integer,text) TO authenticated;
COMMIT;
