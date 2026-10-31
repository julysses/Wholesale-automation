-- Require fresh capacity and server-verified bot evidence at the atomic write.
BEGIN;
ALTER TABLE private.acquisition_portal_admission_policy ADD COLUMN bot_hostname text
 CHECK(bot_hostname IS NULL OR (length(bot_hostname)<=253 AND bot_hostname ~ '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'));
ALTER TABLE private.acquisition_portal_admissions ADD COLUMN consumed_at timestamptz,
 ADD COLUMN consumed_receipt_id uuid REFERENCES public.lead_form_submissions(id),
 ADD CONSTRAINT portal_admission_consumed CHECK((consumed_at IS NULL AND consumed_receipt_id IS NULL) OR
  (consumed_at IS NOT NULL AND isfinite(consumed_at) AND consumed_receipt_id IS NOT NULL AND consumed_receipt_id=submission_id AND purpose='submit'));
CREATE TABLE private.acquisition_portal_verifications (
 token_hash text PRIMARY KEY CHECK(token_hash ~ '^[0-9a-f]{64}$'),
 verification_id uuid NOT NULL UNIQUE,
 workspace_id uuid NOT NULL,
 form_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 form_key text NOT NULL,
 submission_id uuid NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 preparation_hash text NOT NULL CHECK(preparation_hash ~ '^[0-9a-f]{64}$'),
 challenged_at timestamptz NOT NULL CHECK(isfinite(challenged_at)),
 verified_at timestamptz NOT NULL CHECK(isfinite(verified_at)),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 CHECK(expires_at=challenged_at+interval '300 seconds'),
 CHECK(verified_at>=challenged_at-interval '5 seconds' AND verified_at<expires_at),
 FOREIGN KEY(form_id,workspace_id,campaign_id,form_key)
 REFERENCES public.lead_form_configs(id,workspace_id,campaign_id,acquisition_form_key)
);
CREATE INDEX portal_verification_expiry ON private.acquisition_portal_verifications(expires_at);
ALTER TABLE private.acquisition_portal_verifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_portal_verifications FROM PUBLIC,anon,authenticated,service_role;
-- Keep the tested transaction as an internal implementation, removing its bypass.
REVOKE ALL ON FUNCTION public.accept_acquisition_online_offer(text,uuid,jsonb),private.accept_acquisition_online_offer(text,uuid,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.complete_acquisition_portal_request(p_attempt uuid,p_prepared jsonb,p_bot jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE admission private.acquisition_portal_admissions%ROWTYPE; policy private.acquisition_portal_admission_policy%ROWTYPE;
 publication private.acquisition_form_publications%ROWTYPE; saved private.acquisition_portal_verifications%ROWTYPE;
 stamped timestamptz; challenged timestamptz; verified timestamptz; expiry timestamptz; verify_id uuid;
 fingerprint text; result jsonb;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'Portal completion unavailable' USING ERRCODE='42501'; END IF;
 IF p_attempt IS NULL OR p_prepared IS NULL OR jsonb_typeof(p_prepared)<>'object' OR octet_length(p_prepared::text)>65536
  OR p_bot IS NULL OR jsonb_typeof(p_bot)<>'object' OR octet_length(p_bot::text)>4096
  OR EXISTS(SELECT 1 FROM jsonb_each(p_bot) e WHERE jsonb_typeof(e.value)<>'string')
  OR p_bot->>'provider' IS DISTINCT FROM 'turnstile' OR p_bot->>'action' IS DISTINCT FROM 'acquisition_offer'
  OR coalesce(p_bot->>'token_hash','') !~ '^[0-9a-f]{64}$'
  OR coalesce(p_bot->>'request_hash','') !~ '^[0-9a-f]{64}$'
  OR coalesce(p_bot->>'challenged_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
  OR coalesce(p_bot->>'verified_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
  OR coalesce(p_bot->>'expires_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
  OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_bot) k WHERE k NOT IN ('provider','action','hostname','submission_id','request_hash','token_hash','verification_id','challenged_at','verified_at','expires_at')) THEN
  RAISE EXCEPTION 'Invalid portal verification' USING ERRCODE='22023'; END IF;
 BEGIN
  challenged:=(p_bot->>'challenged_at')::timestamptz; verified:=(p_bot->>'verified_at')::timestamptz;
  expiry:=(p_bot->>'expires_at')::timestamptz; verify_id:=(p_bot->>'verification_id')::uuid;
 EXCEPTION WHEN data_exception THEN
  RAISE EXCEPTION 'Invalid portal verification' USING ERRCODE='22023'; END;
 IF challenged IS NULL OR verified IS NULL OR expiry IS NULL OR verify_id IS NULL OR NOT isfinite(challenged) OR NOT isfinite(verified) OR NOT isfinite(expiry)
  OR expiry<>challenged+interval '300 seconds' THEN RAISE EXCEPTION 'Invalid portal verification' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('portal-request-admission',0));
 SELECT * INTO policy FROM private.acquisition_portal_admission_policy WHERE singleton FOR SHARE;
 IF NOT FOUND OR NOT policy.enabled OR policy.bot_hostname IS NULL THEN RAISE EXCEPTION 'Portal completion unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO admission FROM private.acquisition_portal_admissions WHERE attempt_id=p_attempt FOR UPDATE;
 IF NOT FOUND OR admission.purpose<>'submit' OR admission.consumed_at IS NOT NULL
  OR admission.policy_revision<>policy.revision OR admission.submission_id::text IS DISTINCT FROM p_prepared->>'submission_id'
  OR admission.submission_id::text IS DISTINCT FROM p_bot->>'submission_id'
  OR admission.request_hash IS DISTINCT FROM p_prepared->>'request_hash' OR admission.request_hash IS DISTINCT FROM p_bot->>'request_hash'
  OR admission.form_key IS DISTINCT FROM p_prepared->>'form_key' OR policy.bot_hostname IS DISTINCT FROM p_bot->>'hostname'
  OR verify_id IS DISTINCT FROM extensions.uuid_generate_v5('32c074f8-362c-4d9a-a84c-1851f32e67b4'::uuid,
    admission.submission_id::text||':'||admission.request_hash||':'||(p_bot->>'token_hash')) THEN
  RAISE EXCEPTION 'Portal admission does not match verification' USING ERRCODE='42501'; END IF;
 PERFORM private.read_acquisition_public_form(admission.form_key);
 SELECT * INTO publication FROM private.acquisition_form_publications WHERE form_key=admission.form_key;
 IF ROW(publication.workspace_id,publication.campaign_id,publication.form_id) IS DISTINCT FROM ROW(admission.workspace_id,admission.campaign_id,admission.form_id) THEN
  RAISE EXCEPTION 'Portal publication changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('form-submission:'||admission.submission_id::text,0));
 stamped:=clock_timestamp();
 IF admission.expires_at<=stamped OR policy.valid_from>stamped OR policy.expires_at<=stamped OR policy.valid_from IS NULL OR policy.expires_at IS NULL
  OR challenged>stamped+interval '5 seconds' OR verified<challenged-interval '5 seconds'
  OR verified<stamped-interval '15 seconds' OR verified>stamped+interval '5 seconds' OR expiry<=stamped OR verified>=expiry THEN
  RAISE EXCEPTION 'Portal verification expired' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(p_prepared::text,'UTF8')),'hex');
 SELECT * INTO saved FROM private.acquisition_portal_verifications WHERE token_hash=p_bot->>'token_hash' FOR UPDATE;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.form_id,saved.submission_id,saved.request_hash,saved.preparation_hash,saved.verification_id,saved.challenged_at,saved.expires_at)
   IS DISTINCT FROM ROW(admission.workspace_id,admission.form_id,admission.submission_id,admission.request_hash,fingerprint,verify_id,challenged,expiry) THEN
   RAISE EXCEPTION 'Verification token already belongs to another inquiry' USING ERRCODE='23505'; END IF;
 ELSE
  INSERT INTO private.acquisition_portal_verifications(token_hash,verification_id,workspace_id,form_id,campaign_id,form_key,submission_id,request_hash,preparation_hash,challenged_at,verified_at,expires_at)
  VALUES(p_bot->>'token_hash',verify_id,admission.workspace_id,admission.form_id,admission.campaign_id,admission.form_key,admission.submission_id,admission.request_hash,fingerprint,challenged,verified,expiry);
 END IF;
 result:=private.accept_acquisition_online_offer(admission.form_key,admission.submission_id,p_prepared);
 -- Any blocking work in the receipt transaction must still finish within authority.
 PERFORM private.read_acquisition_public_form(admission.form_key);
 IF admission.expires_at<=clock_timestamp() OR expiry<=clock_timestamp() OR policy.expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION 'Portal verification expired' USING ERRCODE='42501'; END IF;
 UPDATE private.acquisition_portal_admissions SET consumed_at=clock_timestamp(),consumed_receipt_id=admission.submission_id WHERE attempt_id=p_attempt;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('portal_verified_acceptance',p_attempt::text,'consumed','online_offer_service',
  jsonb_build_object('submission_id',admission.submission_id,'policy_revision',policy.revision,'form_id',admission.form_id,'duplicate',result->'duplicate'),admission.workspace_id);
 RETURN result;
END $$;
CREATE FUNCTION public.complete_acquisition_portal_request(p_attempt uuid,p_prepared jsonb,p_bot jsonb) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.complete_acquisition_portal_request(p_attempt,p_prepared,p_bot) $$;
REVOKE ALL ON FUNCTION public.complete_acquisition_portal_request(uuid,jsonb,jsonb),private.complete_acquisition_portal_request(uuid,jsonb,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.complete_acquisition_portal_request(uuid,jsonb,jsonb),private.complete_acquisition_portal_request(uuid,jsonb,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION private.purge_acquisition_portal_admissions() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE removed integer; tokens integer;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'Portal cleanup unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('portal-request-admission',0));
 DELETE FROM private.acquisition_portal_admissions WHERE retain_until<=clock_timestamp();
 GET DIAGNOSTICS removed=ROW_COUNT;
 DELETE FROM private.acquisition_portal_verifications WHERE expires_at<=clock_timestamp();
 GET DIAGNOSTICS tokens=ROW_COUNT;
 RETURN removed+tokens;
END $$;
COMMIT;
