-- One transaction per authenticated Twilio event; only the backend may call it.
CREATE OR REPLACE FUNCTION public.record_twilio_event(p_event uuid, p_kind text, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_phone text;
  v_lead uuid;
  v_inserted uuid;
  v_stop boolean;
  v_body text := coalesce(p_payload->>'Body','');
  v_control text := upper(trim(coalesce(p_payload->>'OptOutType',p_payload->>'Body','')));
BEGIN
  IF p_kind NOT IN ('inbound','status') OR coalesce(p_payload->>'MessageSid','') !~ '^SM[0-9a-fA-F]{32}$' THEN
    RAISE EXCEPTION 'Invalid Twilio event';
  END IF;
  v_phone := CASE WHEN p_kind='inbound' THEN p_payload->>'From' ELSE p_payload->>'To' END;
  IF coalesce(v_phone,'') !~ '^\+1[0-9]{10}$' THEN RAISE EXCEPTION 'Invalid phone'; END IF;
  v_stop := p_kind='inbound' AND (v_control IN ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT')
    OR upper(trim(v_body)) IN ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT'));
  IF p_kind='status' THEN
    IF p_payload->>'app_message_id' IS NOT NULL THEN
      SELECT lead_id INTO v_lead FROM public.sms_events WHERE id=(p_payload->>'app_message_id')::uuid
        AND provider='twilio' AND direction='outbound' AND phone_number=v_phone;
    ELSE
      SELECT lead_id INTO v_lead FROM public.sms_events WHERE provider='twilio'
        AND raw_payload->>'provider_sid'=p_payload->>'MessageSid' LIMIT 1;
    END IF;
  ELSE
    SELECT id INTO v_lead FROM public.leads l WHERE EXISTS (
      SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
      WHERE regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=right(v_phone,10)
    ) ORDER BY created_at DESC LIMIT 1;
  END IF;
  INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status,opt_out,raw_payload)
    VALUES(p_event,v_lead,'twilio',CASE WHEN p_kind='inbound' THEN 'inbound' ELSE 'outbound' END,
      v_phone,v_body,CASE WHEN p_kind='inbound' THEN 'replied' ELSE p_payload->>'MessageStatus' END,v_stop,p_payload)
    ON CONFLICT(id) DO NOTHING RETURNING id INTO v_inserted;
  IF v_inserted IS NULL THEN RETURN jsonb_build_object('saved',true,'duplicate',true); END IF;
  IF v_stop THEN
    -- Store even unknown numbers so a later imported lead remains suppressed.
    INSERT INTO public.dnc_registry(id,phone_number,lead_id,reason,source,opt_out_keyword,raw_payload)
      VALUES(p_event,v_phone,v_lead,'opt_out','twilio',left(v_body,100),p_payload) ON CONFLICT(id) DO NOTHING;
    UPDATE public.leads l SET dnc=true,status='dnc',sms_sequence_active=false,email_sequence_active=false,ai_calling_paused=true
      WHERE EXISTS (SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
        WHERE regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=right(v_phone,10));
  ELSIF p_kind='inbound' AND v_control NOT IN ('START','UNSTOP','YES','HELP','INFO') THEN
    UPDATE public.leads SET status='responding',sms_sequence_active=false,ai_calling_paused=true
      WHERE id=v_lead AND dnc IS FALSE AND status NOT IN ('dead','dnc','closed');
  END IF;
  -- START is recorded, but never automatically clears existing DNC or renews consent.
  IF p_kind='inbound' THEN
    INSERT INTO public.app_notifications(id,recipient_role,type,title,body,action_url,lead_id,metadata)
      VALUES(p_event,'admin','pipeline_step',CASE WHEN v_stop THEN 'SMS opt-out received' ELSE 'SMS reply received' END,
        left(v_body,500),'/leads',v_lead,jsonb_build_object('provider','twilio','message_sid',p_payload->>'MessageSid','opt_out',v_stop));
  END IF;
  RETURN jsonb_build_object('saved',true,'duplicate',false);
END;
$$;
REVOKE ALL ON FUNCTION public.record_twilio_event(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_twilio_event(uuid,text,jsonb) TO service_role;
