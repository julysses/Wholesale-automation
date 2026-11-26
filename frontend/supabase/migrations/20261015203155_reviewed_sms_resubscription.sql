-- Reviewed re-subscription preserves original STOP and requires both carrier START and fresh form consent.
CREATE TABLE public.sms_resubscription_reviews (
 stop_event_id uuid PRIMARY KEY REFERENCES public.sms_events(id),
 start_event_id uuid NOT NULL REFERENCES public.sms_events(id),
 submission_id uuid NOT NULL REFERENCES public.lead_form_submissions(id),
 reviewed_at timestamptz NOT NULL DEFAULT now(),
 review_note text NOT NULL CHECK(length(trim(review_note))>10)
);
ALTER TABLE public.sms_resubscription_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sms_resubscription_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.sms_resubscription_reviews TO service_role;
-- Only database operator may record a review. START alone never clears suppression.
CREATE FUNCTION public.sms_stop_has_reviewed_opt_in(p_stop uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT EXISTS (
 SELECT 1 FROM public.sms_resubscription_reviews r
 JOIN public.sms_events stop ON stop.id=r.stop_event_id
 JOIN public.sms_events start ON start.id=r.start_event_id
 JOIN public.lead_form_submissions f ON f.id=r.submission_id
 WHERE r.stop_event_id=p_stop AND stop.opt_out IS TRUE
 AND stop.provider='twilio' AND stop.direction='inbound'
 AND start.provider='twilio' AND start.direction='inbound' AND start.opt_out IS FALSE
 AND start.raw_payload->>'OptOutType'='START'
 AND start.phone_number=stop.phone_number AND start.created_at>stop.created_at
 AND f.created_at>=start.created_at AND r.reviewed_at>=f.created_at
 AND f.raw_answers->'_sms_consent'->>'accepted'='true'
 AND f.raw_answers->'_sms_consent'->>'rendered_disclosure_matches'='true'
 AND right(regexp_replace(f.raw_answers->>'phone','[^0-9]','','g'),10)=right(start.phone_number,10)
 );
$$;
REVOKE ALL ON FUNCTION public.sms_stop_has_reviewed_opt_in(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sms_stop_has_reviewed_opt_in(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.intake_phone_status(p_phone text, p_lead uuid, p_property text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $function$
WITH input AS (
 SELECT regexp_replace(regexp_replace(coalesce(p_phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1') AS phone
), contacts AS (
 SELECT l.id,l.dnc,l.property_address,l.created_at,
   regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1') AS phone
 FROM public.leads l CROSS JOIN LATERAL unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
)
SELECT jsonb_build_object(
 'suppressed', input.phone !~ '^[0-9]{10}$' OR EXISTS (
   SELECT 1 FROM contacts c WHERE c.phone=input.phone AND c.dnc IS TRUE
 ) OR EXISTS (
   SELECT 1 FROM public.dnc_registry d WHERE (d.lead_id=p_lead OR
   regexp_replace(regexp_replace(coalesce(d.phone_number,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=input.phone)
 AND NOT (d.source='twilio' AND d.reason='opt_out' AND public.sms_stop_has_reviewed_opt_in(d.id))
 ),
 'duplicate', EXISTS (
   SELECT 1 FROM contacts c WHERE c.phone=input.phone AND c.id<>p_lead
   AND lower(trim(c.property_address))=lower(trim(p_property))
   AND c.created_at >= now()-interval '30 days'
 )
) FROM input;
$function$
;
CREATE OR REPLACE FUNCTION public.claim_retell_form_sms(p_limit integer DEFAULT 3)
 RETURNS SETOF retell_form_sms_jobs
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE j public.retell_form_sms_jobs;
BEGIN
  FOR j IN SELECT * FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now()
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT least(greatest(p_limit,1),10)
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
