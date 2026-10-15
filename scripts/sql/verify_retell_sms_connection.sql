-- Rehearsal only; read-only Retell credential verification. All sending gates remain OFF.
-- Returns request IDs only. Never select or print the headers/secret values.
-- Read results from net._http_response using the returned IDs: wrong bearer must
-- return 401, valid bearer must return 200 with connected=true/dispatch_authorized=false.
DO $$ BEGIN
  IF (SELECT enabled FROM private.retell_sms_scheduler WHERE singleton) IS DISTINCT FROM false
     OR EXISTS (SELECT 1 FROM cron.job WHERE jobname='wholesaleos-retell-form-sms' AND active) THEN
    RAISE EXCEPTION 'Disable scheduler before isolated ingress acceptance';
  END IF;
END $$;
SELECT label, net.http_get(
  url:='https://wholesale-automation-git-codex-dallas-de1768-julysses-projects.vercel.app/webhooks/_worker/retell-form-sms?check_connection=true',
  headers:=jsonb_build_object(
    'Authorization', CASE WHEN label='invalid_bearer' THEN 'Bearer invalid-rehearsal-test'
      ELSE 'Bearer '||(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='retell_sms_worker_bearer') END,
    'x-vercel-protection-bypass',(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='retell_sms_preview_bypass')),
  timeout_milliseconds:=60000) AS request_id
FROM (VALUES ('invalid_bearer'),('valid_bearer')) AS checks(label);
