-- Additive, inert provider inbox. No subscriptions, processors, cron or sends.
BEGIN;
CREATE TABLE private.acquisition_integrations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 provider text NOT NULL CHECK(provider IN ('facebook','retell','twilio','mail')),
 account_id text NOT NULL CHECK(length(trim(account_id)) BETWEEN 1 AND 200),
 enabled boolean NOT NULL DEFAULT false,
 approval_ref text,
 retention_days integer NOT NULL DEFAULT 30 CHECK(retention_days BETWEEN 1 AND 90),
 UNIQUE(provider,account_id), UNIQUE(id,workspace_id),
 CHECK(NOT enabled OR (approval_ref IS NOT NULL AND length(trim(approval_ref))>0))
);
ALTER TABLE private.acquisition_integrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_integrations FROM PUBLIC,anon,authenticated,service_role;
-- Account routing is privileged configuration; no browser chooses a tenant.
CREATE FUNCTION private.audit_acquisition_integration() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Disable integrations instead of deleting them'; END IF;
 IF TG_OP='UPDATE' AND ROW(NEW.id,NEW.workspace_id,NEW.provider,NEW.account_id)
  IS DISTINCT FROM ROW(OLD.id,OLD.workspace_id,OLD.provider,OLD.account_id) THEN
  RAISE EXCEPTION 'Integration identity is immutable'; END IF;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_integration',NEW.id::text,lower(TG_OP),session_user,
  jsonb_build_object('enabled',NEW.enabled,'approval_ref',NEW.approval_ref,'retention_days',NEW.retention_days),NEW.workspace_id);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_acquisition_integration() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_integration_audit BEFORE INSERT OR UPDATE OR DELETE ON private.acquisition_integrations
 FOR EACH ROW EXECUTE FUNCTION private.audit_acquisition_integration();

ALTER TABLE public.webhook_jobs
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_integration_id uuid,
 ADD COLUMN external_event_id text,
 ADD COLUMN acquisition_event_type text,
 ADD COLUMN acquisition_payload_hash text,
 ADD COLUMN acquisition_raw_body bytea,
 ADD COLUMN acquisition_raw_hash text,
 ADD COLUMN acquisition_expires_at timestamptz,
 ADD COLUMN acquisition_purged_at timestamptz,
 ADD CONSTRAINT acquisition_inbox_integration_fk FOREIGN KEY(acquisition_integration_id,workspace_id)
  REFERENCES private.acquisition_integrations(id,workspace_id),
 ADD CONSTRAINT acquisition_inbox_shape CHECK (
  (workspace_id IS NULL AND acquisition_integration_id IS NULL AND external_event_id IS NULL
   AND acquisition_event_type IS NULL AND acquisition_payload_hash IS NULL AND acquisition_raw_body IS NULL
   AND acquisition_raw_hash IS NULL AND acquisition_expires_at IS NULL AND acquisition_purged_at IS NULL)
  OR (workspace_id IS NOT NULL AND acquisition_integration_id IS NOT NULL
   AND external_event_id IS NOT NULL AND length(trim(external_event_id)) BETWEEN 1 AND 200
   AND acquisition_event_type IS NOT NULL AND length(trim(acquisition_event_type)) BETWEEN 1 AND 100
   AND acquisition_payload_hash IS NOT NULL AND acquisition_raw_hash IS NOT NULL
   AND acquisition_expires_at IS NOT NULL AND source='acquisition_inbox'
   AND status IN ('acquisition_received','acquisition_expired')
   AND ((acquisition_purged_at IS NULL AND acquisition_raw_body IS NOT NULL AND status='acquisition_received')
    OR (acquisition_purged_at IS NOT NULL AND acquisition_raw_body IS NULL AND payload='{}'::jsonb AND status='acquisition_expired'))));
CREATE UNIQUE INDEX acquisition_inbox_event_identity ON public.webhook_jobs(acquisition_integration_id,acquisition_event_type,external_event_id)
 WHERE acquisition_integration_id IS NOT NULL;
CREATE INDEX acquisition_inbox_retention ON public.webhook_jobs(acquisition_expires_at,id)
 WHERE workspace_id IS NOT NULL AND acquisition_purged_at IS NULL;
ALTER TABLE public.webhook_jobs ENABLE ROW LEVEL SECURITY;
-- Restrictive even if a future legacy policy grants access; payloads are server-only.
CREATE POLICY acquisition_inbox_private ON public.webhook_jobs AS RESTRICTIVE TO authenticated,anon
 USING(workspace_id IS NULL) WITH CHECK(workspace_id IS NULL);
REVOKE TRUNCATE ON public.webhook_jobs FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.accept_acquisition_event(p_provider text,p_account text,p_external_event text,p_event_type text,p_payload jsonb,p_raw_body bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE integration private.acquisition_integrations%ROWTYPE; receipt public.webhook_jobs%ROWTYPE; active boolean; fingerprint text;
BEGIN
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 SELECT * INTO integration FROM private.acquisition_integrations WHERE provider=p_provider AND account_id=p_account FOR SHARE;
 IF NOT FOUND OR NOT integration.enabled THEN RAISE EXCEPTION 'Integration unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=integration.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_external_event IS NULL OR length(trim(p_external_event)) NOT BETWEEN 1 AND 200
  OR p_event_type IS NULL OR length(trim(p_event_type)) NOT BETWEEN 1 AND 100
  OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR octet_length(p_payload::text)>1048576
  OR p_raw_body IS NULL OR octet_length(p_raw_body) NOT BETWEEN 1 AND 1048576 THEN
  RAISE EXCEPTION 'Invalid provider receipt' USING ERRCODE='22023'; END IF;
 fingerprint:=encode(sha256(convert_to(p_payload::text,'UTF8')),'hex');
 -- Serialization avoids duplicate inserts and permits deterministic retry results.
 PERFORM pg_advisory_xact_lock(hashtextextended(integration.id::text||':'||p_event_type||':'||p_external_event,0));
 SELECT * INTO receipt FROM public.webhook_jobs WHERE acquisition_integration_id=integration.id
  AND acquisition_event_type=p_event_type AND external_event_id=p_external_event;
 IF FOUND THEN
  IF receipt.acquisition_payload_hash<>fingerprint THEN RAISE EXCEPTION 'Provider identity payload conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('receipt_id',receipt.id,'workspace_id',receipt.workspace_id,'duplicate',true,'status',receipt.status);
 END IF;
 INSERT INTO public.webhook_jobs(source,payload,status,workspace_id,acquisition_integration_id,external_event_id,
  acquisition_event_type,acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,acquisition_expires_at)
 VALUES('acquisition_inbox',p_payload,'acquisition_received',integration.workspace_id,integration.id,p_external_event,
  p_event_type,fingerprint,p_raw_body,encode(sha256(p_raw_body),'hex'),clock_timestamp()+make_interval(days=>integration.retention_days)) RETURNING * INTO receipt;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbox',receipt.id::text,'received','provider_ingestion',
  jsonb_build_object('integration_id',integration.id,'event_type',p_event_type,'payload_hash',fingerprint),integration.workspace_id);
 RETURN jsonb_build_object('receipt_id',receipt.id,'workspace_id',receipt.workspace_id,'duplicate',false,'status',receipt.status);
END $$;

CREATE FUNCTION private.purge_acquisition_payloads(p_limit integer DEFAULT 100)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE receipt public.webhook_jobs%ROWTYPE; total integer:=0;
BEGIN
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid purge batch size' USING ERRCODE='22023'; END IF;
 FOR receipt IN SELECT * FROM public.webhook_jobs WHERE workspace_id IS NOT NULL AND acquisition_purged_at IS NULL
  AND acquisition_expires_at<=clock_timestamp() ORDER BY acquisition_expires_at,id LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
  UPDATE public.webhook_jobs SET payload='{}',acquisition_raw_body=NULL,acquisition_purged_at=clock_timestamp(),status='acquisition_expired' WHERE id=receipt.id;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_inbox',receipt.id::text,'payload_purged','retention',jsonb_build_object('payload_hash',receipt.acquisition_payload_hash),receipt.workspace_id);
  total:=total+1;
 END LOOP;
 RETURN total;
END $$;
CREATE FUNCTION private.protect_acquisition_inbox() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE function_owner text;
BEGIN
 IF TG_OP='INSERT' AND NEW.workspace_id IS NULL THEN RETURN NEW; END IF;
 IF TG_OP='DELETE' AND OLD.workspace_id IS NULL THEN RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND OLD.workspace_id IS NULL AND NEW.workspace_id IS NULL THEN RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Acquisition receipts cannot be deleted' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.accept_acquisition_event(text,text,text,text,jsonb,bytea)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use acquisition inbox functions' USING ERRCODE='42501'; END IF;
 IF TG_OP='UPDATE' AND (OLD.workspace_id IS NULL OR OLD.acquisition_purged_at IS NOT NULL
  OR NEW.acquisition_purged_at IS NULL OR OLD.acquisition_expires_at>clock_timestamp()
  OR (to_jsonb(NEW)-ARRAY['payload','acquisition_raw_body','acquisition_purged_at','status']) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['payload','acquisition_raw_body','acquisition_purged_at','status'])) THEN
  RAISE EXCEPTION 'Acquisition receipt is immutable' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_inbox() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_inbox_protected BEFORE INSERT OR UPDATE OR DELETE ON public.webhook_jobs
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_inbox();
CREATE FUNCTION public.accept_acquisition_event(p_provider text,p_account text,p_external_event text,p_event_type text,p_payload jsonb,p_raw_body bytea)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.accept_acquisition_event(p_provider,p_account,p_external_event,p_event_type,p_payload,p_raw_body) $$;
CREATE FUNCTION public.purge_acquisition_payloads(p_limit integer DEFAULT 100)
RETURNS integer LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.purge_acquisition_payloads(p_limit) $$;
REVOKE ALL ON FUNCTION private.accept_acquisition_event(text,text,text,text,jsonb,bytea),public.accept_acquisition_event(text,text,text,text,jsonb,bytea),
 private.purge_acquisition_payloads(integer),public.purge_acquisition_payloads(integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.accept_acquisition_event(text,text,text,text,jsonb,bytea),public.accept_acquisition_event(text,text,text,text,jsonb,bytea),
 private.purge_acquisition_payloads(integer),public.purge_acquisition_payloads(integer) TO service_role;
COMMIT;
