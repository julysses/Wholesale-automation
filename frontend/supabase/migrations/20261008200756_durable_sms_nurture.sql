-- Service-only durable enrollment. One follow-up, no automatic retries.
CREATE TABLE public.sms_nurture_jobs (
  id uuid PRIMARY KEY,
  lead_id uuid NOT NULL REFERENCES public.leads(id),
  requested_by uuid NOT NULL REFERENCES public.profiles(id),
  phone_number text NOT NULL CHECK (phone_number ~ '^\+1[2-9][0-9]{9}$'),
  body text NOT NULL CHECK (length(body) BETWEEN 1 AND 1600),
  created_at timestamptz NOT NULL DEFAULT now(),
  due_at timestamptz NOT NULL,
  claimed_at timestamptz,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','processing','accepted','stopped','review','canceled')),
  reason text
);
CREATE UNIQUE INDEX sms_nurture_one_active_phone ON public.sms_nurture_jobs(phone_number)
  WHERE status IN ('scheduled','processing','review');
CREATE INDEX sms_nurture_due ON public.sms_nurture_jobs(due_at) WHERE status='scheduled';
ALTER TABLE public.sms_nurture_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sms_nurture_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.sms_nurture_jobs TO service_role;

-- All Twilio SMS entry points use this transaction. Advisory lock serializes
-- distinct references and duplicate leads sharing one canonical recipient.
CREATE FUNCTION public.claim_twilio_sms(p_id uuid,p_lead uuid,p_phone text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_id uuid; v_count int;
BEGIN
  IF coalesce(p_phone,'') !~ '^\+1[2-9][0-9]{9}$' OR length(coalesce(p_body,'')) NOT BETWEEN 1 AND 1600 THEN
    RAISE EXCEPTION 'Invalid SMS claim';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('twilio-sms:'||p_phone,0));
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE id=p_id) THEN
    RETURN jsonb_build_object('claimed',false,'reason','existing_reference');
  END IF;
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE provider='twilio' AND direction='outbound'
      AND phone_number=p_phone AND status IN ('submitting','unknown')) THEN
    RETURN jsonb_build_object('claimed',false,'reason','unresolved_attempt');
  END IF;
  IF coalesce((public.intake_phone_status(p_phone,p_lead,''))->>'suppressed','true') <> 'false' THEN
    RETURN jsonb_build_object('claimed',false,'reason','suppressed');
  END IF;
  -- Status callbacks are archives, not additional send attempts.
  SELECT count(*) INTO v_count FROM public.sms_events WHERE provider='twilio' AND direction='outbound'
    AND phone_number=p_phone AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
    AND created_at > now()-interval '30 days';
  IF v_count >= 2 THEN RETURN jsonb_build_object('claimed',false,'reason','attempt_limit'); END IF;
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE provider='twilio' AND direction='outbound'
    AND phone_number=p_phone AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
    AND created_at > now()-interval '24 hours') THEN
    RETURN jsonb_build_object('claimed',false,'reason','contact_cooldown');
  END IF;
  INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status)
    VALUES(p_id,p_lead,'twilio','outbound',p_phone,p_body,'submitting')
    ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
  RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'reason',CASE WHEN v_id IS NULL THEN 'existing_reference' ELSE 'claimed' END);
END; $$;
REVOKE ALL ON FUNCTION public.claim_twilio_sms(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_twilio_sms(uuid,uuid,text,text) TO service_role;

CREATE FUNCTION public.claim_sms_nurture(p_limit int DEFAULT 10)
RETURNS SETOF public.sms_nurture_jobs LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
  UPDATE public.sms_nurture_jobs SET status='processing',claimed_at=now()
  WHERE id IN (SELECT id FROM public.sms_nurture_jobs WHERE status='scheduled' AND due_at<=now()
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT least(greatest(p_limit,1),10))
  RETURNING *;
$$;
REVOKE ALL ON FUNCTION public.claim_sms_nurture(int) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_sms_nurture(int) TO service_role;
