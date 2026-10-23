-- Candidate-only buyer email dispatch latch. Buyer SMS remains inquiry-route blocked.
ALTER TABLE public.buyer_outreach_log ALTER COLUMN buyer_id DROP NOT NULL;
ALTER TABLE public.buyer_outreach_log DROP CONSTRAINT buyer_outreach_log_buyer_id_fkey;
ALTER TABLE public.buyer_outreach_log ADD CONSTRAINT buyer_outreach_log_buyer_id_fkey
 FOREIGN KEY(buyer_id) REFERENCES public.buyers(id) ON DELETE SET NULL;
ALTER TABLE public.buyer_outreach_log ADD COLUMN request_id uuid,
 ADD COLUMN provider_submission_id text, ADD COLUMN buyer_snapshot jsonb NOT NULL DEFAULT '{}', ADD COLUMN outcome_reason text;
DO $$ DECLARE policy_name text; BEGIN
 FOR policy_name IN SELECT polname FROM pg_policy WHERE polrelid='public.buyer_outreach_log'::regclass LOOP
   EXECUTE format('DROP POLICY %I ON public.buyer_outreach_log',policy_name);
 END LOOP; END $$;
REVOKE ALL ON public.buyer_outreach_log FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.buyer_outreach_log TO authenticated;
CREATE POLICY buyer_history_approved_read ON public.buyer_outreach_log FOR SELECT TO authenticated
 USING(public.is_approved());
CREATE TABLE private.buyer_outreach_attempts (
 id uuid PRIMARY KEY, request_id uuid NOT NULL, operator_id uuid NOT NULL,
 buyer_id uuid NOT NULL, channel text NOT NULL CHECK(channel IN ('sms','email')),
 payload jsonb NOT NULL, status text NOT NULL, reason text NOT NULL,
 provider_message_id text, provider_submission_id text, conflict boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.buyer_outreach_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_outreach_attempts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON private.buyer_outreach_attempts TO service_role;
CREATE FUNCTION private.protect_buyer_outreach_attempt() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['status','reason','provider_message_id','provider_submission_id','conflict'])
 IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','reason','provider_message_id','provider_submission_id','conflict'])
 THEN RAISE EXCEPTION 'Buyer outreach identity is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_buyer_outreach_attempt() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER buyer_outreach_attempt_identity BEFORE UPDATE OR DELETE ON private.buyer_outreach_attempts
 FOR EACH ROW EXECUTE FUNCTION private.protect_buyer_outreach_attempt();

CREATE FUNCTION public.claim_buyer_outreach(p_id uuid,p_request uuid,p_operator uuid,p_buyer uuid,p_channel text,p_payload jsonb,p_hold text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a private.buyer_outreach_attempts; b public.buyers; destination text; why text:=''; state text; snapshot jsonb;
BEGIN
 IF p_id IS NULL OR p_request IS NULL OR p_buyer IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF p_channel NOT IN ('sms','email') OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
 OR coalesce(p_payload->>'body','')='' THEN RAISE EXCEPTION 'Invalid outreach payload' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-outreach:'||p_id::text,0));
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
   IF a.operator_id<>p_operator THEN RAISE EXCEPTION 'Foreign outreach reference' USING ERRCODE='42501'; END IF;
   IF a.request_id<>p_request OR a.buyer_id<>p_buyer OR a.channel<>p_channel OR a.payload<>p_payload
   THEN RAISE EXCEPTION 'Outreach reference changed' USING ERRCODE='22023'; END IF;
   IF a.channel='email' AND a.status IN ('submitting','unknown') THEN
     PERFORM public.finish_buyer_outreach(p_id,p_operator,'unknown','recovered_native_result');
     SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id;
   END IF;
   RETURN jsonb_build_object('id',a.id,'claimed',false,'status',a.status,'reason',a.reason,'provider_message_id',a.provider_message_id,'provider_submission_id',a.provider_submission_id);
 END IF;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 IF NOT FOUND THEN why:='buyer_missing';
 ELSIF b.active IS DISTINCT FROM true THEN why:='buyer_inactive';
 ELSIF p_channel='email' AND b.email_opt_in IS DISTINCT FROM true THEN why:='email_not_opted_in';
 ELSIF p_channel='sms' AND b.sms_opt_in IS DISTINCT FROM true THEN why:='sms_not_opted_in'; END IF;
 destination:=CASE WHEN p_channel='email' THEN lower(btrim(coalesce(b.email,''))) ELSE coalesce(b.phone,'') END;
 IF why='' AND destination='' THEN why:='destination_missing'; END IF;
 IF why='' AND destination IS DISTINCT FROM p_payload->>'destination' THEN
   RAISE EXCEPTION 'Buyer destination changed' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-destination:'||p_channel||':'||destination,0));
 IF why='' AND p_channel='email' AND (EXISTS(SELECT 1 FROM public.email_suppressions WHERE email=destination)
   OR EXISTS(SELECT 1 FROM public.dnc_registry WHERE lower(btrim(email))=destination)
   OR EXISTS(SELECT 1 FROM public.leads WHERE lower(btrim(owner_email))=destination AND dnc IS TRUE)) THEN why:='email_suppressed'; END IF;
 -- The existing sender route authorizes property inquiries, never buyer blasts.
 IF why='' AND p_channel='sms' THEN why:='buyer_sms_route_unavailable'; END IF;
 IF why='' AND coalesce(p_hold,'')<>'' THEN why:=p_hold; END IF;
 IF why='' AND (EXISTS(SELECT 1 FROM private.buyer_outreach_attempts WHERE channel=p_channel
    AND payload->>'destination'=destination AND status IN ('submitting','unknown'))
   OR EXISTS(SELECT 1 FROM public.email_messages WHERE recipient=destination AND status IN ('attempting','unknown')))
 THEN why:='earlier_submission_unconfirmed'; END IF;
 state:=CASE WHEN why='earlier_submission_unconfirmed' THEN 'held' WHEN why<>'' THEN 'skipped' ELSE 'submitting' END;
 snapshot:=jsonb_build_object('id',p_buyer,'first_name',b.first_name,'last_name',b.last_name);
 INSERT INTO private.buyer_outreach_attempts(id,request_id,operator_id,buyer_id,channel,payload,status,reason)
 VALUES(p_id,p_request,p_operator,p_buyer,p_channel,p_payload,state,why);
 INSERT INTO public.buyer_outreach_log(id,buyer_id,request_id,buyer_snapshot,deal_id,channel,direction,status,subject,body,to_address,outcome_reason)
 VALUES(p_id,b.id,p_request,snapshot,(p_payload->>'deal_id')::uuid,p_channel,'outbound',state,p_payload->>'subject',p_payload->>'body',destination,why);
 RETURN jsonb_build_object('id',p_id,'claimed',state='submitting','status',state,'reason',why,'provider_message_id',NULL);
END $$;
REVOKE ALL ON FUNCTION public.claim_buyer_outreach(uuid,uuid,uuid,uuid,text,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_buyer_outreach(uuid,uuid,uuid,uuid,text,jsonb,text) TO service_role;

CREATE FUNCTION public.finish_buyer_outreach(p_id uuid,p_operator uuid,p_status text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a private.buyer_outreach_attempts; m public.email_messages; outcome text; sid text;
BEGIN
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR a.operator_id<>p_operator OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Outreach access denied' USING ERRCODE='42501'; END IF;
 IF p_status NOT IN ('accepted','unknown','skipped') THEN RAISE EXCEPTION 'Invalid outcome' USING ERRCODE='22023'; END IF;
 SELECT * INTO m FROM public.email_messages WHERE id=p_id AND recipient=a.payload->>'destination';
 IF a.provider_submission_id IS NOT NULL AND nullif(m.provider_message_id,'') IS NOT NULL
 AND a.provider_submission_id<>m.provider_message_id THEN
   UPDATE private.buyer_outreach_attempts SET status='unknown',reason='conflicting_provider_ids',conflict=true WHERE id=p_id RETURNING * INTO a;
   UPDATE public.buyer_outreach_log SET status='unknown',outcome_reason=a.reason WHERE id=p_id;
 END IF;
 IF a.status IN ('submitting','unknown') AND NOT a.conflict THEN
   SELECT * INTO m FROM public.email_messages WHERE id=p_id AND recipient=a.payload->>'destination';
   sid:=m.provider_message_id;
   outcome:=CASE WHEN m.status='accepted' AND nullif(sid,'') IS NOT NULL THEN 'accepted'
     WHEN p_status='skipped' AND m.id IS NULL THEN 'skipped' ELSE 'unknown' END;
   UPDATE private.buyer_outreach_attempts SET status=outcome,reason=coalesce(p_reason,''),provider_submission_id=sid WHERE id=p_id RETURNING * INTO a;
   UPDATE public.buyer_outreach_log SET status=a.status,outcome_reason=a.reason,provider_submission_id=sid,provider=m.provider WHERE id=p_id;
 END IF;
 RETURN jsonb_build_object('id',a.id,'claimed',false,'status',a.status,'reason',a.reason,'provider_message_id',a.provider_message_id,'provider_submission_id',a.provider_submission_id);
END $$;
REVOKE ALL ON FUNCTION public.finish_buyer_outreach(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_buyer_outreach(uuid,uuid,text,text) TO service_role;

-- Only verified SendGrid ingress writes this service-owned event table. Bind
-- callback evidence to the existing native email claim and recipient, never a name.
CREATE FUNCTION private.buyer_email_delivery() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a private.buyer_outreach_attempts; sid text; incoming text; outcome text; clash boolean;
BEGIN
 IF NEW.message_id IS NULL THEN RETURN NEW; END IF;
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=NEW.message_id AND channel='email' FOR UPDATE;
 IF NOT FOUND OR a.payload->>'destination'<>NEW.recipient OR NOT EXISTS(SELECT 1 FROM public.email_messages
   WHERE id=a.id AND provider='sendgrid' AND recipient=NEW.recipient) THEN RETURN NEW; END IF;
 sid:=nullif(NEW.payload->>'provider_message_id','');
 IF sid IS NULL THEN RETURN NEW; END IF;
 incoming:=CASE WHEN NEW.event='delivered' THEN 'delivered'
   WHEN NEW.event IN ('bounce','dropped') THEN 'failed' ELSE NULL END;
 IF incoming IS NULL THEN RETURN NEW; END IF;
 clash:=a.conflict OR (a.provider_message_id IS NOT NULL AND a.provider_message_id<>sid)
   OR (a.status='delivered' AND incoming='failed') OR (a.status='failed' AND incoming='delivered');
 outcome:=CASE WHEN clash THEN 'unknown' ELSE incoming END;
 UPDATE private.buyer_outreach_attempts SET status=outcome,reason=CASE WHEN clash THEN 'conflicting_receipts' ELSE 'verified_sendgrid_'||NEW.event END,
   provider_message_id=coalesce(a.provider_message_id,sid),conflict=clash WHERE id=a.id;
 UPDATE public.buyer_outreach_log SET status=outcome,outcome_reason=CASE WHEN clash THEN 'conflicting_receipts' ELSE 'verified_sendgrid_'||NEW.event END,
   provider='sendgrid',provider_msg_id=coalesce(a.provider_message_id,sid) WHERE id=a.id;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.buyer_email_delivery() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER buyer_email_delivery_receipt AFTER INSERT ON public.email_delivery_events
 FOR EACH ROW EXECUTE FUNCTION private.buyer_email_delivery();

CREATE FUNCTION public.reconcile_buyer_outreach_campaign(p_request uuid,p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE row_id uuid; checked integer:=0;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 OR NOT EXISTS(SELECT 1 FROM private.buyer_outreach_attempts WHERE request_id=p_request AND operator_id=p_operator)
 THEN RAISE EXCEPTION 'Outreach reference unavailable' USING ERRCODE='42501'; END IF;
 FOR row_id IN SELECT id FROM private.buyer_outreach_attempts WHERE request_id=p_request AND operator_id=p_operator ORDER BY id LOOP
   PERFORM public.finish_buyer_outreach(row_id,p_operator,'unknown','operator_reconciliation');
   checked:=checked+1;
 END LOOP;
 RETURN jsonb_build_object('request_id',p_request,'checked',checked,'provider_calls',0);
END $$;
REVOKE ALL ON FUNCTION public.reconcile_buyer_outreach_campaign(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_buyer_outreach_campaign(uuid,uuid) TO service_role;
