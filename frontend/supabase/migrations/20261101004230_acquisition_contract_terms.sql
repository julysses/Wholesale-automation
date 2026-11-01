-- Immutable draft terms on canonical deals. Source links retain original artifacts;
-- no copied uploads, signatures, review carry-over or legacy stage changes.
-- Compensation: pause acquisition / revoke new RPC access, preserve versions/audits.
BEGIN;
CREATE FUNCTION private.valid_contract_terms(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE field text; item jsonb; source jsonb; names text[]:=ARRAY[]::text[]; known boolean;
BEGIN
 IF value IS NULL OR jsonb_typeof(value)<>'object' OR NOT(value ?& ARRAY['purchase_price_cents','earnest_money_cents','assignment_allowed','assignment_provisions','effective','inspection_deadline','closing_deadline','sources','note'])
  OR (SELECT count(*) FROM jsonb_object_keys(value))<>9 OR jsonb_typeof(value->'sources')<>'array'
  OR jsonb_array_length(value->'sources')>6 OR jsonb_typeof(value->'note')<>'string' OR length(trim(value->>'note')) NOT BETWEEN 20 AND 4000 THEN RETURN false; END IF;
 FOREACH field IN ARRAY ARRAY['purchase_price_cents','earnest_money_cents'] LOOP
  IF value->field<>'null'::jsonb AND (jsonb_typeof(value->field)<>'number' OR value->>field !~ '^[0-9]+$'
    OR (value->>field)::numeric>9007199254740991 OR (field='purchase_price_cents' AND (value->>field)::numeric=0)) THEN RETURN false; END IF;
 END LOOP;
 IF value->'assignment_allowed'<>'null'::jsonb AND jsonb_typeof(value->'assignment_allowed')<>'boolean' THEN RETURN false; END IF;
 IF value->'assignment_provisions'<>'null'::jsonb AND (jsonb_typeof(value->'assignment_provisions')<>'string' OR length(trim(value->>'assignment_provisions')) NOT BETWEEN 1 AND 4000) THEN RETURN false; END IF;
 IF value->'assignment_allowed'<>'null'::jsonb AND value->'assignment_provisions'='null'::jsonb THEN RETURN false; END IF;
 FOREACH field IN ARRAY ARRAY['effective','inspection_deadline','closing_deadline'] LOOP
  item:=value->field;
  IF jsonb_typeof(item)<>'object' OR NOT(item ? 'precision') OR EXISTS(SELECT 1 FROM jsonb_object_keys(item) k WHERE k NOT IN ('precision','calendar_date','instant')) THEN RETURN false; END IF;
  IF item->>'precision'='unknown' THEN
   IF coalesce(item->'calendar_date','null'::jsonb)<>'null'::jsonb OR coalesce(item->'instant','null'::jsonb)<>'null'::jsonb THEN RETURN false; END IF;
  ELSIF item->>'precision'='date' THEN
   IF coalesce(jsonb_typeof(item->'calendar_date'),'')<>'string' OR item->>'calendar_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    OR coalesce(item->'instant','null'::jsonb)<>'null'::jsonb OR to_char((item->>'calendar_date')::date,'YYYY-MM-DD')<>item->>'calendar_date' THEN RETURN false; END IF;
  ELSIF item->>'precision'='instant' THEN
   IF coalesce(jsonb_typeof(item->'instant'),'')<>'string' OR item->>'instant' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'
    OR coalesce(item->'calendar_date','null'::jsonb)<>'null'::jsonb OR NOT isfinite((item->>'instant')::timestamptz) THEN RETURN false; END IF;
  ELSE RETURN false; END IF;
 END LOOP;
 FOR source IN SELECT * FROM jsonb_array_elements(value->'sources') LOOP
  IF jsonb_typeof(source)<>'object' OR NOT(source ?& ARRAY['term','artifact_id','artifact_version','sha256','locator']) OR (SELECT count(*) FROM jsonb_object_keys(source))<>5
   OR source->>'term' IS NULL OR source->>'term' NOT IN ('purchase_price','earnest_money','assignment','effective','inspection_deadline','closing_deadline')
   OR source->>'term'=ANY(names) OR jsonb_typeof(source->'artifact_id')<>'string'
   OR jsonb_typeof(source->'artifact_version')<>'number' OR source->>'artifact_version' !~ '^[0-9]+$'
   OR (source->>'artifact_version')::numeric NOT BETWEEN 1 AND 2147483647
   OR jsonb_typeof(source->'sha256')<>'string' OR source->>'sha256' !~ '^[0-9a-f]{64}$'
   OR jsonb_typeof(source->'locator')<>'string' OR length(trim(source->>'locator')) NOT BETWEEN 1 AND 1000
   OR source->>'locator' ~ '[[:cntrl:]]' THEN RETURN false; END IF;
  PERFORM (source->>'artifact_id')::uuid;
  names:=array_append(names,source->>'term');
 END LOOP;
 FOREACH field IN ARRAY ARRAY['purchase_price','earnest_money','assignment','effective','inspection_deadline','closing_deadline'] LOOP
  known:=CASE WHEN field IN ('purchase_price','earnest_money') THEN value->(field||'_cents')<>'null'::jsonb
   WHEN field='assignment' THEN value->'assignment_allowed'<>'null'::jsonb OR value->'assignment_provisions'<>'null'::jsonb
   ELSE value->field->>'precision'<>'unknown' END;
  IF known AND NOT(field=ANY(names)) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR numeric_value_out_of_range THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_contract_terms(jsonb) FROM PUBLIC,anon,authenticated,service_role;
ALTER TABLE public.acquisition_contract_versions DROP CONSTRAINT acquisition_contract_versions_version_check,
 ADD CONSTRAINT acquisition_contract_versions_version_check CHECK(version BETWEEN 1 AND 2147483647),
 ADD COLUMN terms jsonb,
 ADD COLUMN previous_version integer,
 ADD COLUMN session_id uuid,
 ADD CONSTRAINT acquisition_contract_terms_shape CHECK((version=1 AND terms IS NULL AND previous_version IS NULL AND session_id IS NULL)
  OR (version>1 AND previous_version=version-1 AND previous_version IS NOT NULL AND terms IS NOT NULL AND session_id IS NOT NULL AND private.valid_contract_terms(terms))),
 ADD CONSTRAINT acquisition_contract_previous_version FOREIGN KEY(workspace_id,deal_id,previous_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version);
-- Keep every original draft guard; only lift the single-version restriction.
ALTER TABLE public.deals DROP CONSTRAINT acquisition_deal_shape;
ALTER TABLE public.deals ADD CONSTRAINT acquisition_deal_shape CHECK(
 (workspace_id IS NULL AND acquisition_status IS NULL AND acquisition_version IS NULL AND acquisition_property_id IS NULL AND acquisition_owner_relationship_id IS NULL AND acquisition_offer_id IS NULL AND acquisition_offer_sequence IS NULL) OR
 (workspace_id IS NOT NULL AND acquisition_status='draft' AND acquisition_status IS NOT NULL AND acquisition_version BETWEEN 1 AND 2147483647 AND acquisition_version IS NOT NULL
 AND acquisition_property_id IS NOT NULL AND acquisition_owner_relationship_id IS NOT NULL AND acquisition_offer_id IS NOT NULL AND acquisition_offer_sequence>0 AND acquisition_offer_sequence IS NOT NULL
 AND stage='offer_made' AND contract_price IS NULL AND buyer_id IS NULL AND contract_date IS NULL AND closing_date IS NULL AND actual_close_date IS NULL AND psa_doc_url IS NULL AND assignment_doc_url IS NULL));
CREATE TABLE public.acquisition_contract_term_sources (
 workspace_id uuid NOT NULL, contract_id uuid NOT NULL, contract_version integer NOT NULL,
 term text NOT NULL CHECK(term IN ('purchase_price','earnest_money','assignment','effective','inspection_deadline','closing_deadline')),
 artifact_version integer NOT NULL CHECK(artifact_version>0 AND artifact_version<contract_version),
 artifact_id uuid NOT NULL, verification_id uuid NOT NULL, sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 locator text NOT NULL CHECK(length(trim(locator)) BETWEEN 1 AND 1000),
 PRIMARY KEY(workspace_id,contract_id,contract_version,term),
 FOREIGN KEY(workspace_id,contract_id,contract_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 FOREIGN KEY(workspace_id,contract_id,artifact_version,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id),
 FOREIGN KEY(workspace_id,contract_id,artifact_version,artifact_id,verification_id) REFERENCES public.acquisition_evidence_verifications(workspace_id,contract_id,contract_version,artifact_id,id)
);
ALTER TABLE public.acquisition_contract_term_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contract_term_sources FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contract_term_sources TO authenticated;
CREATE POLICY acquisition_term_sources_read ON public.acquisition_contract_term_sources FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator') AND auth.jwt()->>'aal'='aal2');
CREATE TRIGGER acquisition_term_sources_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contract_term_sources
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
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
  IF OLD.workspace_id IS NOT NULL AND NEW.acquisition_version=OLD.acquisition_version+1
   AND (to_jsonb(NEW)-'acquisition_version'-'updated_at')=(to_jsonb(OLD)-'acquisition_version'-'updated_at')
   AND EXISTS(SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=NEW.workspace_id AND deal_id=NEW.id AND version=NEW.acquisition_version) THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Immutable contract history and controlled version advancement required' USING ERRCODE='42501';
END $$;
CREATE FUNCTION private.save_contract_terms(p_id uuid,p_workspace uuid,p_contract uuid,p_expected_version integer,p_terms jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_versions%ROWTYPE; source jsonb; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 scan public.acquisition_evidence_verifications%ROWTYPE; manifest jsonb; active boolean; stamped timestamptz; new_version integer;
BEGIN
 IF p_id IS NULL OR p_expected_version IS NULL OR p_expected_version NOT BETWEEN 1 AND 2147483646 OR NOT private.valid_contract_terms(p_terms) THEN
  RAISE EXCEPTION 'Exact sourced draft terms required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_expected_version,ARRAY['owner','admin','operator']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-terms-request:'||p_id::text,0));
 manifest:=jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'expected_version',p_expected_version,'terms',p_terms);
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Terms session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_versions WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM p_workspace OR saved.deal_id IS DISTINCT FROM p_contract OR saved.actor_id IS DISTINCT FROM auth.uid() OR saved.request IS DISTINCT FROM manifest THEN
   RAISE EXCEPTION 'Terms request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('request_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'version',saved.version,'status','draft','duplicate',true,'execution_authorized',false);
 END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true OR NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_expected_version AND acquisition_status='draft') THEN
  RAISE EXCEPTION 'Current active draft required' USING ERRCODE='55000'; END IF;
 new_version:=p_expected_version+1;
 -- Artifact ordering matches shared scan/revocation locks and avoids cross-source inversions.
 FOR source IN SELECT value FROM jsonb_array_elements(p_terms->'sources') ORDER BY (value->>'artifact_id')::uuid,value->>'term' LOOP
  IF (source->>'artifact_version')::integer>p_expected_version THEN RAISE EXCEPTION 'Future term source denied' USING ERRCODE='22023'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(source->>'artifact_id')::uuid::text,0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=(source->>'artifact_version')::integer
   AND id=(source->>'artifact_id')::uuid AND expected_sha256=source->>'sha256' AND campaign_id IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Exact same-contract source unavailable' USING ERRCODE='42501'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
  SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=artifact.id ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'Verified source required' USING ERRCODE='55000'; END IF;
  PERFORM 1 FROM private.acquisition_evidence_verification_keys k
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=scan.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.id=scan.session_id AND sess.user_id=m.user_id
   WHERE k.workspace_id=p_workspace AND k.id=scan.key_id FOR SHARE OF k,ks,rp,m,profile,sess;
  IF NOT private.contract_review_evidence_current(p_workspace,p_contract,artifact.contract_version,artifact.id,scan.id,artifact.expected_sha256,artifact.purpose,clock_timestamp()) THEN
   RAISE EXCEPTION 'Current verified source required' USING ERRCODE='55000'; END IF;
 END LOOP;
 stamped:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN RAISE EXCEPTION 'Terms session expired' USING ERRCODE='42501'; END IF;
 -- Recheck every source after all lock waits, including expired earlier sources.
 FOR source IN SELECT * FROM jsonb_array_elements(p_terms->'sources') LOOP
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE id=(source->>'artifact_id')::uuid;
  SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=artifact.id ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT private.contract_review_evidence_current(p_workspace,p_contract,artifact.contract_version,artifact.id,scan.id,artifact.expected_sha256,artifact.purpose,stamped) THEN
   RAISE EXCEPTION 'Source authority expired while waiting' USING ERRCODE='55000'; END IF;
 END LOOP;
 INSERT INTO public.acquisition_contract_versions(id,workspace_id,deal_id,version,status,request,actor_id,created_at,terms,previous_version,session_id)
 VALUES(p_id,p_workspace,p_contract,new_version,'draft',manifest,auth.uid(),stamped,p_terms,p_expected_version,(auth.jwt()->>'session_id')::uuid);
 FOR source IN SELECT * FROM jsonb_array_elements(p_terms->'sources') LOOP
  SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=(source->>'artifact_id')::uuid ORDER BY created_at DESC,id DESC LIMIT 1;
  INSERT INTO public.acquisition_contract_term_sources(workspace_id,contract_id,contract_version,term,artifact_version,artifact_id,verification_id,sha256,locator)
  VALUES(p_workspace,p_contract,new_version,source->>'term',(source->>'artifact_version')::integer,(source->>'artifact_id')::uuid,scan.id,source->>'sha256',source->>'locator');
 END LOOP;
 UPDATE public.deals SET acquisition_version=new_version WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_expected_version;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_terms',p_id::text,'prepared',auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,'version',new_version,'previous_version',p_expected_version,'source_count',jsonb_array_length(p_terms->'sources'),'execution_authorized',false));
 RETURN jsonb_build_object('request_id',p_id,'workspace_id',p_workspace,'contract_id',p_contract,'version',new_version,'status','draft','duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.save_contract_terms(p_id uuid,p_workspace uuid,p_contract uuid,p_expected_version integer,p_terms jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.save_contract_terms(p_id,p_workspace,p_contract,p_expected_version,p_terms) $$;
REVOKE ALL ON FUNCTION private.save_contract_terms(uuid,uuid,uuid,integer,jsonb),public.save_contract_terms(uuid,uuid,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.save_contract_terms(uuid,uuid,uuid,integer,jsonb),public.save_contract_terms(uuid,uuid,uuid,integer,jsonb) TO authenticated;
COMMIT;
