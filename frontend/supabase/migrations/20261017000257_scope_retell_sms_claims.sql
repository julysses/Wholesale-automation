-- Scope an operator-approved run to one fresh job. No sending or activation here.
-- Share all prior suppression, contact-limit, expiry and no-replay checks.
CREATE OR REPLACE FUNCTION public.claim_retell_form_sms_matching(p_limit integer, p_job uuid)
 RETURNS SETOF retell_form_sms_jobs
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE j public.retell_form_sms_jobs;
BEGIN
  FOR j IN SELECT * FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now()
    AND (p_job IS NULL OR id=p_job)
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT CASE WHEN p_job IS NOT NULL THEN 1 ELSE least(greatest(p_limit,1),10) END
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||j.phone_number,0));
    IF j.expires_at <= now() OR
       public.outreach_recipient_limits(j.phone_number)->>'blocker' IS NOT NULL OR
       coalesce((public.intake_phone_status(j.phone_number,j.lead_id,''))->>'suppressed','true') <> 'false' OR
       EXISTS (SELECT 1 FROM public.retell_form_sms_jobs r WHERE r.phone_number=j.phone_number
         AND r.id<>j.id AND r.status IN ('processing','accepted','review')) OR
       EXISTS (SELECT 1 FROM public.sms_events e WHERE e.phone_number=j.phone_number
         AND ((e.opt_out IS TRUE AND NOT public.sms_stop_has_reviewed_opt_in(e.id)) OR (e.direction='outbound' AND e.created_at>now()-interval '24 hours'))) THEN
      UPDATE public.retell_form_sms_jobs SET status='stopped',reason='Expired, suppressed, or previous recipient contact' WHERE id=j.id;
      CONTINUE;
    END IF;
    UPDATE public.retell_form_sms_jobs SET status='processing',claimed_at=now() WHERE id=j.id RETURNING * INTO j;
    -- Shared ledger blocks Twilio's claim function from sending alongside Retell.
    INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status)
      VALUES(j.id,j.lead_id,'retell','outbound',j.phone_number,'Retell consented form response pending','submitting');
    RETURN NEXT j;
  END LOOP;
END; $function$
;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms_matching(integer,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms_matching(integer,uuid) TO service_role;

-- Preserve the existing scheduled worker interface and behavior.
CREATE OR REPLACE FUNCTION public.claim_retell_form_sms(p_limit integer DEFAULT 3)
RETURNS SETOF public.retell_form_sms_jobs LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
  SELECT * FROM public.claim_retell_form_sms_matching(p_limit,NULL);
$$;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms(integer) TO service_role;
