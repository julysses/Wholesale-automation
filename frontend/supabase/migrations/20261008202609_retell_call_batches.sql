-- Common phone-level limits for selected seller automation channels.
CREATE FUNCTION public.outreach_recipient_limits(p_phone text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
WITH attempts AS (
  SELECT created_at,status IN ('submitting','unknown') AS unresolved FROM public.sms_events
    WHERE provider='twilio' AND direction='outbound' AND phone_number=p_phone
      AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
  UNION ALL
  SELECT created_at,status<>'completed' FROM public.retell_call_requests WHERE phone_number=p_phone
)
SELECT jsonb_build_object('blocker', CASE
  WHEN EXISTS (SELECT 1 FROM attempts WHERE unresolved) THEN 'unresolved_attempt'
  WHEN (SELECT count(*) FROM attempts WHERE created_at>now()-interval '30 days')>=2 THEN 'attempt_limit'
  WHEN EXISTS (SELECT 1 FROM attempts WHERE created_at>now()-interval '24 hours') THEN 'contact_cooldown'
  ELSE NULL END);
$$;
REVOKE ALL ON FUNCTION public.outreach_recipient_limits(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.outreach_recipient_limits(text) TO service_role;

CREATE FUNCTION public.claim_retell_call(p_id uuid,p_lead uuid,p_phone text,p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_id uuid; v_reason text;
BEGIN
  IF coalesce(p_phone,'') !~ '^\+1[2-9][0-9]{9}$' THEN RAISE EXCEPTION 'Invalid call phone'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||p_phone,0));
  IF EXISTS(SELECT 1 FROM public.retell_call_requests WHERE id=p_id) THEN
    RETURN jsonb_build_object('claimed',false,'reason','existing_reference');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.leads WHERE id=p_lead AND dnc IS FALSE AND ai_calling_paused IS FALSE)
    OR coalesce((public.intake_phone_status(p_phone,p_lead,''))->>'suppressed','true')<>'false' THEN
    RETURN jsonb_build_object('claimed',false,'reason','suppressed_or_paused');
  END IF;
  v_reason:=public.outreach_recipient_limits(p_phone)->>'blocker';
  IF v_reason IS NOT NULL THEN RETURN jsonb_build_object('claimed',false,'reason',v_reason); END IF;
  INSERT INTO public.retell_call_requests(id,lead_id,phone_number,requested_by,status)
    VALUES(p_id,p_lead,p_phone,p_operator,'submitting') ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
  RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'reason',CASE WHEN v_id IS NULL THEN 'existing_reference' ELSE 'claimed' END);
END; $$;
REVOKE ALL ON FUNCTION public.claim_retell_call(uuid,uuid,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_call(uuid,uuid,text,uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.claim_twilio_sms(p_id uuid,p_lead uuid,p_phone text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_id uuid; v_reason text;
BEGIN
  IF coalesce(p_phone,'') !~ '^\+1[2-9][0-9]{9}$' OR length(coalesce(p_body,'')) NOT BETWEEN 1 AND 1600 THEN
    RAISE EXCEPTION 'Invalid SMS claim';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||p_phone,0));
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE id=p_id) THEN
    RETURN jsonb_build_object('claimed',false,'reason','existing_reference');
  END IF;
  IF coalesce((public.intake_phone_status(p_phone,p_lead,''))->>'suppressed','true') <> 'false' THEN
    RETURN jsonb_build_object('claimed',false,'reason','suppressed');
  END IF;
  v_reason:=public.outreach_recipient_limits(p_phone)->>'blocker';
  IF v_reason IS NOT NULL THEN RETURN jsonb_build_object('claimed',false,'reason',v_reason); END IF;
  INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status)
    VALUES(p_id,p_lead,'twilio','outbound',p_phone,p_body,'submitting') ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
  RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'reason',CASE WHEN v_id IS NULL THEN 'existing_reference' ELSE 'claimed' END);
END; $$;
-- Existing function grants stay service-only.

CREATE TABLE public.retell_call_batches (
  id uuid PRIMARY KEY,
  requested_by uuid NOT NULL REFERENCES public.profiles(id),
  lead_ids uuid[] NOT NULL CHECK (cardinality(lead_ids) BETWEEN 1 AND 5),
  outcomes jsonb NOT NULL CHECK (jsonb_typeof(outcomes)='array' AND jsonb_array_length(outcomes) BETWEEN 1 AND 5),
  status text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','processing','review','completed','canceled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  claimed_at timestamptz
);
ALTER TABLE public.retell_call_batches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.retell_call_batches FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.retell_call_batches TO service_role;
CREATE INDEX retell_call_batches_operator ON public.retell_call_batches(requested_by);

CREATE FUNCTION public.claim_retell_batch_next(p_batch uuid,p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.retell_call_batches%ROWTYPE; item jsonb; idx int;
BEGIN
  SELECT * INTO b FROM public.retell_call_batches WHERE id=p_batch AND requested_by=p_operator FOR UPDATE;
  IF NOT FOUND OR b.status<>'ready' THEN RETURN jsonb_build_object('claimed',false); END IF;
  SELECT e.value,e.ordinality-1 INTO item,idx FROM jsonb_array_elements(b.outcomes) WITH ORDINALITY e
    WHERE e.value->>'status'='pending' ORDER BY e.ordinality LIMIT 1;
  IF item IS NULL THEN
    UPDATE public.retell_call_batches SET status='completed' WHERE id=p_batch;
    RETURN jsonb_build_object('claimed',false);
  END IF;
  UPDATE public.retell_call_batches SET status='processing',claimed_at=now(),
    outcomes=jsonb_set(outcomes,ARRAY[idx::text,'status'],'"submitting"'::jsonb) WHERE id=p_batch;
  RETURN jsonb_build_object('claimed',true,'item',item);
END; $$;
REVOKE ALL ON FUNCTION public.claim_retell_batch_next(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_batch_next(uuid,uuid) TO service_role;

CREATE FUNCTION public.finish_retell_batch_item(p_batch uuid,p_reference uuid,p_status text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.retell_call_batches%ROWTYPE; item jsonb; idx int; ledger public.retell_call_requests%ROWTYPE; updated jsonb;
BEGIN
  IF p_status NOT IN ('accepted','blocked','unknown') THEN RAISE EXCEPTION 'Invalid batch outcome'; END IF;
  SELECT * INTO b FROM public.retell_call_batches WHERE id=p_batch FOR UPDATE;
  IF NOT FOUND OR b.status NOT IN ('processing','review') THEN RAISE EXCEPTION 'Batch is not awaiting an outcome'; END IF;
  SELECT e.value,e.ordinality-1 INTO item,idx FROM jsonb_array_elements(b.outcomes) WITH ORDINALITY e
    WHERE e.value->>'request_id'=p_reference::text AND e.value->>'status' IN ('submitting','unknown');
  IF item IS NULL THEN RAISE EXCEPTION 'No matching claimed batch item'; END IF;
  SELECT * INTO ledger FROM public.retell_call_requests WHERE id=p_reference;
  IF FOUND THEN
    IF ledger.lead_id::text<>item->>'lead_id' OR ledger.phone_number<>item->>'phone_number' THEN RAISE EXCEPTION 'Mismatched batch call'; END IF;
    IF p_status='blocked' OR (p_status='accepted' AND (ledger.provider_call_id IS NULL OR ledger.status NOT IN ('accepted','completed'))) THEN
      RAISE EXCEPTION 'Provider outcome not confirmed';
    END IF;
  ELSIF p_status='accepted' THEN RAISE EXCEPTION 'No durable call receipt'; END IF;
  updated:=jsonb_set(b.outcomes,ARRAY[idx::text],item||jsonb_build_object('status',p_status,'reason',left(p_reason,500)));
  UPDATE public.retell_call_batches SET outcomes=updated,status=CASE WHEN p_status='unknown' THEN 'review'
    WHEN EXISTS(SELECT 1 FROM jsonb_array_elements(updated) e WHERE e->>'status'='pending') THEN 'ready'
    ELSE 'completed' END WHERE id=p_batch;
  RETURN jsonb_build_object('saved',true);
END; $$;
REVOKE ALL ON FUNCTION public.finish_retell_batch_item(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_retell_batch_item(uuid,uuid,text,text) TO service_role;
