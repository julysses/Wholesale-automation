-- Explicit same-contract supporting-document references; original bytes/history stay intact.
-- Term sources already provide immutable references and are not duplicated here.
-- Compensation: pause acquisition/revoke new RPC access; preserve links/revocations/audits.
BEGIN;
CREATE TABLE public.acquisition_contract_document_links (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 source_version integer NOT NULL CHECK(source_version>0 AND source_version<contract_version),
 artifact_id uuid NOT NULL, verification_id uuid NOT NULL, sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 note text NOT NULL CHECK(length(trim(note)) BETWEEN 20 AND 4000), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,contract_id,contract_version,artifact_id), UNIQUE(workspace_id,contract_id,contract_version,id),
 FOREIGN KEY(workspace_id,contract_id,contract_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 FOREIGN KEY(workspace_id,contract_id,source_version,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id),
 FOREIGN KEY(workspace_id,contract_id,source_version,artifact_id,verification_id) REFERENCES public.acquisition_evidence_verifications(workspace_id,contract_id,contract_version,artifact_id,id)
);
CREATE TABLE public.acquisition_contract_document_link_revocations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 link_id uuid NOT NULL UNIQUE, actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 20 AND 4000), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,contract_id,contract_version,link_id) REFERENCES public.acquisition_contract_document_links(workspace_id,contract_id,contract_version,id)
);
ALTER TABLE public.acquisition_contract_document_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.acquisition_contract_document_link_revocations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contract_document_links,public.acquisition_contract_document_link_revocations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contract_document_links,public.acquisition_contract_document_link_revocations TO authenticated;
CREATE POLICY contract_document_links_read ON public.acquisition_contract_document_links FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator') AND auth.jwt()->>'aal'='aal2');
CREATE POLICY contract_document_link_revocations_read ON public.acquisition_contract_document_link_revocations FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator') AND auth.jwt()->>'aal'='aal2');
CREATE TRIGGER contract_document_links_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contract_document_links
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE TRIGGER contract_document_link_revocations_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contract_document_link_revocations
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.link_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_source_version integer,
 p_artifact uuid,p_verification uuid,p_sha256 text,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_document_links%ROWTYPE; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 scan public.acquisition_evidence_verifications%ROWTYPE; stamped timestamptz; active boolean;
BEGIN
 IF p_id IS NULL OR p_source_version IS NULL OR p_version IS NULL OR p_source_version<1 OR p_source_version>=p_version
  OR p_artifact IS NULL OR p_verification IS NULL OR p_sha256 IS NULL OR p_sha256 !~ '^[0-9a-f]{64}$'
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 4000 OR length(p_note)>4000 THEN
  RAISE EXCEPTION 'Exact earlier source and link note required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin','operator']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-document-link:'||p_id::text,0));
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Link session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_document_links WHERE id=p_id;
 IF FOUND THEN
  IF (saved.workspace_id,saved.contract_id,saved.contract_version,saved.source_version,saved.artifact_id,saved.verification_id,saved.sha256,saved.note,saved.actor_id)
   IS DISTINCT FROM (p_workspace,p_contract,p_version,p_source_version,p_artifact,p_verification,p_sha256,p_note,auth.uid()) THEN
   RAISE EXCEPTION 'Document link request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('link_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
   'source_version',p_source_version,'artifact_id',p_artifact,'duplicate',true,'review_approved',false,'execution_authorized',false);
 END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true OR NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='draft') THEN
  RAISE EXCEPTION 'Current active draft required' USING ERRCODE='55000'; END IF;
 IF EXISTS(SELECT 1 FROM public.acquisition_contract_term_sources WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND artifact_id=p_artifact) THEN
  RAISE EXCEPTION 'Document already referenced by recorded terms' USING ERRCODE='55000'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_source_version AND id=p_artifact AND expected_sha256=p_sha256 AND campaign_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Same-contract original source required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||p_sha256,0));
 SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact AND id=p_verification;
 IF NOT FOUND THEN RAISE EXCEPTION 'Exact source verification required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
  JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
  JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=scan.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.id=scan.session_id AND sess.user_id=m.user_id
  WHERE k.workspace_id=p_workspace AND k.id=scan.key_id FOR SHARE OF k,ks,rp,m,profile,sess;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Link session expired' USING ERRCODE='42501'; END IF;
 IF NOT private.contract_review_evidence_current(p_workspace,p_contract,p_source_version,p_artifact,p_verification,p_sha256,artifact.purpose,stamped) THEN
  RAISE EXCEPTION 'Current verified original source required' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_contract_document_links(id,workspace_id,contract_id,contract_version,source_version,artifact_id,verification_id,sha256,actor_id,session_id,note,created_at)
 VALUES(p_id,p_workspace,p_contract,p_version,p_source_version,p_artifact,p_verification,p_sha256,auth.uid(),(auth.jwt()->>'session_id')::uuid,p_note,stamped);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_document_link',p_id::text,'linked',auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'source_version',p_source_version,'artifact_id',p_artifact,'verification_id',p_verification,'execution_authorized',false));
 RETURN jsonb_build_object('link_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'source_version',p_source_version,'artifact_id',p_artifact,'duplicate',false,'review_approved',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.link_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_source_version integer,p_artifact uuid,p_verification uuid,p_sha256 text,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.link_contract_document(p_id,p_workspace,p_contract,p_version,p_source_version,p_artifact,p_verification,p_sha256,p_note) $$;
REVOKE ALL ON FUNCTION private.link_contract_document(uuid,uuid,uuid,integer,integer,uuid,uuid,text,text),public.link_contract_document(uuid,uuid,uuid,integer,integer,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.link_contract_document(uuid,uuid,uuid,integer,integer,uuid,uuid,text,text),public.link_contract_document(uuid,uuid,uuid,integer,integer,uuid,uuid,text,text) TO authenticated;

CREATE FUNCTION private.revoke_contract_document_link(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_link uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_document_link_revocations%ROWTYPE; stamped timestamptz;
BEGIN
 IF p_id IS NULL OR p_link IS NULL OR p_reason IS NULL OR length(trim(p_reason)) NOT BETWEEN 20 AND 4000 OR length(p_reason)>4000 THEN
  RAISE EXCEPTION 'Exact document link withdrawal required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin','operator']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-document-link-revocation:'||p_id::text,0));
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Withdrawal session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_document_link_revocations WHERE id=p_id;
 IF FOUND THEN
  IF (saved.workspace_id,saved.contract_id,saved.contract_version,saved.link_id,saved.reason,saved.actor_id)
   IS DISTINCT FROM (p_workspace,p_contract,p_version,p_link,p_reason,auth.uid()) THEN
   RAISE EXCEPTION 'Link withdrawal request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('revocation_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'link_id',p_link,'duplicate',true,'execution_authorized',false);
 END IF;
 PERFORM 1 FROM public.acquisition_contract_document_links WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND id=p_link;
 IF NOT FOUND THEN RAISE EXCEPTION 'Document link unavailable' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_contract_document_link_revocations(id,workspace_id,contract_id,contract_version,link_id,actor_id,session_id,reason,created_at)
 VALUES(p_id,p_workspace,p_contract,p_version,p_link,auth.uid(),(auth.jwt()->>'session_id')::uuid,p_reason,stamped);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_document_link',p_link::text,'revoked',auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'revocation_id',p_id,'execution_authorized',false));
 RETURN jsonb_build_object('revocation_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'link_id',p_link,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.revoke_contract_document_link(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_link uuid,p_reason text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.revoke_contract_document_link(p_id,p_workspace,p_contract,p_version,p_link,p_reason) $$;
REVOKE ALL ON FUNCTION private.revoke_contract_document_link(uuid,uuid,uuid,integer,uuid,text),public.revoke_contract_document_link(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.revoke_contract_document_link(uuid,uuid,uuid,integer,uuid,text),public.revoke_contract_document_link(uuid,uuid,uuid,integer,uuid,text) TO authenticated;

-- Internal identity resolver: callers must separately enforce user scope and fresh evidence.
-- This helper does not confer review, byte access, or execution authority.
CREATE FUNCTION private.contract_document_reference(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS TABLE(source_version integer,reference_type text,link_id uuid,link_revoked boolean)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT a.contract_version,
  CASE WHEN a.contract_version=p_version THEN 'native' WHEN EXISTS(SELECT 1 FROM public.acquisition_contract_term_sources t
   WHERE t.workspace_id=p_workspace AND t.contract_id=p_contract AND t.contract_version=p_version AND t.artifact_id=a.id) THEN 'term_source' ELSE 'linked' END,
  l.id,EXISTS(SELECT 1 FROM public.acquisition_contract_document_link_revocations r WHERE r.link_id=l.id)
 FROM public.acquisition_evidence_artifacts a
 LEFT JOIN public.acquisition_contract_document_links l ON l.workspace_id=p_workspace AND l.contract_id=p_contract AND l.contract_version=p_version AND l.artifact_id=a.id
 WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.id=p_artifact AND a.campaign_id IS NULL AND a.contract_version<=p_version
 AND (a.contract_version=p_version OR l.id IS NOT NULL OR EXISTS(SELECT 1 FROM public.acquisition_contract_term_sources t
  WHERE t.workspace_id=p_workspace AND t.contract_id=p_contract AND t.contract_version=p_version AND t.artifact_id=a.id))
$$;
REVOKE ALL ON FUNCTION private.contract_document_reference(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.contract_reference_state(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE ref record; artifact public.acquisition_evidence_artifacts%ROWTYPE; scan public.acquisition_evidence_verifications%ROWTYPE;
 checked timestamptz:=statement_timestamp(); source_state jsonb; status_name text;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Contract source authority required' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract version unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract source unavailable' USING ERRCODE='42501'; END IF;
 source_state:=private.contract_document_state(p_workspace,p_contract,ref.source_version,p_artifact);
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE id=p_artifact;
 SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 IF ref.link_revoked THEN status_name:='reference_withdrawn';
 ELSIF source_state->>'status'='revoked' THEN status_name:='source_revoked';
 ELSIF scan.id IS NULL OR NOT private.contract_review_evidence_current(p_workspace,p_contract,ref.source_version,p_artifact,scan.id,artifact.expected_sha256,artifact.purpose,checked) THEN status_name:='requires_review';
 ELSE status_name:='available_for_review'; END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'artifact_id',p_artifact,
  'source_version',ref.source_version,'reference_type',ref.reference_type,'link_id',ref.link_id,'status',status_name,
  'purpose',artifact.purpose,'sha256',artifact.expected_sha256,'verification_id',CASE WHEN status_name='available_for_review' THEN scan.id ELSE NULL END,
  'checked_at',checked,'review_approved',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.contract_reference_state(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.contract_reference_state(p_workspace,p_contract,p_version,p_artifact) $$;
REVOKE ALL ON FUNCTION private.contract_reference_state(uuid,uuid,integer,uuid),public.contract_reference_state(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.contract_reference_state(uuid,uuid,integer,uuid),public.contract_reference_state(uuid,uuid,integer,uuid) TO authenticated;
COMMIT;
