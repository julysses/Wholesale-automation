-- Server-only delivery ledger. Provider acceptance is distinct from delivery events.
CREATE TABLE public.email_messages (
 id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
 recipient text NOT NULL, subject text NOT NULL, provider text NOT NULL,
 status text NOT NULL DEFAULT 'attempting', provider_message_id text,
 CHECK (recipient = lower(trim(recipient)))
);
CREATE TABLE public.email_delivery_events (
 event_id text PRIMARY KEY, received_at timestamptz NOT NULL DEFAULT now(),
 message_id uuid REFERENCES public.email_messages(id), recipient text NOT NULL,
 event text NOT NULL, occurred_at timestamptz NOT NULL, payload jsonb NOT NULL
);
CREATE INDEX email_delivery_events_message ON public.email_delivery_events(message_id,occurred_at);
CREATE TABLE public.email_suppressions (
 email text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), reason text NOT NULL,
 CHECK (email = lower(trim(email)))
);
ALTER TABLE public.email_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_delivery_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_suppressions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.email_messages,public.email_delivery_events,public.email_suppressions FROM anon,authenticated;
GRANT ALL ON public.email_messages,public.email_delivery_events,public.email_suppressions TO service_role;

CREATE FUNCTION public.claim_email_message(p_id uuid,p_email text,p_subject text,p_provider text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_email text := lower(trim(p_email)); v_id uuid;
BEGIN
 IF v_email = '' OR position('@' in v_email)=0 THEN RAISE EXCEPTION 'Invalid email'; END IF;
 -- Serialize suppression updates and claims for each mailbox.
 PERFORM pg_advisory_xact_lock(hashtextextended(v_email,0));
 IF EXISTS(SELECT 1 FROM public.email_suppressions WHERE email=v_email)
 OR EXISTS(SELECT 1 FROM public.dnc_registry WHERE lower(trim(email))=v_email)
 OR EXISTS(SELECT 1 FROM public.leads WHERE lower(trim(owner_email))=v_email AND dnc IS TRUE)
 THEN RETURN jsonb_build_object('claimed',false,'suppressed',true); END IF;
 INSERT INTO public.email_messages(id,recipient,subject,provider)
 VALUES(p_id,v_email,left(p_subject,998),p_provider) ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
 RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'suppressed',false);
END;
$$;
REVOKE ALL ON FUNCTION public.claim_email_message(uuid,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_email_message(uuid,text,text,text) TO service_role;

CREATE FUNCTION public.record_sendgrid_events(p_events jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE e jsonb; v_email text; v_id text; v_msg uuid; v_new text; v_stop boolean;
BEGIN
 IF jsonb_typeof(p_events)<>'array' OR jsonb_array_length(p_events)>1000 THEN RAISE EXCEPTION 'Invalid batch'; END IF;
 FOR e IN SELECT value FROM jsonb_array_elements(p_events) LOOP
  v_email:=lower(trim(e->>'email')); v_id:=e->>'event_id'; v_msg:=NULL;
  IF coalesce(v_email,'')='' OR coalesce(v_id,'')='' THEN RAISE EXCEPTION 'Invalid event'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(v_email,0));
  IF e->>'message_id' IS NOT NULL THEN
   SELECT id INTO v_msg FROM public.email_messages WHERE id=(e->>'message_id')::uuid AND recipient=v_email AND provider='sendgrid';
  END IF;
  INSERT INTO public.email_delivery_events(event_id,message_id,recipient,event,occurred_at,payload)
  VALUES(v_id,v_msg,v_email,e->>'event',to_timestamp((e->>'timestamp')::double precision),e)
  ON CONFLICT(event_id) DO NOTHING RETURNING event_id INTO v_new;
  IF v_new IS NULL THEN CONTINUE; END IF;
  v_stop:=e->>'event' IN ('unsubscribe','group_unsubscribe','spamreport','bounce');
  IF v_stop THEN
   INSERT INTO public.email_suppressions(email,reason) VALUES(v_email,e->>'event') ON CONFLICT(email) DO NOTHING;
   UPDATE public.leads SET email_sequence_active=false WHERE lower(trim(owner_email))=v_email;
   UPDATE public.buyers SET email_opt_in=false WHERE lower(trim(email))=v_email;
  END IF;
  -- Never remove suppression on group_resubscribe or on out-of-order delivery events.
  IF v_stop OR (v_msg IS NOT NULL AND e->>'event' IN ('delivered','dropped','deferred')) THEN
   INSERT INTO public.app_notifications(recipient_role,type,title,body,action_url,metadata)
   VALUES('admin','pipeline_step','Email ' || (e->>'event'),
    v_email || ': ' || left(coalesce(e->>'reason',e->>'event'),300),'/settings',
    jsonb_build_object('provider','sendgrid','message_id',v_msg,'event_id',v_id,'suppressed',v_stop));
  END IF;
 END LOOP;
 RETURN jsonb_build_object('saved',true);
END;
$$;
REVOKE ALL ON FUNCTION public.record_sendgrid_events(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_sendgrid_events(jsonb) TO service_role;
