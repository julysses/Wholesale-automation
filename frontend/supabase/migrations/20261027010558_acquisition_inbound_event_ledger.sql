-- Metadata-only inbound lifecycle ledger. No routing activation, raw content or sends.
BEGIN;
CREATE TABLE private.acquisition_inbound_routes (
 integration_id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 agent_id text NOT NULL CHECK(agent_id ~ '^[A-Za-z0-9_-]{1,200}$'),
 agent_version integer NOT NULL CHECK(agent_version>=0),
 acquisition_number text NOT NULL UNIQUE CHECK(acquisition_number ~ '^\+[1-9][0-9]{7,14}$'),
 enabled boolean NOT NULL DEFAULT false,
 privacy_approval_ref text,
 disclosure_approval_ref text,
 phase_one_acceptance_ref text,
 FOREIGN KEY(integration_id,workspace_id) REFERENCES private.acquisition_integrations(id,workspace_id),
 UNIQUE(integration_id,workspace_id),
 CHECK(NOT enabled OR (length(trim(privacy_approval_ref))>=10 AND privacy_approval_ref IS NOT NULL
  AND length(trim(disclosure_approval_ref))>=10 AND disclosure_approval_ref IS NOT NULL
  AND length(trim(phase_one_acceptance_ref))>=10 AND phase_one_acceptance_ref IS NOT NULL))
);
ALTER TABLE private.acquisition_inbound_routes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_inbound_routes FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.audit_acquisition_inbound_route() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Disable inbound routes instead of deleting them'; END IF;
 IF TG_OP='UPDATE' AND ROW(NEW.integration_id,NEW.workspace_id,NEW.agent_id,NEW.agent_version,NEW.acquisition_number)
  IS DISTINCT FROM ROW(OLD.integration_id,OLD.workspace_id,OLD.agent_id,OLD.agent_version,OLD.acquisition_number) THEN
  RAISE EXCEPTION 'Inbound routing identity is immutable'; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_integrations WHERE id=NEW.integration_id AND workspace_id=NEW.workspace_id AND provider='retell') THEN
  RAISE EXCEPTION 'Retell integration required'; END IF;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbound_route',NEW.integration_id::text,lower(TG_OP),session_user,
  jsonb_build_object('enabled',NEW.enabled,'agent_id',NEW.agent_id,'agent_version',NEW.agent_version,
  'privacy_approval_ref',NEW.privacy_approval_ref,'disclosure_approval_ref',NEW.disclosure_approval_ref,
  'phase_one_acceptance_ref',NEW.phase_one_acceptance_ref),NEW.workspace_id);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_acquisition_inbound_route() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_inbound_route_audit BEFORE INSERT OR UPDATE OR DELETE ON private.acquisition_inbound_routes
 FOR EACH ROW EXECUTE FUNCTION private.audit_acquisition_inbound_route();

ALTER TABLE public.call_events
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_integration_id uuid,
 ADD COLUMN acquisition_call_id text,
 ADD COLUMN acquisition_event_type text,
 ADD COLUMN acquisition_projection jsonb,
 ADD CONSTRAINT acquisition_call_integration_fk FOREIGN KEY(acquisition_integration_id,workspace_id)
 REFERENCES private.acquisition_inbound_routes(integration_id,workspace_id),
 ADD CONSTRAINT acquisition_call_event_shape CHECK (
 (workspace_id IS NULL AND acquisition_integration_id IS NULL AND acquisition_call_id IS NULL AND acquisition_event_type IS NULL AND acquisition_projection IS NULL)
 OR (workspace_id IS NOT NULL AND acquisition_integration_id IS NOT NULL AND acquisition_call_id IS NOT NULL
  AND acquisition_call_id ~ '^[A-Za-z0-9_-]{1,200}$' AND acquisition_event_type IS NOT NULL
  AND acquisition_event_type IN ('call_started','call_ended','call_analyzed') AND acquisition_projection IS NOT NULL
  AND jsonb_typeof(acquisition_projection)='object' AND dialer='acquisition_retell_inbound' AND disposition='provider_lifecycle'
  AND lead_id IS NULL AND agent_id IS NULL AND phone_number IS NULL AND duration_sec IS NULL
  AND recording_url IS NULL AND notes IS NULL AND raw_payload IS NOT NULL AND raw_payload='{}'::jsonb));
CREATE UNIQUE INDEX acquisition_call_event_identity ON public.call_events(acquisition_integration_id,acquisition_call_id,acquisition_event_type)
 WHERE workspace_id IS NOT NULL;
CREATE INDEX acquisition_call_event_scope ON public.call_events(workspace_id,acquisition_call_id,id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.call_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY acquisition_call_namespace ON public.call_events AS RESTRICTIVE FOR ALL TO authenticated,anon
 USING(workspace_id IS NULL) WITH CHECK(workspace_id IS NULL);
REVOKE TRUNCATE,TRIGGER ON public.call_events FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.accept_acquisition_inbound_event(p_integration uuid,p_number text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; saved public.call_events%ROWTYPE;
 fingerprint text; event_key text; k text; start_ms bigint; end_ms bigint;
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND provider='retell' AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_data IS NULL OR jsonb_typeof(p_data)<>'object' OR octet_length(p_data::text)>4096
  OR (SELECT count(*) FROM jsonb_object_keys(p_data))<>15
  OR NOT p_data ?& ARRAY['version','workspace_id','integration_id','call_id','event','agent_id','agent_version','direction','call_status','start_timestamp','end_timestamp','sensitive_content_present','execution_authorized','event_key','projection_hash'] THEN
  RAISE EXCEPTION 'Invalid inbound projection' USING ERRCODE='22023'; END IF;
 -- Exactly 15 fields: no transcript, recording, phone, metadata or free-text analysis.
 IF p_data->>'version' IS DISTINCT FROM 'acquisition-inbound-events-v1'
  OR p_data->>'workspace_id' IS DISTINCT FROM route.workspace_id::text OR p_data->>'integration_id' IS DISTINCT FROM p_integration::text
  OR p_data->>'agent_id' IS DISTINCT FROM route.agent_id OR p_data->'agent_version' IS DISTINCT FROM to_jsonb(route.agent_version)
  OR p_data->>'direction' IS DISTINCT FROM 'inbound' OR p_data->'execution_authorized' IS DISTINCT FROM 'false'::jsonb
  OR jsonb_typeof(p_data->'sensitive_content_present') IS DISTINCT FROM 'boolean'
  OR jsonb_typeof(p_data->'call_id') IS DISTINCT FROM 'string' OR p_data->>'call_id' !~ '^[A-Za-z0-9_-]{1,200}$'
  OR p_data->>'event' NOT IN ('call_started','call_ended','call_analyzed')
  OR p_data->>'call_status' NOT IN ('registered','ongoing','ended','error','not_connected') THEN
  RAISE EXCEPTION 'Inbound identity or lifecycle mismatch' USING ERRCODE='22023'; END IF;
 FOREACH k IN ARRAY ARRAY['version','workspace_id','integration_id','agent_id','direction','event','call_status','event_key','projection_hash'] LOOP
  IF jsonb_typeof(p_data->k) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'Invalid inbound scalar' USING ERRCODE='22023'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['start_timestamp','end_timestamp'] LOOP
  IF p_data->k IS DISTINCT FROM 'null'::jsonb AND (jsonb_typeof(p_data->k) IS DISTINCT FROM 'number'
   OR p_data->>k !~ '^[0-9]{1,15}$' OR (p_data->>k)::numeric>253402300799999) THEN
   RAISE EXCEPTION 'Invalid inbound timestamp' USING ERRCODE='22023'; END IF;
 END LOOP;
 start_ms:=(p_data->>'start_timestamp')::bigint; end_ms:=(p_data->>'end_timestamp')::bigint;
 IF end_ms<start_ms OR (p_data->>'event'='call_started' AND (end_ms IS NOT NULL OR p_data->>'call_status' NOT IN ('registered','ongoing')))
  OR (p_data->>'event'<>'call_started' AND p_data->>'call_status' NOT IN ('ended','error','not_connected')) THEN
  RAISE EXCEPTION 'Conflicting inbound lifecycle' USING ERRCODE='22023'; END IF;
 event_key:=encode(sha256(convert_to(replace(jsonb_build_array('acquisition-inbound-events-v1',route.workspace_id::text,p_integration::text,p_data->>'event',p_data->>'call_id')::text,', ',','),'UTF8')),'hex');
 SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex')
 INTO fingerprint FROM jsonb_each(p_data-'projection_hash');
 IF p_data->>'event_key' IS DISTINCT FROM event_key OR p_data->>'projection_hash' IS DISTINCT FROM fingerprint THEN
  RAISE EXCEPTION 'Inbound projection integrity mismatch' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||(p_data->>'call_id'),0));
 SELECT * INTO saved FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_data->>'call_id' AND acquisition_event_type=p_data->>'event';
 IF FOUND THEN
  IF saved.acquisition_projection IS DISTINCT FROM p_data THEN RAISE EXCEPTION 'Inbound event identity conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'duplicate',true,'execution_authorized',false);
 END IF;
 INSERT INTO public.call_events(dialer,disposition,raw_payload,workspace_id,acquisition_integration_id,acquisition_call_id,acquisition_event_type,acquisition_projection)
 VALUES('acquisition_retell_inbound','provider_lifecycle','{}',route.workspace_id,p_integration,p_data->>'call_id',p_data->>'event',p_data) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbound_event',saved.id::text,'received','inbound_ingestion',jsonb_build_object('integration_id',p_integration,'event_type',p_data->>'event','projection_hash',fingerprint),route.workspace_id);
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'duplicate',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.accept_acquisition_inbound_event(uuid,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.accept_acquisition_inbound_event(uuid,text,jsonb) TO service_role;
CREATE FUNCTION public.accept_acquisition_inbound_event(p_integration uuid,p_number text,p_data jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.accept_acquisition_inbound_event(p_integration,p_number,p_data) $$;
REVOKE ALL ON FUNCTION public.accept_acquisition_inbound_event(uuid,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.accept_acquisition_inbound_event(uuid,text,jsonb) TO service_role;

CREATE FUNCTION private.protect_acquisition_call_event() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF TG_OP='INSERT' AND NEW.workspace_id IS NOT NULL THEN
  IF current_user<>(SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='private.accept_acquisition_inbound_event(uuid,text,jsonb)'::regprocedure) THEN
   RAISE EXCEPTION 'Use controlled inbound receipt' USING ERRCODE='42501'; END IF;
 ELSIF TG_OP<>'INSERT' AND (OLD.workspace_id IS NOT NULL OR (TG_OP='UPDATE' AND NEW.workspace_id IS NOT NULL)) THEN
  RAISE EXCEPTION 'Inbound evidence is immutable' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_call_event() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_call_event BEFORE INSERT OR UPDATE OR DELETE ON public.call_events
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_call_event();

CREATE FUNCTION private.acquisition_inbound_events(p_workspace uuid,p_integration uuid,p_call text,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE rows jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Inbound read access denied' USING ERRCODE='42501'; END IF;
 IF p_integration IS NULL OR p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Invalid inbound read bounds' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) INTO rows FROM (
  SELECT id,acquisition_projection,created_at FROM public.call_events WHERE workspace_id=p_workspace AND acquisition_integration_id=p_integration AND acquisition_call_id=p_call
   AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit
 ) t;
 RETURN jsonb_build_object('workspace_id',p_workspace,'integration_id',p_integration,'call_id',p_call,'items',rows,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_events(uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inbound_events(uuid,uuid,text,uuid,integer) TO authenticated;
CREATE FUNCTION public.acquisition_inbound_events(p_workspace uuid,p_integration uuid,p_call text,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_inbound_events(p_workspace,p_integration,p_call,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION public.acquisition_inbound_events(uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_inbound_events(uuid,uuid,text,uuid,integer) TO authenticated;
COMMIT;
