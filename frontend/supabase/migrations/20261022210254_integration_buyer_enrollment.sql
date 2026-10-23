-- Buyer enrollment capabilities. No public table grants, invitations or sends are seeded.
CREATE TABLE private.buyer_enrollment_invites (
 id uuid PRIMARY KEY, buyer_id uuid NOT NULL, operator_id uuid NOT NULL,
 token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[0-9a-f]{64}$'),
 phone text NOT NULL, program jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '7 days'
);
CREATE TABLE private.buyer_enrollment_submissions (
 id uuid PRIMARY KEY, invite_id uuid NOT NULL UNIQUE REFERENCES private.buyer_enrollment_invites(id),
 buyer_id uuid NOT NULL, phone text NOT NULL, accepted boolean NOT NULL,
 evidence jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.buyer_enrollment_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE private.buyer_enrollment_submissions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_enrollment_invites,private.buyer_enrollment_submissions FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.buyer_enrollment_invites,private.buyer_enrollment_submissions TO service_role;
CREATE TRIGGER buyer_enrollment_invite_immutable BEFORE UPDATE OR DELETE ON private.buyer_enrollment_invites
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();
CREATE TRIGGER buyer_enrollment_submission_immutable BEFORE UPDATE OR DELETE ON private.buyer_enrollment_submissions
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();
CREATE INDEX buyer_enrollment_buyer_history ON private.buyer_enrollment_submissions(buyer_id,created_at DESC,id DESC);

CREATE FUNCTION public.create_buyer_enrollment_invite(p_id uuid,p_buyer uuid,p_operator uuid,p_hash text,p_program jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.buyers; prior private.buyer_enrollment_invites; v_phone text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_buyer IS NULL OR coalesce(p_hash,'') !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(p_program) IS DISTINCT FROM 'object' OR coalesce(p_program->>'version','') !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'Invalid enrollment invitation' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-enrollment-invite:'||p_id::text,0));
 SELECT * INTO prior FROM private.buyer_enrollment_invites WHERE id=p_id;
 IF FOUND THEN
   IF prior.buyer_id<>p_buyer OR prior.operator_id<>p_operator OR prior.token_hash<>p_hash OR prior.program<>p_program
   THEN RAISE EXCEPTION 'Invitation reference changed' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'expires_at',prior.expires_at);
 END IF;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 v_phone:=private.buyer_phone(b.phone);
 IF b.id IS NULL OR v_phone IS NULL OR b.active IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'Active buyer with valid phone required' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_enrollment_invites(id,buyer_id,operator_id,token_hash,phone,program)
 VALUES(p_id,p_buyer,p_operator,p_hash,v_phone,p_program) RETURNING * INTO prior;
 RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'expires_at',prior.expires_at);
END $$;
REVOKE ALL ON FUNCTION public.create_buyer_enrollment_invite(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.create_buyer_enrollment_invite(uuid,uuid,uuid,text,jsonb) TO service_role;

CREATE FUNCTION public.buyer_enrollment_receipt(p_id uuid,p_hash text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT coalesce((SELECT jsonb_build_object('id',s.id,'saved',true,'accepted',s.accepted)
 FROM private.buyer_enrollment_submissions s JOIN private.buyer_enrollment_invites i ON i.id=s.invite_id
 WHERE s.id=p_id AND i.token_hash=p_hash),jsonb_build_object('id',p_id,'saved',false));
$$;
REVOKE ALL ON FUNCTION public.buyer_enrollment_receipt(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.buyer_enrollment_receipt(uuid,text) TO service_role;

CREATE FUNCTION public.submit_buyer_enrollment(p_id uuid,p_hash text,p_phone text,p_accepted boolean,p_version text,p_program jsonb,p_hold boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE i private.buyer_enrollment_invites; s private.buyer_enrollment_submissions; v_phone text; b public.buyers; evidence jsonb; v_owner uuid;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-enrollment-submit:'||p_hash,0));
 SELECT * INTO i FROM private.buyer_enrollment_invites WHERE token_hash=p_hash;
 IF NOT FOUND OR i.id IS DISTINCT FROM p_id THEN RAISE EXCEPTION 'Enrollment unavailable' USING ERRCODE='22023'; END IF;
 v_phone:=private.buyer_phone(p_phone);
 SELECT * INTO s FROM private.buyer_enrollment_submissions WHERE invite_id=i.id;
 IF FOUND THEN
   IF s.phone IS DISTINCT FROM v_phone OR s.accepted IS DISTINCT FROM p_accepted OR i.program->>'version' IS DISTINCT FROM p_version
   THEN RAISE EXCEPTION 'Enrollment unavailable' USING ERRCODE='22023'; END IF;
   RETURN public.buyer_enrollment_receipt(p_id,p_hash);
 END IF;
 IF p_hold OR p_accepted IS NULL OR i.expires_at<=now() OR v_phone IS DISTINCT FROM i.phone
 OR i.program IS DISTINCT FROM p_program OR i.program->>'version' IS DISTINCT FROM p_version
 THEN RAISE EXCEPTION 'Enrollment unavailable' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||v_phone,0));
 SELECT * INTO b FROM public.buyers WHERE id=i.buyer_id FOR UPDATE;
 IF NOT FOUND OR private.buyer_phone(b.phone) IS DISTINCT FROM v_phone OR b.active IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'Enrollment unavailable' USING ERRCODE='22023'; END IF;
 evidence:=jsonb_build_object('id',p_id,'buyer_id',b.id,'phone',v_phone,'accepted',p_accepted,
 'submitted_at',now(),'program',i.program,'affirmative_action',CASE WHEN p_accepted THEN 'Selected optional buyer SMS checkbox and submitted the choice' ELSE 'Submitted with buyer SMS checkbox unchecked' END);
 INSERT INTO private.buyer_enrollment_submissions(id,invite_id,buyer_id,phone,accepted,evidence)
 VALUES(p_id,i.id,b.id,v_phone,p_accepted,evidence);
 IF NOT p_accepted THEN UPDATE public.buyers SET sms_opt_in=false WHERE id=b.id; END IF;
 SELECT id INTO v_owner FROM public.profiles WHERE id=i.operator_id AND status='approved' AND role='admin';
 IF v_owner IS NULL THEN SELECT p.id INTO v_owner FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' AND p.role='admin'; END IF;
 INSERT INTO public.tasks(id,buyer_id,title,description,priority,status,type,assigned_to,due_date)
 VALUES(p_id,b.id,'Review buyer SMS enrollment','Retained consumer choice for program '||(i.program->>'version'),
 'high','pending','buyer_enrollment_review',v_owner,now());
 INSERT INTO public.app_notifications(id,recipient_id,recipient_role,type,title,body,action_url,metadata)
 VALUES(md5('buyer-enrollment:'||p_id::text)::uuid,v_owner,'admin','pipeline_step','Buyer SMS enrollment choice',
 CASE WHEN p_accepted THEN 'A buyer requested deal-alert SMS. Review the retained consent before activation.' ELSE 'A buyer kept SMS off. The refusal is already effective.' END,
 '/buyer-intel',jsonb_build_object('enrollment_id',p_id,'buyer_id',b.id,'accepted',p_accepted));
 -- Positive submissions deliberately do not opt in the buyer; reviewed evidence is still required.
 RETURN public.buyer_enrollment_receipt(p_id,p_hash);
END $$;
REVOKE ALL ON FUNCTION public.submit_buyer_enrollment(uuid,text,text,boolean,text,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.submit_buyer_enrollment(uuid,text,text,boolean,text,jsonb,boolean) TO service_role;

CREATE FUNCTION public.buyer_enrollment_submissions(p_buyer uuid,p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required' USING ERRCODE='42501'; END IF;
 IF p_offset<0 THEN RAISE EXCEPTION 'Invalid page' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('buyer_id',p_buyer,'total',(SELECT count(*) FROM private.buyer_enrollment_submissions WHERE buyer_id=p_buyer),
 'offset',p_offset,'submissions',(SELECT coalesce(jsonb_agg(to_jsonb(v)),'[]') FROM (
 SELECT s.id,s.phone,s.accepted,s.created_at,s.evidence,
 encode(sha256(convert_to(s.evidence::text,'UTF8')),'hex') evidence_sha256,
 EXISTS(SELECT 1 FROM private.buyer_sms_consent_reviews r WHERE r.id=s.id) reviewed
 FROM private.buyer_enrollment_submissions s WHERE buyer_id=p_buyer ORDER BY created_at DESC,id DESC OFFSET p_offset LIMIT 20) v));
END $$;
REVOKE ALL ON FUNCTION public.buyer_enrollment_submissions(uuid,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.buyer_enrollment_submissions(uuid,uuid,integer) TO service_role;

CREATE FUNCTION public.review_buyer_enrollment(p_id uuid,p_buyer uuid,p_operator uuid,p_origin text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s private.buyer_enrollment_submissions; evidence jsonb; result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required' USING ERRCODE='42501'; END IF;
 SELECT * INTO s FROM private.buyer_enrollment_submissions WHERE id=p_id AND buyer_id=p_buyer;
 IF NOT FOUND OR coalesce(p_origin,'') !~ '^https://[^/?#[:space:]]+$' THEN RAISE EXCEPTION 'Enrollment unavailable' USING ERRCODE='22023'; END IF;
 evidence:=jsonb_build_object('source_type','written_web_form','source_url',p_origin||'/buyer-intel#enrollment='||s.id::text,
 'sha256',encode(sha256(convert_to(s.evidence::text,'UTF8')),'hex'),'consented_at',s.created_at,
 'disclosure',s.evidence->'program'->>'disclosure','affirmative_action',s.evidence->>'affirmative_action',
 'reviewed_written_evidence',true,'enrollment_id',s.id,'program_version',s.evidence->'program'->>'version');
 result:=public.review_buyer_sms_consent(s.id,p_buyer,p_operator,s.phone,evidence,s.accepted);
 UPDATE public.tasks SET status='completed',completed_at=coalesce(completed_at,now()) WHERE id=p_id AND type='buyer_enrollment_review' AND status='pending';
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.review_buyer_enrollment(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_buyer_enrollment(uuid,uuid,uuid,text) TO service_role;

-- Consumer refusals remain effective even if an older positive receipt is reviewed later.
CREATE OR REPLACE FUNCTION public.buyer_sms_consent_status(p_buyer uuid,p_operator uuid) RETURNS jsonb
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
 eligible:=v_phone IS NOT NULL AND b.active IS TRUE AND b.sms_opt_in IS TRUE AND receipt.accepted IS TRUE AND NOT suppressed AND NOT EXISTS(SELECT 1 FROM private.buyer_enrollment_submissions s
 WHERE s.buyer_id=p_buyer AND s.phone=v_phone AND NOT s.accepted
 AND s.created_at>coalesce((receipt.evidence->>'consented_at')::timestamptz,'epoch'::timestamptz));
 RETURN jsonb_build_object('buyer_id',p_buyer,'phone',v_phone,'can_review',EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin'),
 'consent_ready',coalesce(eligible,false),'suppressed',suppressed,'receipt_id',receipt.id,
 'accepted',receipt.accepted,'recorded_at',receipt.recorded_at,'evidence',receipt.evidence,
 'sending_available',false,'sending_reason','buyer_campaign_and_transport_not_accepted');
END $$;
REVOKE ALL ON FUNCTION public.buyer_sms_consent_status(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.buyer_sms_consent_status(uuid,uuid) TO service_role;


CREATE OR REPLACE FUNCTION public.review_buyer_sms_consent(p_id uuid,p_buyer uuid,p_operator uuid,p_phone text,p_evidence jsonb,p_accepted boolean)
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
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||v_phone,0));
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer not found' USING ERRCODE='P0002'; END IF;
 IF v_phone IS DISTINCT FROM private.buyer_phone(b.phone)
 THEN RAISE EXCEPTION 'Buyer phone changed; review the current number' USING ERRCODE='22023'; END IF;
 suppressed:=EXISTS(SELECT 1 FROM public.dnc_registry WHERE private.buyer_phone(phone_number)=v_phone)
 OR EXISTS(SELECT 1 FROM public.leads l WHERE l.dnc IS TRUE AND v_phone IN (
 private.buyer_phone(l.owner_phone_1),private.buyer_phone(l.owner_phone_2),private.buyer_phone(l.owner_phone_3)));
 IF p_accepted AND suppressed THEN RAISE EXCEPTION 'Phone is suppressed; review cannot clear suppression' USING ERRCODE='22023'; END IF;
 IF p_accepted AND EXISTS(SELECT 1 FROM private.buyer_enrollment_submissions s WHERE s.buyer_id=p_buyer AND s.phone=v_phone
 AND NOT s.accepted AND s.created_at>(p_evidence->>'consented_at')::timestamptz)
 THEN RAISE EXCEPTION 'Later buyer refusal requires new written consent' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_sms_consent_reviews(id,buyer_id,operator_id,phone,evidence,accepted)
 VALUES(p_id,p_buyer,p_operator,v_phone,p_evidence,p_accepted);
 UPDATE public.buyers SET sms_opt_in=p_accepted WHERE id=p_buyer;
 RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'duplicate',false,'accepted',p_accepted);
END $$;
REVOKE ALL ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) TO service_role;
