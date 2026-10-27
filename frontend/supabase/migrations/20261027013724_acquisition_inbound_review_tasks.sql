-- Additive review-only call requests in the existing task relation. No execution.
BEGIN;
ALTER TABLE public.tasks
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_integration_id uuid,
 ADD COLUMN acquisition_call_id text,
 ADD COLUMN acquisition_request_id uuid,
 ADD COLUMN acquisition_revision integer,
 ADD COLUMN acquisition_request_kind text,
 ADD COLUMN acquisition_evidence jsonb,
 ADD COLUMN acquisition_request_hash text,
 ADD COLUMN acquisition_phone text,
 ADD CONSTRAINT acquisition_task_route_fk FOREIGN KEY(acquisition_integration_id,workspace_id)
 REFERENCES private.acquisition_inbound_routes(integration_id,workspace_id),
 ADD CONSTRAINT acquisition_task_shape CHECK (
  (workspace_id IS NULL AND acquisition_integration_id IS NULL AND acquisition_call_id IS NULL
   AND acquisition_request_id IS NULL AND acquisition_revision IS NULL AND acquisition_request_kind IS NULL
   AND acquisition_evidence IS NULL AND acquisition_request_hash IS NULL AND acquisition_phone IS NULL)
  OR (workspace_id IS NOT NULL AND acquisition_integration_id IS NOT NULL AND acquisition_call_id IS NOT NULL
   AND acquisition_call_id ~ '^[A-Za-z0-9_-]{1,200}$' AND acquisition_request_id IS NOT NULL
   AND acquisition_revision IS NOT NULL AND acquisition_revision>0 AND acquisition_request_kind IS NOT NULL
   AND acquisition_request_kind IN ('request_callback','request_human')
   AND acquisition_evidence IS NOT NULL AND jsonb_typeof(acquisition_evidence)='object'
   AND acquisition_request_hash IS NOT NULL AND acquisition_request_hash ~ '^[0-9a-f]{64}$'
   AND title='Inbound acquisition review' AND status IS NOT NULL AND status='acquisition_review_required'
   AND type IS NOT NULL AND type='acquisition_inbound_review' AND priority IS NULL AND description IS NULL
   AND due_date IS NULL AND completed_at IS NULL AND lead_id IS NULL AND deal_id IS NULL
   AND buyer_id IS NULL AND assigned_to IS NULL));
CREATE UNIQUE INDEX acquisition_task_request_identity ON public.tasks(acquisition_integration_id,acquisition_request_id) WHERE workspace_id IS NOT NULL;
CREATE UNIQUE INDEX acquisition_task_call_revision ON public.tasks(acquisition_integration_id,acquisition_call_id,acquisition_request_kind,acquisition_revision) WHERE workspace_id IS NOT NULL;
CREATE INDEX acquisition_task_scope ON public.tasks(workspace_id,acquisition_integration_id,acquisition_call_id,id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY acquisition_task_namespace ON public.tasks AS RESTRICTIVE FOR ALL TO authenticated,anon
 USING(workspace_id IS NULL) WITH CHECK(workspace_id IS NULL);
REVOKE TRUNCATE,TRIGGER ON public.tasks FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_acquisition_inbound_request(p_integration uuid,p_number text,p_agent text,p_agent_version integer,
 p_call text,p_request uuid,p_expected_revision integer,p_kind text,p_evidence jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; saved public.tasks%ROWTYPE;
 fingerprint text; revision integer; phone text; k text; max_length integer;
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND enabled AND provider='retell' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number OR route.agent_id IS DISTINCT FROM p_agent
  OR route.agent_version IS DISTINCT FROM p_agent_version THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_request IS NULL OR p_expected_revision IS NULL
  OR p_expected_revision NOT BETWEEN 0 AND 999999999 OR p_kind IS NULL OR p_kind NOT IN ('request_callback','request_human')
  OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'object' OR octet_length(p_evidence::text)>8192 THEN
  RAISE EXCEPTION 'Invalid inbound request' USING ERRCODE='22023'; END IF;
 IF p_kind='request_callback' THEN
  IF (SELECT count(*) FROM jsonb_object_keys(p_evidence))<>4 OR NOT p_evidence ?& ARRAY['phone','preferred_time','purpose','requested_by_caller']
   OR p_evidence->'requested_by_caller' IS DISTINCT FROM 'true'::jsonb THEN
   RAISE EXCEPTION 'Invalid callback evidence' USING ERRCODE='22023'; END IF;
  FOREACH k IN ARRAY ARRAY['phone','preferred_time','purpose'] LOOP
   max_length:=CASE WHEN k='phone' THEN 100 ELSE 500 END;
   IF jsonb_typeof(p_evidence->k) IS DISTINCT FROM 'string' OR length(trim(p_evidence->>k))<1 OR length(p_evidence->>k)>max_length THEN
    RAISE EXCEPTION 'Invalid callback text' USING ERRCODE='22023'; END IF;
  END LOOP;
  BEGIN phone:=private.normalize_acquisition_contact('phone',p_evidence->>'phone');
  EXCEPTION WHEN SQLSTATE '22023' THEN phone:=NULL; END;
 ELSE
  IF (SELECT count(*) FROM jsonb_object_keys(p_evidence))<>3 OR NOT p_evidence ?& ARRAY['reason','details','requested_by_caller']
   OR jsonb_typeof(p_evidence->'requested_by_caller') IS DISTINCT FROM 'boolean'
   OR jsonb_typeof(p_evidence->'reason') IS DISTINCT FROM 'string'
   OR p_evidence->>'reason' NOT IN ('caller_requested','unsupported_language','failed_transfer','sensitive_situation','unable_to_complete')
   OR (p_evidence->>'reason'='caller_requested' AND p_evidence->'requested_by_caller'<>'true'::jsonb)
   OR jsonb_typeof(p_evidence->'details') IS DISTINCT FROM 'string' OR length(trim(p_evidence->>'details'))<1 OR length(p_evidence->>'details')>1000 THEN
   RAISE EXCEPTION 'Invalid escalation evidence' USING ERRCODE='22023'; END IF;
 END IF;
 -- Database fingerprint is authoritative; client hashes never grant authority.
 fingerprint:=encode(sha256(convert_to(jsonb_build_object('version','acquisition-inbound-requests-v1',
  'workspace_id',route.workspace_id,'integration_id',p_integration,'agent_id',p_agent,'agent_version',p_agent_version,
  'call_id',p_call,'request_id',p_request,'expected_revision',p_expected_revision,'kind',p_kind,'evidence',p_evidence)::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound-request:'||p_integration::text||':'||p_request::text,0));
 -- Same lock used by lifecycle receipt, serializing new intents with terminal events.
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||p_call,0));
 SELECT * INTO saved FROM public.tasks WHERE acquisition_integration_id=p_integration AND acquisition_request_id=p_request;
 IF FOUND THEN
  IF saved.acquisition_request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Inbound request conflict' USING ERRCODE='23505'; END IF;
  -- Confirm an existing commit even if the call has since ended. No new work.
  RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'revision',saved.acquisition_revision,'duplicate',true,'execution_authorized',false);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
    AND acquisition_event_type='call_started' AND acquisition_projection->>'call_status'='ongoing')
  OR EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
    AND acquisition_event_type IN ('call_ended','call_analyzed')) THEN
  RAISE EXCEPTION 'Ongoing inbound ledger required' USING ERRCODE='55000'; END IF;
 SELECT coalesce(max(acquisition_revision),0) INTO revision FROM public.tasks WHERE acquisition_integration_id=p_integration
  AND acquisition_call_id=p_call AND acquisition_request_kind=p_kind;
 IF revision<>p_expected_revision THEN RAISE EXCEPTION 'Inbound request revision changed' USING ERRCODE='40001'; END IF;
 INSERT INTO public.tasks(title,priority,status,type,workspace_id,acquisition_integration_id,acquisition_call_id,
  acquisition_request_id,acquisition_revision,acquisition_request_kind,acquisition_evidence,acquisition_request_hash,acquisition_phone)
 VALUES('Inbound acquisition review',NULL,'acquisition_review_required','acquisition_inbound_review',route.workspace_id,p_integration,p_call,
  p_request,revision+1,p_kind,p_evidence,fingerprint,phone) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbound_request',saved.id::text,'recorded','inbound_tools',
  jsonb_build_object('integration_id',p_integration,'request_id',p_request,'revision',revision+1,'kind',p_kind,'request_hash',fingerprint,'execution_authorized',false),route.workspace_id);
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'revision',saved.acquisition_revision,'duplicate',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_inbound_request(uuid,text,text,integer,text,uuid,integer,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_inbound_request(uuid,text,text,integer,text,uuid,integer,text,jsonb) TO service_role;
CREATE FUNCTION public.record_acquisition_inbound_request(p_integration uuid,p_number text,p_agent text,p_agent_version integer,
 p_call text,p_request uuid,p_expected_revision integer,p_kind text,p_evidence jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_inbound_request(p_integration,p_number,p_agent,p_agent_version,p_call,p_request,p_expected_revision,p_kind,p_evidence) $$;
REVOKE ALL ON FUNCTION public.record_acquisition_inbound_request(uuid,text,text,integer,text,uuid,integer,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_acquisition_inbound_request(uuid,text,text,integer,text,uuid,integer,text,jsonb) TO service_role;

CREATE FUNCTION private.protect_acquisition_task() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF TG_OP='INSERT' AND NEW.workspace_id IS NOT NULL THEN
  IF current_user<>(SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='private.record_acquisition_inbound_request(uuid,text,text,integer,text,uuid,integer,text,jsonb)'::regprocedure) THEN
   RAISE EXCEPTION 'Use controlled inbound task receipt' USING ERRCODE='42501'; END IF;
 ELSIF TG_OP<>'INSERT' AND (OLD.workspace_id IS NOT NULL OR (TG_OP='UPDATE' AND NEW.workspace_id IS NOT NULL)) THEN
  RAISE EXCEPTION 'Inbound request evidence is immutable' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_task() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_task BEFORE INSERT OR UPDATE OR DELETE ON public.tasks FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_task();

CREATE FUNCTION private.acquisition_inbound_requests(p_workspace uuid,p_integration uuid,p_call text,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE rows jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Inbound request read denied' USING ERRCODE='42501'; END IF;
 IF p_integration IS NULL OR p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Invalid read bounds' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) INTO rows FROM (
  SELECT id,acquisition_revision,acquisition_request_kind,acquisition_evidence,acquisition_phone,acquisition_request_hash,created_at
  FROM public.tasks WHERE workspace_id=p_workspace AND acquisition_integration_id=p_integration AND acquisition_call_id=p_call
   AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit
 ) t;
 RETURN jsonb_build_object('workspace_id',p_workspace,'integration_id',p_integration,'call_id',p_call,'items',rows,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_requests(uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inbound_requests(uuid,uuid,text,uuid,integer) TO authenticated;
CREATE FUNCTION public.acquisition_inbound_requests(p_workspace uuid,p_integration uuid,p_call text,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_inbound_requests(p_workspace,p_integration,p_call,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION public.acquisition_inbound_requests(uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_inbound_requests(uuid,uuid,text,uuid,integer) TO authenticated;
COMMIT;
