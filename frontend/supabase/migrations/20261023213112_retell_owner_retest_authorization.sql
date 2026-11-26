-- Operator-created, exact-inquiry, single-use test exception. No rows are
-- installed, no scheduler enabled, and no normal outreach limit is changed.
CREATE TABLE private.retell_owner_retest_authorizations (
 job_id uuid PRIMARY KEY REFERENCES public.retell_form_sms_jobs(id),
 lead_id uuid NOT NULL REFERENCES public.leads(id),
 phone_number text NOT NULL CHECK(phone_number ~ '^\+1[0-9]{10}$'),
 operator_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 10 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz,
 before_state jsonb NOT NULL CHECK(jsonb_typeof(before_state)='object'),
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '30 minutes')
);
ALTER TABLE private.retell_owner_retest_authorizations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_owner_retest_authorizations FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT,UPDATE(consumed_at) ON private.retell_owner_retest_authorizations TO service_role;

CREATE OR REPLACE FUNCTION public.claim_retell_form_sms_transport(p_limit integer, p_job uuid, p_transport text)
 RETURNS SETOF public.retell_form_sms_jobs
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE j public.retell_form_sms_jobs; test_override boolean; blocker text;
BEGIN
  IF p_transport IS NULL OR p_transport NOT IN ('retell_native','app_twilio') THEN RAISE EXCEPTION 'Invalid delivery transport'; END IF;
  FOR j IN SELECT * FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now() AND delivery_transport=p_transport
    AND (p_job IS NULL OR id=p_job)
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT CASE WHEN p_job IS NOT NULL THEN 1 ELSE least(greatest(p_limit,1),10) END
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||j.phone_number,0));
    blocker := public.outreach_recipient_limits(j.phone_number)->>'blocker';
    SELECT EXISTS(SELECT 1 FROM private.retell_owner_retest_authorizations a
      WHERE a.job_id=j.id AND a.phone_number=j.phone_number AND a.lead_id=j.lead_id
        AND a.created_at<=now() AND a.expires_at>now() AND a.consumed_at IS NULL
        AND p_job=j.id AND p_transport='app_twilio') INTO test_override;
    IF j.expires_at <= now() OR
       (blocker IS NOT NULL AND NOT (test_override AND blocker='attempt_limit')) OR
       coalesce((public.intake_phone_status(j.phone_number,j.lead_id,''))->>'suppressed','true') <> 'false' OR
       EXISTS (SELECT 1 FROM public.retell_form_sms_jobs r WHERE r.phone_number=j.phone_number
         AND r.id<>j.id AND r.status IN ('processing','accepted','review')) OR
       EXISTS (SELECT 1 FROM public.sms_events e WHERE e.phone_number=j.phone_number
         AND ((e.opt_out IS TRUE AND NOT public.sms_stop_has_reviewed_opt_in(e.id)) OR (e.direction='outbound' AND e.created_at>now()-interval '24 hours'))) THEN
      UPDATE public.retell_form_sms_jobs SET status='stopped',reason='Expired, suppressed, or previous recipient contact' WHERE id=j.id;
      CONTINUE;
    END IF;
    IF test_override THEN
      UPDATE private.retell_owner_retest_authorizations SET consumed_at=now() WHERE job_id=j.id AND consumed_at IS NULL;
    END IF;
    UPDATE public.retell_form_sms_jobs SET status='processing',claimed_at=now() WHERE id=j.id RETURNING * INTO j;
    -- Shared ledger blocks Twilio's claim function from sending alongside Retell.
    INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status,raw_payload)
      VALUES(j.id,j.lead_id,CASE WHEN p_transport='retell_native' THEN 'retell' ELSE 'twilio' END,
        'outbound',j.phone_number,coalesce(j.delivery_body,'Retell consented form response pending'),'submitting',
        CASE WHEN p_transport='app_twilio' THEN jsonb_build_object('transport',p_transport,'form_job_id',j.id,'sender_number',j.delivery_sender) ELSE '{}'::jsonb END);
    RETURN NEXT j;
  END LOOP;
END; $function$
;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms_transport(integer,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms_transport(integer,uuid,text) TO service_role;


