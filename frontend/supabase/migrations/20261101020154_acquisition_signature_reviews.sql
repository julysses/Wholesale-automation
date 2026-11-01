-- Separate human signature-release review; no signing, delivery or state transition.
-- No authority policies are seeded. Compensation: revoke policy / pause activation,
-- preserving immutable decisions and their exact underlying contract review.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD CONSTRAINT acquisition_review_identity
 UNIQUE(workspace_id,contract_id,contract_version,id);
CREATE TABLE private.acquisition_signature_policies (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 reviewer_id uuid NOT NULL REFERENCES public.profiles(id), basis_policy_id uuid NOT NULL,
 artifact_id uuid NOT NULL, source_version integer NOT NULL, sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 template_approval_ref uuid NOT NULL, approved_by uuid NOT NULL REFERENCES public.profiles(id),
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)), valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 revoked_at timestamptz CHECK(isfinite(revoked_at)), max_review_seconds integer NOT NULL CHECK(max_review_seconds BETWEEN 1 AND 86400),
 CHECK(valid_from<valid_until), UNIQUE(workspace_id,id,reviewer_id),
 FOREIGN KEY(workspace_id,contract_id,contract_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 FOREIGN KEY(workspace_id,contract_id,source_version,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id),
 FOREIGN KEY(basis_policy_id) REFERENCES private.acquisition_contract_review_policies(id)
);
ALTER TABLE private.acquisition_signature_policies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_signature_policies FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE public.acquisition_signature_reviews (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 sequence integer NOT NULL CHECK(sequence>0), status text NOT NULL CHECK(status IN ('approved','withdrawn')),
 basis_review_id uuid NOT NULL, policy_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 actor_membership_updated_at timestamptz NOT NULL, personally_reviewed boolean NOT NULL,
 note text NOT NULL CHECK(length(trim(note)) BETWEEN 20 AND 4000), expires_at timestamptz,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((status='approved' AND personally_reviewed AND expires_at IS NOT NULL AND isfinite(expires_at) AND expires_at>created_at)
  OR (status='withdrawn' AND NOT personally_reviewed AND expires_at IS NULL)),
 UNIQUE(workspace_id,contract_id,contract_version,sequence),
 FOREIGN KEY(workspace_id,contract_id,contract_version,basis_review_id) REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,id),
 FOREIGN KEY(workspace_id,policy_id,actor_id) REFERENCES private.acquisition_signature_policies(workspace_id,id,reviewer_id)
);
ALTER TABLE public.acquisition_signature_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_signature_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_signature_reviews TO authenticated;
CREATE POLICY acquisition_signature_review_read ON public.acquisition_signature_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin') AND auth.jwt()->>'aal'='aal2');
CREATE TRIGGER acquisition_signature_review_immutable BEFORE UPDATE OR DELETE ON public.acquisition_signature_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

-- Caller supplies current time only inside private controlled functions after locks.
CREATE FUNCTION private.signature_basis_current(p_workspace uuid,p_contract uuid,p_version integer,p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.acquisition_contract_reviews r
 JOIN private.acquisition_contract_review_policies policy ON policy.id=r.policy_id AND policy.workspace_id=r.workspace_id
 JOIN public.workspace_memberships m ON m.workspace_id=r.workspace_id AND m.user_id=r.actor_id
 JOIN public.profiles profile ON profile.id=m.user_id
 JOIN auth.sessions sess ON sess.id=r.session_id AND sess.user_id=r.actor_id
 JOIN public.deals d ON d.workspace_id=r.workspace_id AND d.id=r.contract_id
 JOIN public.acquisition_contract_versions v ON v.workspace_id=d.workspace_id AND v.deal_id=d.id AND v.version=d.acquisition_version
 WHERE r.id=p_review AND r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version
 AND r.kind='contract_review' AND r.status='approved' AND r.created_at<=p_at AND p_at<r.expires_at
 AND r.id=(SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='contract_review' ORDER BY sequence DESC LIMIT 1)
 AND d.acquisition_version=p_version AND d.acquisition_status='draft'
 AND v.terms->'purchase_price_cents'<>'null'::jsonb AND v.terms->'earnest_money_cents'<>'null'::jsonb
 AND (v.terms->>'purchase_price_cents')::numeric>0
 AND (v.terms->>'earnest_money_cents')::numeric<=(v.terms->>'purchase_price_cents')::numeric
 AND policy.kind=r.kind AND policy.purpose=r.purpose AND policy.reviewer_id=r.actor_id AND policy.revoked_at IS NULL
 AND policy.valid_from<=r.created_at AND p_at<policy.valid_until
 AND r.expires_at<=r.created_at+make_interval(secs=>policy.max_review_seconds)
 AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=r.actor_membership_updated_at
 AND profile.status='approved' AND (sess.not_after IS NULL OR p_at<sess.not_after)
 AND EXISTS(SELECT 1 FROM private.contract_document_reference(p_workspace,p_contract,p_version,r.artifact_id) ref
  WHERE ref.source_version=r.source_version AND NOT ref.link_revoked)
 AND private.contract_review_evidence_current(p_workspace,p_contract,r.source_version,r.artifact_id,r.verification_id,r.sha256,r.purpose,p_at))
$$;
REVOKE ALL ON FUNCTION private.signature_basis_current(uuid,uuid,integer,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_signature_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_basis uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; prior public.acquisition_signature_reviews%ROWTYPE; saved public.acquisition_signature_reviews%ROWTYPE;
 basis public.acquisition_contract_reviews%ROWTYPE; policy private.acquisition_signature_policies%ROWTYPE;
 fingerprint text; stamped timestamptz; seq integer; active boolean;
BEGIN
 IF p_id IS NULL OR p_basis IS NULL OR p_policy IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('approved','withdrawn') OR p_personally_reviewed IS NULL
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 4000
  OR (p_status='approved' AND (NOT p_personally_reviewed OR p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL)) THEN
  RAISE EXCEPTION 'Exact signature review request required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('signature-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_basis,p_policy,
  p_expires,p_personally_reviewed,p_note,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Signature review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_signature_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Signature review request conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO prior FROM public.acquisition_signature_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Signature review sequence changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS NULL OR prior.status<>'approved' OR prior.actor_id<>auth.uid() OR prior.basis_review_id<>p_basis OR prior.policy_id<>p_policy THEN
    RAISE EXCEPTION 'Original signature review required for withdrawal' USING ERRCODE='55000'; END IF;
  ELSE
   SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
   IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
   SELECT * INTO basis FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND id=p_basis AND kind='contract_review';
   IF NOT FOUND THEN RAISE EXCEPTION 'Exact contract review required' USING ERRCODE='42501'; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||basis.artifact_id::text,0));
   PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||basis.sha256,0));
   SELECT * INTO policy FROM private.acquisition_signature_policies WHERE id=p_policy AND workspace_id=p_workspace
    AND contract_id=p_contract AND contract_version=p_version AND reviewer_id=auth.uid()
    AND basis_policy_id=basis.policy_id AND artifact_id=basis.artifact_id AND source_version=basis.source_version AND sha256=basis.sha256 FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Exact signature reviewer policy required' USING ERRCODE='42501'; END IF;
   -- Pin underlying review and scanner authority through commit. All review writes
   -- for this contract share deal-ref; shared identity locks do not mutate authority.
   PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id=basis.policy_id FOR SHARE;
   PERFORM 1 FROM public.acquisition_evidence_artifacts a
    JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.artifact_id=a.id AND v.id=basis.verification_id
    JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=a.workspace_id AND rp.id=a.retention_policy_id
    JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
    JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
    WHERE a.workspace_id=p_workspace AND a.id=basis.artifact_id FOR SHARE OF rp,k,ks;
   PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
    JOIN auth.sessions sess ON sess.user_id=m.user_id
    WHERE m.workspace_id=p_workspace AND (sess.id=basis.session_id OR sess.id=(SELECT session_id FROM public.acquisition_evidence_verifications WHERE id=basis.verification_id))
    ORDER BY m.user_id,sess.id FOR SHARE OF m,profile,sess;
   stamped:=clock_timestamp();
   IF policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
    OR p_expires<=stamped OR p_expires>policy.valid_until OR p_expires>basis.expires_at
    OR p_expires>stamped+make_interval(secs=>policy.max_review_seconds)
    OR (authority.session_expires IS NOT NULL AND p_expires>authority.session_expires)
    OR NOT private.signature_basis_current(p_workspace,p_contract,p_version,p_basis,stamped) THEN
    RAISE EXCEPTION 'Current contract review and bounded signature approval required' USING ERRCODE='55000'; END IF;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Signature review session expired' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_signature_reviews(id,workspace_id,contract_id,contract_version,sequence,status,basis_review_id,policy_id,
   actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at)
  VALUES(p_id,p_workspace,p_contract,p_version,seq+1,p_status,p_basis,p_policy,auth.uid(),(auth.jwt()->>'session_id')::uuid,
   authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_signature_review',p_id::text,p_status,auth.uid()::text,p_workspace,
   jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'sequence',saved.sequence,'basis_review_id',p_basis,'policy_id',p_policy,'execution_authorized',false));
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
   'sequence',saved.sequence,'status',saved.status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_signature_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,timestamptz,boolean,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_signature_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,timestamptz,boolean,text) TO authenticated;
CREATE FUNCTION public.record_signature_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_basis uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_signature_review(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_basis,p_policy,p_expires,p_personally_reviewed,p_note) $$;
REVOKE ALL ON FUNCTION public.record_signature_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,timestamptz,boolean,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_signature_review(uuid,uuid,uuid,integer,integer,text,uuid,uuid,timestamptz,boolean,text) TO authenticated;
CREATE FUNCTION private.signature_review_state(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_signature_reviews%ROWTYPE; checked timestamptz; current_review boolean:=false;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin')
  OR NOT EXISTS(SELECT 1 FROM auth.sessions WHERE user_id=auth.uid() AND id::text=auth.jwt()->>'session_id'
   AND (not_after IS NULL OR not_after>clock_timestamp()))
  OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Signature review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_signature_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
 checked:=clock_timestamp();
 IF latest.status='approved' AND latest.created_at<=checked AND checked<latest.expires_at THEN
  SELECT EXISTS(SELECT 1 FROM private.acquisition_signature_policies policy
   JOIN public.acquisition_contract_reviews basis ON basis.id=latest.basis_review_id AND basis.workspace_id=policy.workspace_id
   JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=latest.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.id=latest.session_id AND sess.user_id=m.user_id
   WHERE policy.id=latest.policy_id AND policy.workspace_id=p_workspace AND policy.contract_id=p_contract AND policy.contract_version=p_version
    AND policy.reviewer_id=latest.actor_id AND policy.basis_policy_id=basis.policy_id AND policy.artifact_id=basis.artifact_id
    AND policy.source_version=basis.source_version AND policy.sha256=basis.sha256 AND policy.revoked_at IS NULL
    AND policy.valid_from<=latest.created_at AND checked<policy.valid_until
    AND latest.expires_at<=latest.created_at+make_interval(secs=>policy.max_review_seconds)
    AND latest.expires_at<=policy.valid_until AND latest.expires_at<=basis.expires_at
    AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=latest.actor_membership_updated_at
    AND profile.status='approved' AND (sess.not_after IS NULL OR checked<sess.not_after))
   AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
   AND private.signature_basis_current(p_workspace,p_contract,p_version,latest.basis_review_id,checked)
  INTO current_review;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'review_id',latest.id,'sequence',coalesce(latest.sequence,0),'basis_review_id',latest.basis_review_id,
  'status',CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status='withdrawn' THEN 'withdrawn' WHEN current_review THEN 'approved' ELSE 'requires_review' END,
  'approval_current',current_review,'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,
  'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.signature_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.signature_review_state(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.signature_review_state(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.signature_review_state(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.signature_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.signature_review_state(uuid,uuid,integer) TO authenticated;
COMMIT;
