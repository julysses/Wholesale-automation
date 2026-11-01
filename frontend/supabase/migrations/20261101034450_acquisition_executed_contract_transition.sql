-- Add the reviewed pending_signature -> executed edge to the existing ledger.
-- No signature dispatch, legal title claim, marketing or disposition authority.
-- Compensation: pause acquisition/revoke current policy; preserve status and history.
-- A later correction must be a separately audited transition, never a history rewrite.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD CONSTRAINT acquisition_execution_transition_identity
 UNIQUE(workspace_id,contract_id,contract_version,id,kind);
ALTER TABLE public.acquisition_contract_transitions
 ALTER COLUMN signature_review_id DROP NOT NULL,
 ADD COLUMN execution_review_id uuid,
 ADD COLUMN execution_review_kind text,
 DROP CONSTRAINT acquisition_contract_transitions_check,
 ADD CONSTRAINT acquisition_transition_supported_edge CHECK(
  (previous_status='draft' AND recorded_status='pending_signature' AND sequence=1
   AND signature_review_id IS NOT NULL AND execution_review_id IS NULL AND execution_review_kind IS NULL)
  OR (previous_status='pending_signature' AND recorded_status='executed' AND sequence=2
   AND signature_review_id IS NULL AND execution_review_id IS NOT NULL AND execution_review_kind IS NOT NULL AND execution_review_kind='executed_contract')),
 ADD CONSTRAINT acquisition_transition_execution_source FOREIGN KEY(workspace_id,contract_id,contract_version,execution_review_id,execution_review_kind)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,id,kind);
ALTER TABLE public.deals DROP CONSTRAINT acquisition_deal_shape;
ALTER TABLE public.deals ADD CONSTRAINT acquisition_deal_shape CHECK(
 (workspace_id IS NULL AND acquisition_status IS NULL AND acquisition_version IS NULL AND acquisition_property_id IS NULL AND acquisition_owner_relationship_id IS NULL AND acquisition_offer_id IS NULL AND acquisition_offer_sequence IS NULL) OR
 (workspace_id IS NOT NULL AND acquisition_status IN ('draft','pending_signature','executed') AND acquisition_status IS NOT NULL AND acquisition_version BETWEEN 1 AND 2147483647 AND acquisition_version IS NOT NULL
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
  IF OLD.workspace_id IS NOT NULL AND ((OLD.acquisition_status='draft' AND NEW.acquisition_status='pending_signature') OR (OLD.acquisition_status='pending_signature' AND NEW.acquisition_status='executed'))
   AND (to_jsonb(NEW)-'acquisition_status'-'updated_at')=(to_jsonb(OLD)-'acquisition_status'-'updated_at')
   AND EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=NEW.workspace_id AND contract_id=NEW.id
    AND contract_version=NEW.acquisition_version AND previous_status=OLD.acquisition_status AND recorded_status=NEW.acquisition_status AND sequence=CASE WHEN NEW.acquisition_status='executed' THEN 2 ELSE 1 END) THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Immutable contract history and controlled version advancement required' USING ERRCODE='42501';
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
