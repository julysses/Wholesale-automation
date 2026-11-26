-- Selection leases are not provider claims. An interrupted selection may be
-- reconsidered; processing/generating/submitting operations are never replayed.
ALTER TABLE public.retell_form_sms_jobs ADD COLUMN auto_selected_at timestamptz;
ALTER TABLE public.retell_api_turns ADD COLUMN auto_selected_at timestamptz;
CREATE FUNCTION public.clear_retell_app_turn_selection() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF NEW.status<>OLD.status THEN NEW.auto_selected_at:=NULL; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.clear_retell_app_turn_selection() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER clear_retell_app_turn_selection BEFORE UPDATE ON public.retell_api_turns
 FOR EACH ROW EXECUTE FUNCTION public.clear_retell_app_turn_selection();
CREATE FUNCTION public.pick_retell_app_work(p_job uuid DEFAULT NULL,p_first_turn_only boolean DEFAULT false,p_phones text[] DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE chosen record; updated uuid;
BEGIN
 IF p_first_turn_only IS NULL OR (p_first_turn_only AND p_job IS NULL) THEN RAISE EXCEPTION 'Finite test scope required'; END IF;
 IF p_phones IS NOT NULL AND EXISTS(SELECT 1 FROM unnest(p_phones) p WHERE p IS NULL OR p !~ '^\+1[0-9]{10}$') THEN RAISE EXCEPTION 'Invalid recipient scope'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:retell-app-select',0)) THEN
  RETURN jsonb_build_object('selected',false,'reason','selection_busy'); END IF;
 SELECT * INTO chosen FROM (
  SELECT 'ack'::text action,j.id reference,j.id job_id,2 priority,j.due_at due_at
  FROM public.retell_form_sms_jobs j
  WHERE j.delivery_transport='app_twilio' AND j.status='scheduled' AND j.due_at<=now() AND j.expires_at>now()
   AND (p_job IS NULL OR j.id=p_job) AND (p_phones IS NULL OR j.phone_number=ANY(p_phones))
   AND (j.auto_selected_at IS NULL OR j.auto_selected_at<=now()-interval '90 seconds')
  UNION ALL
  SELECT CASE WHEN t.status='generated' THEN 'reply' ELSE 'generate' END,t.id,s.id,
   CASE WHEN t.status='generated' THEN 0 ELSE 1 END,t.created_at
  FROM public.retell_api_turns t JOIN public.retell_api_sessions s ON s.id=t.session_id
  JOIN public.retell_form_sms_jobs j ON j.id=s.id
  WHERE j.delivery_transport='app_twilio' AND j.status='accepted' AND t.expires_at>now()
   AND ((t.status='queued' AND s.status IN ('pending','ready')) OR (t.status='generated' AND s.status='ready'))
   AND (p_job IS NULL OR s.id=p_job) AND (p_phones IS NULL OR s.phone_number=ANY(p_phones))
   AND (t.auto_selected_at IS NULL OR t.auto_selected_at<=now()-interval '90 seconds')
   AND t.id=(SELECT x.id FROM public.retell_api_turns x WHERE x.session_id=s.id AND x.status NOT IN ('accepted','stopped') ORDER BY x.created_at,x.id LIMIT 1)
   AND (NOT p_first_turn_only OR t.id=(SELECT x.id FROM public.retell_api_turns x WHERE x.session_id=s.id ORDER BY x.created_at,x.id LIMIT 1))
 ) candidates ORDER BY priority,due_at,reference LIMIT 1;
 IF NOT FOUND THEN RETURN jsonb_build_object('selected',false,'reason','no_due_work'); END IF;
 IF chosen.action='ack' THEN
  UPDATE public.retell_form_sms_jobs SET auto_selected_at=now()
   WHERE id=chosen.reference AND status='scheduled' RETURNING id INTO updated;
 ELSE
  UPDATE public.retell_api_turns SET auto_selected_at=now()
   WHERE id=chosen.reference AND status=CASE WHEN chosen.action='reply' THEN 'generated' ELSE 'queued' END RETURNING id INTO updated;
 END IF;
 IF updated IS NULL THEN RETURN jsonb_build_object('selected',false,'reason','state_changed'); END IF;
 RETURN jsonb_build_object('selected',true,'action',chosen.action,'reference',chosen.reference,'job_id',chosen.job_id,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.pick_retell_app_work(uuid,boolean,text[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.pick_retell_app_work(uuid,boolean,text[]) TO service_role;

-- Separate from the native scheduler: installation cannot activate either.
CREATE TABLE private.retell_app_scheduler(
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
 enabled boolean NOT NULL DEFAULT false,
 start_hour smallint NOT NULL DEFAULT 9,end_hour smallint NOT NULL DEFAULT 19,
 CHECK(start_hour>=0 AND start_hour<end_hour AND end_hour<=24),
 last_request_id bigint,last_requested_at timestamptz,
 last_state text NOT NULL DEFAULT 'disabled',last_http_status integer
);
ALTER TABLE private.retell_app_scheduler ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_app_scheduler FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT ON private.retell_app_scheduler TO service_role;
INSERT INTO private.retell_app_scheduler(singleton) VALUES(true);
CREATE FUNCTION private.tick_retell_app_sms() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.retell_app_scheduler; bearer text; rid bigint; response record; response_body jsonb;
BEGIN
 SELECT * INTO c FROM private.retell_app_scheduler WHERE singleton FOR UPDATE;
 IF NOT FOUND OR NOT c.enabled THEN RETURN jsonb_build_object('status','disabled','requested',false); END IF;
 IF EXISTS(SELECT 1 FROM private.retell_sms_scheduler WHERE enabled) THEN
  UPDATE private.retell_app_scheduler SET last_state='native_scheduler_enabled' WHERE singleton;
  RETURN jsonb_build_object('status','native_scheduler_enabled','requested',false); END IF;
 IF c.last_request_id IS NOT NULL THEN
  SELECT * INTO response FROM net._http_response WHERE id=c.last_request_id;
  IF NOT FOUND THEN
   IF c.last_requested_at>now()-interval '90 seconds' THEN RETURN jsonb_build_object('status','in_flight','requested',false); END IF;
   UPDATE private.retell_app_scheduler SET enabled=false,last_state='worker_http_unconfirmed' WHERE singleton;
   RETURN jsonb_build_object('status','worker_http_unconfirmed','requested',false); END IF;
  IF response.status_code IS DISTINCT FROM 200 OR response.timed_out IS DISTINCT FROM false THEN
   UPDATE private.retell_app_scheduler SET enabled=false,last_state='worker_http_failed',last_http_status=response.status_code WHERE singleton;
   RETURN jsonb_build_object('status','worker_http_failed','requested',false); END IF;
  BEGIN response_body:=response.content::jsonb;
  EXCEPTION WHEN invalid_text_representation THEN response_body:=NULL; END;
  IF coalesce(response_body->>'status','') NOT IN ('processed','idle','deferred') THEN
   UPDATE private.retell_app_scheduler SET enabled=false,last_state='worker_disabled_or_invalid',last_http_status=200 WHERE singleton;
   RETURN jsonb_build_object('status','worker_disabled_or_invalid','requested',false); END IF;
  -- A completed HTTP receipt no longer needs to remain in pg_net's short-lived
  -- response store. Retain it in our diagnostic columns, not as an in-flight lock.
  UPDATE private.retell_app_scheduler SET last_request_id=NULL,last_state='idle',last_http_status=200 WHERE singleton;
 END IF;
 -- Contact hours are rechecked by the application immediately before providers.
 -- This guard avoids background HTTP traffic outside the configured launch window.
 IF extract(hour FROM now() AT TIME ZONE 'America/Chicago')<c.start_hour
  OR extract(hour FROM now() AT TIME ZONE 'America/Chicago')>=c.end_hour THEN
  RETURN jsonb_build_object('status','outside_contact_hours','requested',false); END IF;
 IF NOT EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE delivery_transport='app_twilio'
    AND status='scheduled' AND due_at<=now() AND expires_at>now()
    AND (auto_selected_at IS NULL OR auto_selected_at<=now()-interval '90 seconds'))
  AND NOT EXISTS(SELECT 1 FROM public.retell_api_turns t JOIN public.retell_api_sessions s ON s.id=t.session_id
    WHERE t.status IN ('queued','generated') AND s.status IN ('pending','ready') AND t.expires_at>now()
    AND (t.auto_selected_at IS NULL OR t.auto_selected_at<=now()-interval '90 seconds')) THEN
  RETURN jsonb_build_object('status','idle','requested',false); END IF;
 SELECT decrypted_secret INTO bearer FROM vault.decrypted_secrets WHERE name='retell_sms_worker_bearer';
 IF coalesce(bearer,'')='' THEN
  UPDATE private.retell_app_scheduler SET last_state='missing_worker_credential' WHERE singleton;
  RETURN jsonb_build_object('status','missing_worker_credential','requested',false); END IF;
 SELECT net.http_post(url:='https://wholesale-automation.vercel.app/webhooks/_worker/retell-app/automatic',
  body:='{}'::jsonb,headers:=jsonb_build_object('Authorization','Bearer '||bearer,'Content-Type','application/json'),
  timeout_milliseconds:=60000) INTO rid;
 UPDATE private.retell_app_scheduler SET last_request_id=rid,last_requested_at=now(),last_state='requested',last_http_status=NULL WHERE singleton;
 RETURN jsonb_build_object('status','requested','requested',true,'request_id',rid);
END $$;
REVOKE ALL ON FUNCTION private.tick_retell_app_sms() FROM PUBLIC,anon,authenticated,service_role;
DO $$ DECLARE jid bigint;
BEGIN
 jid:=cron.schedule('wholesaleos-retell-app-sms','10 seconds','SELECT private.tick_retell_app_sms()');
 PERFORM cron.alter_job(jid,active:=false);
END $$;

CREATE OR REPLACE FUNCTION public.retell_app_monitor_findings()
RETURNS TABLE(category text,reference uuid,lead_id uuid,created_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT 'retell_api_turn',t.id,s.lead_id,t.created_at
 FROM public.retell_api_turns t JOIN public.retell_api_sessions s ON s.id=t.session_id
 LEFT JOIN public.sms_events e ON e.id=t.outbound_id
 WHERE t.status='review'
 OR (t.status IN ('queued','generated') AND t.expires_at<=now())
 OR (t.status IN ('creating_session','generating') AND coalesce(t.claimed_at,t.created_at)<=now()-interval '5 minutes')
 OR (t.status='submitting' AND coalesce(e.created_at,t.claimed_at,t.created_at)<=now()-interval '5 minutes')
 UNION ALL SELECT 'retell_api_session',s.id,s.lead_id,s.created_at FROM public.retell_api_sessions s
 WHERE s.status='review' OR (s.status='creating' AND coalesce(s.claimed_at,s.created_at)<=now()-interval '5 minutes')
 UNION ALL SELECT 'retell_app_scheduler',c.id,NULL::uuid,coalesce(c.last_requested_at,now())
 FROM private.retell_app_scheduler c WHERE c.last_state IN
 ('native_scheduler_enabled','worker_http_unconfirmed','worker_http_failed','worker_disabled_or_invalid','missing_worker_credential');
$$;
REVOKE ALL ON FUNCTION public.retell_app_monitor_findings() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.retell_app_monitor_findings() TO service_role;

