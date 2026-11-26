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
 AND NOT coalesce(d.source='twilio' AND d.reason='opt_out' AND public.sms_stop_has_reviewed_opt_in(d.id),false)
 ),
 'duplicate', EXISTS (
   SELECT 1 FROM contacts c WHERE c.phone=input.phone AND c.id<>p_lead
   AND lower(trim(c.property_address))=lower(trim(p_property))
   AND c.created_at >= now()-interval '30 days'
 )
) FROM input;
$function$
;
