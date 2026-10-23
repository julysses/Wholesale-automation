-- Candidate-only, reviewed written buyer SMS consent; no sender activation.
CREATE TABLE private.buyer_sms_consent_reviews (
 id uuid PRIMARY KEY, buyer_id uuid NOT NULL, operator_id uuid NOT NULL,
 phone text NOT NULL CHECK(phone ~ '^\+1[0-9]{10}$'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 accepted boolean NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.buyer_sms_consent_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_sms_consent_reviews FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.buyer_sms_consent_reviews TO service_role;
CREATE TRIGGER buyer_sms_consent_immutable BEFORE UPDATE OR DELETE ON private.buyer_sms_consent_reviews
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();

CREATE FUNCTION private.buyer_phone(p_phone text) RETURNS text
LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT CASE WHEN length(n)=10 THEN '+1'||n WHEN length(n)=11 AND left(n,1)='1' THEN '+'||n ELSE NULL END
 FROM (SELECT regexp_replace(coalesce(p_phone,''),'[^0-9]','','g') n) v;
$$;
REVOKE ALL ON FUNCTION private.buyer_phone(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.buyer_phone(text) TO service_role;

CREATE FUNCTION public.buyer_sms_consent_status(p_buyer uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.buyers; receipt private.buyer_sms_consent_reviews; v_phone text; suppressed boolean; eligible boolean;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer not found' USING ERRCODE='P0002'; END IF;
 v_phone:=private.buyer_phone(b.phone);
 SELECT * INTO receipt FROM private.buyer_sms_consent_reviews WHERE buyer_id=p_buyer AND phone=v_phone
 ORDER BY recorded_at DESC,id DESC LIMIT 1;
 suppressed:=EXISTS(SELECT 1 FROM public.dnc_registry WHERE private.buyer_phone(phone_number)=v_phone)
 OR EXISTS(SELECT 1 FROM public.leads l WHERE l.dnc IS TRUE AND v_phone IN (
 private.buyer_phone(l.owner_phone_1),private.buyer_phone(l.owner_phone_2),private.buyer_phone(l.owner_phone_3)));
 eligible:=v_phone IS NOT NULL AND b.active IS TRUE AND b.sms_opt_in IS TRUE AND receipt.accepted IS TRUE AND NOT suppressed;
 RETURN jsonb_build_object('buyer_id',p_buyer,'phone',v_phone,'can_review',EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin'),
 'consent_ready',coalesce(eligible,false),'suppressed',suppressed,'receipt_id',receipt.id,
 'accepted',receipt.accepted,'recorded_at',receipt.recorded_at,'evidence',receipt.evidence,
 'sending_available',false,'sending_reason','buyer_campaign_and_transport_not_accepted');
END $$;
REVOKE ALL ON FUNCTION public.buyer_sms_consent_status(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.buyer_sms_consent_status(uuid,uuid) TO service_role;

CREATE FUNCTION public.review_buyer_sms_consent(p_id uuid,p_buyer uuid,p_operator uuid,p_phone text,p_evidence jsonb,p_accepted boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.buyers; prior private.buyer_sms_consent_reviews; v_phone text; suppressed boolean;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_buyer IS NULL OR p_accepted IS NULL OR jsonb_typeof(p_evidence) IS DISTINCT FROM 'object'
 OR coalesce(p_evidence->>'source_type','') NOT IN ('signed_document','written_web_form')
 OR coalesce(p_evidence->>'source_url','') !~ '^https://[^[:space:]]+$'
 OR coalesce(p_evidence->>'sha256','') !~ '^[0-9a-f]{64}$'
 OR length(coalesce(p_evidence->>'disclosure','')) NOT BETWEEN 40 AND 4000
 OR length(coalesce(p_evidence->>'affirmative_action','')) NOT BETWEEN 3 AND 2000
 OR p_evidence->'reviewed_written_evidence' IS DISTINCT FROM 'true'::jsonb
 OR coalesce(p_evidence->>'consented_at','')=''
 THEN RAISE EXCEPTION 'Written consent evidence required' USING ERRCODE='22023'; END IF;
 IF (p_evidence->>'consented_at')::timestamptz>now()+interval '5 minutes'
 OR (p_evidence->>'consented_at')::timestamptz<'2000-01-01'::timestamptz
 THEN RAISE EXCEPTION 'Invalid consent date' USING ERRCODE='22023'; END IF;
 v_phone:=private.buyer_phone(p_phone);
 IF v_phone IS NULL THEN RAISE EXCEPTION 'Invalid US phone' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-sms-consent:'||p_id::text,0));
 SELECT * INTO prior FROM private.buyer_sms_consent_reviews WHERE id=p_id;
 IF FOUND THEN
   IF prior.buyer_id<>p_buyer OR prior.operator_id<>p_operator OR prior.phone<>v_phone
   OR prior.evidence<>p_evidence OR prior.accepted<>p_accepted
   THEN RAISE EXCEPTION 'Consent review reference changed' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'duplicate',true,'accepted',prior.accepted);
 END IF;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer not found' USING ERRCODE='P0002'; END IF;
 IF v_phone IS DISTINCT FROM private.buyer_phone(b.phone)
 THEN RAISE EXCEPTION 'Buyer phone changed; review the current number' USING ERRCODE='22023'; END IF;
 suppressed:=EXISTS(SELECT 1 FROM public.dnc_registry WHERE private.buyer_phone(phone_number)=v_phone)
 OR EXISTS(SELECT 1 FROM public.leads l WHERE l.dnc IS TRUE AND v_phone IN (
 private.buyer_phone(l.owner_phone_1),private.buyer_phone(l.owner_phone_2),private.buyer_phone(l.owner_phone_3)));
 IF p_accepted AND suppressed THEN RAISE EXCEPTION 'Phone is suppressed; review cannot clear suppression' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_sms_consent_reviews(id,buyer_id,operator_id,phone,evidence,accepted)
 VALUES(p_id,p_buyer,p_operator,v_phone,p_evidence,p_accepted);
 UPDATE public.buyers SET sms_opt_in=p_accepted WHERE id=p_buyer;
 RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'duplicate',false,'accepted',p_accepted);
END $$;
REVOKE ALL ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) TO service_role;
