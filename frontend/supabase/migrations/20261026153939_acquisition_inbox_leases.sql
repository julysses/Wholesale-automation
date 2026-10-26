-- Recovery state is private; immutable receipt content and legacy queue stay untouched.
BEGIN;
CREATE TABLE private.acquisition_inbox_processing (
 receipt_id uuid PRIMARY KEY REFERENCES public.webhook_jobs(id),
 state text NOT NULL DEFAULT 'ready' CHECK(state IN ('ready','leased','retry','review')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 lease_token uuid,
 lease_expires_at timestamptz,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 reason_code text,
 requested_reason text,
 settled_outcome text CHECK(settled_outcome IN ('retry','review')),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(state<>'leased' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND attempts>0))
);
ALTER TABLE private.acquisition_inbox_processing ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_inbox_processing FROM PUBLIC,anon,authenticated,service_role;
CREATE INDEX acquisition_processing_ready ON private.acquisition_inbox_processing(next_attempt_at,receipt_id) WHERE state IN ('ready','retry','leased');
CREATE FUNCTION private.initialize_acquisition_processing() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.workspace_id IS NOT NULL THEN INSERT INTO private.acquisition_inbox_processing(receipt_id) VALUES(NEW.id); END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.initialize_acquisition_processing() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_processing_initialize AFTER INSERT ON public.webhook_jobs
 FOR EACH ROW EXECUTE FUNCTION private.initialize_acquisition_processing();
INSERT INTO private.acquisition_inbox_processing(receipt_id)
 SELECT id FROM public.webhook_jobs WHERE workspace_id IS NOT NULL;

CREATE FUNCTION private.claim_acquisition_events(p_integration uuid,p_limit integer DEFAULT 1,p_lease_seconds integer DEFAULT 120)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE integration private.acquisition_integrations%ROWTYPE; active boolean; item record; token uuid; deadline timestamptz;
 result jsonb:='[]'::jsonb;
BEGIN
 IF p_integration IS NULL OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 20
  OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 30 AND 300 THEN
  RAISE EXCEPTION 'Invalid claim parameters' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 SELECT * INTO integration FROM private.acquisition_integrations WHERE id=p_integration FOR SHARE;
 IF NOT FOUND OR NOT integration.enabled THEN RAISE EXCEPTION 'Integration unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=integration.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 FOR item IN SELECT j.*,w.payload,w.acquisition_event_type,w.external_event_id,w.acquisition_payload_hash,
   w.acquisition_expires_at,w.acquisition_purged_at
  FROM private.acquisition_inbox_processing j JOIN public.webhook_jobs w ON w.id=j.receipt_id
  WHERE w.acquisition_integration_id=p_integration AND j.state IN ('ready','retry','leased')
   AND ((j.state IN ('ready','retry') AND j.next_attempt_at<=clock_timestamp())
        OR (j.state='leased' AND j.lease_expires_at<=clock_timestamp()))
  ORDER BY j.next_attempt_at,j.receipt_id LIMIT p_limit FOR UPDATE OF w,j SKIP LOCKED LOOP
  IF item.acquisition_purged_at IS NOT NULL OR item.acquisition_expires_at<=clock_timestamp() OR item.attempts>=5 THEN
   UPDATE private.acquisition_inbox_processing SET state='review',lease_expires_at=NULL,settled_outcome='review',
    reason_code=CASE WHEN item.acquisition_purged_at IS NOT NULL OR item.acquisition_expires_at<=clock_timestamp() THEN 'PAYLOAD_EXPIRED' ELSE 'RETRY_EXHAUSTED' END,
    updated_at=clock_timestamp() WHERE receipt_id=item.receipt_id;
   INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
    VALUES('acquisition_inbox',item.receipt_id::text,'processing_held','inbox_worker',
     jsonb_build_object('attempt',item.attempts,'reason',CASE WHEN item.acquisition_purged_at IS NOT NULL OR item.acquisition_expires_at<=clock_timestamp() THEN 'PAYLOAD_EXPIRED' ELSE 'RETRY_EXHAUSTED' END),integration.workspace_id);
   CONTINUE;
  END IF;
  token:=gen_random_uuid(); deadline:=clock_timestamp()+make_interval(secs=>p_lease_seconds);
  UPDATE private.acquisition_inbox_processing SET state='leased',attempts=attempts+1,lease_token=token,
   lease_expires_at=deadline,settled_outcome=NULL,reason_code=NULL,requested_reason=NULL,updated_at=clock_timestamp() WHERE receipt_id=item.receipt_id;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
   VALUES('acquisition_inbox',item.receipt_id::text,'processing_claimed','inbox_worker',
    jsonb_build_object('attempt',item.attempts+1,'recovered_expired_lease',item.state='leased','expires_at',deadline),integration.workspace_id);
  result:=result||jsonb_build_array(jsonb_build_object('receipt_id',item.receipt_id,'workspace_id',integration.workspace_id,
   'integration_id',integration.id,'provider',integration.provider,'account_id',integration.account_id,
   'event_type',item.acquisition_event_type,'external_event_id',item.external_event_id,'payload',item.payload,
   'payload_hash',item.acquisition_payload_hash,'attempt',item.attempts+1,'lease_token',token,'lease_expires_at',deadline));
 END LOOP;
 RETURN result;
END $$;

-- Retry/hold only. Successful CRM completion must be atomic with a later
-- provider-specific writer; workers cannot assert generic "done" here.
CREATE FUNCTION private.defer_acquisition_event(p_receipt uuid,p_lease uuid,p_outcome text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE receipt public.webhook_jobs%ROWTYPE; job private.acquisition_inbox_processing%ROWTYPE; next_state text; code text;
BEGIN
 IF p_outcome IS NULL OR p_outcome NOT IN ('retry','review') OR p_reason IS NULL
  OR (p_outcome='retry' AND p_reason NOT IN ('PROVIDER_TIMEOUT','PROVIDER_RATE_LIMIT','PROVIDER_UNAVAILABLE','PERSISTENCE_UNAVAILABLE'))
  OR (p_outcome='review' AND p_reason NOT IN ('CREDENTIALS_INVALID','PERMISSION_DENIED','INVALID_PROVIDER_DATA','IDENTITY_CONFLICT','UNSUPPORTED_EVENT')) THEN
  RAISE EXCEPTION 'Invalid processing outcome' USING ERRCODE='22023'; END IF;
 -- Match claim/purge lock order. Deferral remains possible after a kill switch.
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=p_receipt AND workspace_id IS NOT NULL FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Receipt unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO job FROM private.acquisition_inbox_processing WHERE receipt_id=p_receipt FOR UPDATE;
 IF NOT FOUND OR p_lease IS NULL OR job.lease_token IS DISTINCT FROM p_lease THEN
  RAISE EXCEPTION 'Processing lease superseded' USING ERRCODE='40001'; END IF;
 next_state:=CASE WHEN p_outcome='retry' AND job.attempts>=5 THEN 'review' ELSE p_outcome END;
 code:=CASE WHEN p_outcome='retry' AND job.attempts>=5 THEN 'RETRY_EXHAUSTED' ELSE p_reason END;
 IF job.state<>'leased' THEN
  IF job.settled_outcome=p_outcome AND job.requested_reason=p_reason THEN
   RETURN jsonb_build_object('receipt_id',p_receipt,'state',job.state,'reason_code',job.reason_code,'duplicate',true);
  END IF;
  RAISE EXCEPTION 'Processing outcome conflict' USING ERRCODE='40001';
 END IF;
 IF job.lease_expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'Processing lease expired' USING ERRCODE='40001'; END IF;
 IF receipt.acquisition_purged_at IS NOT NULL OR receipt.acquisition_expires_at<=clock_timestamp() THEN
  next_state:='review'; code:='PAYLOAD_EXPIRED';
 END IF;
 UPDATE private.acquisition_inbox_processing SET state=next_state,reason_code=code,settled_outcome=p_outcome,requested_reason=p_reason,
  lease_expires_at=NULL,next_attempt_at=clock_timestamp()+make_interval(secs=>least(3600,30*(2^job.attempts)::integer)),
  updated_at=clock_timestamp() WHERE receipt_id=p_receipt;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_inbox',p_receipt::text,'processing_deferred','inbox_worker',
   jsonb_build_object('attempt',job.attempts,'state',next_state,'reason_code',code),receipt.workspace_id);
 RETURN jsonb_build_object('receipt_id',p_receipt,'state',next_state,'reason_code',code,'duplicate',false);
END $$;
CREATE FUNCTION public.claim_acquisition_events(p_integration uuid,p_limit integer DEFAULT 1,p_lease_seconds integer DEFAULT 120)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.claim_acquisition_events(p_integration,p_limit,p_lease_seconds) $$;
CREATE FUNCTION public.defer_acquisition_event(p_receipt uuid,p_lease uuid,p_outcome text,p_reason text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.defer_acquisition_event(p_receipt,p_lease,p_outcome,p_reason) $$;
REVOKE ALL ON FUNCTION private.claim_acquisition_events(uuid,integer,integer),public.claim_acquisition_events(uuid,integer,integer),
 private.defer_acquisition_event(uuid,uuid,text,text),public.defer_acquisition_event(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.claim_acquisition_events(uuid,integer,integer),public.claim_acquisition_events(uuid,integer,integer),
 private.defer_acquisition_event(uuid,uuid,text,text),public.defer_acquisition_event(uuid,uuid,text,text) TO service_role;
COMMIT;
