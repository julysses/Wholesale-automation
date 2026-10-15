-- Cloud trigger only; both scheduler and application sending gates remain OFF.
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;
CREATE TABLE private.retell_sms_scheduler (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  enabled boolean NOT NULL DEFAULT false,
  endpoint text NOT NULL DEFAULT 'https://wholesale-automation-git-codex-dallas-de1768-julysses-projects.vercel.app/webhooks/_worker/retell-form-sms'
    CHECK(endpoint IN (
      'https://wholesale-automation-git-codex-dallas-de1768-julysses-projects.vercel.app/webhooks/_worker/retell-form-sms',
      'https://wholesale-automation.vercel.app/webhooks/_worker/retell-form-sms')),
  last_request_id bigint,
  last_requested_at timestamptz
);
ALTER TABLE private.retell_sms_scheduler ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_sms_scheduler FROM PUBLIC, anon, authenticated, service_role;
INSERT INTO private.retell_sms_scheduler(singleton) VALUES(true);

CREATE FUNCTION private.tick_retell_sms() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.retell_sms_scheduler; bearer text; bypass text; headers jsonb; rid bigint;
BEGIN
  SELECT * INTO c FROM private.retell_sms_scheduler WHERE singleton FOR UPDATE;
  IF NOT FOUND OR NOT c.enabled THEN
    RETURN jsonb_build_object('status','disabled','requested',false);
  END IF;
  SELECT decrypted_secret INTO bearer FROM vault.decrypted_secrets WHERE name='retell_sms_worker_bearer';
  IF coalesce(bearer,'')='' THEN
    RETURN jsonb_build_object('status','missing_worker_credential','requested',false);
  END IF;
  headers := jsonb_build_object('Authorization','Bearer '||bearer);
  IF c.endpoint LIKE 'https://wholesale-automation-git-%' THEN
    SELECT decrypted_secret INTO bypass FROM vault.decrypted_secrets WHERE name='retell_sms_preview_bypass';
    IF coalesce(bypass,'')='' THEN
      RETURN jsonb_build_object('status','missing_preview_access','requested',false);
    END IF;
    headers := headers || jsonb_build_object('x-vercel-protection-bypass',bypass);
  END IF;
  -- Avoid overlapping HTTP workers. A crash cannot make the same processing job
  -- eligible again; the application moves ambiguous attempts to review.
  IF c.last_request_id IS NOT NULL AND c.last_requested_at > now()-interval '90 seconds'
     AND NOT EXISTS (SELECT 1 FROM net._http_response WHERE id=c.last_request_id) THEN
    RETURN jsonb_build_object('status','in_flight','requested',false);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.retell_form_sms_jobs
                   WHERE status='scheduled' AND due_at<=now())
     AND NOT EXISTS (SELECT 1 FROM public.retell_form_sms_jobs
                   WHERE status='processing' AND claimed_at<now()-interval '5 minutes') THEN
    RETURN jsonb_build_object('status','idle','requested',false);
  END IF;
  SELECT net.http_get(url:=c.endpoint, headers:=headers, timeout_milliseconds:=60000) INTO rid;
  UPDATE private.retell_sms_scheduler SET last_request_id=rid,last_requested_at=now() WHERE singleton;
  RETURN jsonb_build_object('status','requested','requested',true,'request_id',rid);
END; $$;
REVOKE ALL ON FUNCTION private.tick_retell_sms() FROM PUBLIC,anon,authenticated,service_role;
-- Registered inactive in the same transaction: installation cannot send.
DO $$
DECLARE jid bigint;
BEGIN
  jid := cron.schedule('wholesaleos-retell-form-sms','10 seconds','SELECT private.tick_retell_sms()');
  PERFORM cron.alter_job(jid,active:=false);
END; $$;
