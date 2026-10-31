-- Disabled operational admission. No public route, bot verification or lead write.
BEGIN;
CREATE TABLE private.acquisition_portal_admission_policy (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 global_per_minute integer NOT NULL DEFAULT 60 CHECK(global_per_minute BETWEEN 1 AND 1000),
 form_per_minute integer NOT NULL DEFAULT 20 CHECK(form_per_minute BETWEEN 1 AND 500),
 network_per_minute integer NOT NULL DEFAULT 5 CHECK(network_per_minute BETWEEN 1 AND 20),
 approval_ref text,
 valid_from timestamptz,
 expires_at timestamptz,
 CHECK(NOT enabled OR (approval_ref IS NOT NULL AND length(trim(approval_ref)) BETWEEN 1 AND 2000
  AND valid_from IS NOT NULL AND expires_at IS NOT NULL AND isfinite(valid_from) AND isfinite(expires_at)
  AND expires_at>valid_from AND expires_at<=valid_from+interval '90 days'))
);
CREATE TABLE private.acquisition_portal_admissions (
 attempt_id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 form_id uuid NOT NULL,
 form_key text NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('display','submit')),
 submission_id uuid,
 request_hash text,
 network_hash text NOT NULL CHECK(network_hash ~ '^[0-9a-f]{64}$'),
 policy_revision integer NOT NULL CHECK(policy_revision>0),
 checked_at timestamptz NOT NULL CHECK(isfinite(checked_at)),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 retain_until timestamptz NOT NULL CHECK(isfinite(retain_until)),
 CHECK(expires_at=checked_at+interval '30 seconds'),
 CHECK(retain_until=checked_at+interval '5 minutes'),
 CHECK((purpose='display' AND submission_id IS NULL AND request_hash IS NULL) OR
  (purpose='submit' AND submission_id IS NOT NULL AND request_hash IS NOT NULL AND request_hash ~ '^[0-9a-f]{64}$')),
 FOREIGN KEY(form_id,workspace_id,campaign_id,form_key)
 REFERENCES public.lead_form_configs(id,workspace_id,campaign_id,acquisition_form_key)
);
CREATE INDEX portal_admission_window ON private.acquisition_portal_admissions(checked_at);
CREATE INDEX portal_admission_retention ON private.acquisition_portal_admissions(retain_until);
CREATE TABLE private.acquisition_portal_admission_totals (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 denied_total bigint NOT NULL DEFAULT 0 CHECK(denied_total BETWEEN 0 AND 1000000000000),
 last_denied_at timestamptz
);
ALTER TABLE private.acquisition_portal_admission_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE private.acquisition_portal_admissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE private.acquisition_portal_admission_totals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_portal_admission_policy,private.acquisition_portal_admissions,private.acquisition_portal_admission_totals
 FROM PUBLIC,anon,authenticated,service_role;

-- Global operational policy audit is not a tenant-owned inquiry record.
CREATE POLICY portal_admission_audit_private ON public.audit_logs AS RESTRICTIVE FOR SELECT TO authenticated
 USING(entity_type IS DISTINCT FROM 'portal_admission_policy');
CREATE FUNCTION private.preserve_portal_admission_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF OLD.entity_type='portal_admission_policy' OR (TG_OP='UPDATE' AND NEW.entity_type='portal_admission_policy') THEN
  RAISE EXCEPTION 'Portal policy audit is immutable' USING ERRCODE='42501'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.preserve_portal_admission_audit() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER preserve_portal_admission_audit BEFORE UPDATE OR DELETE ON public.audit_logs
 FOR EACH ROW EXECUTE FUNCTION private.preserve_portal_admission_audit();

CREATE FUNCTION private.audit_portal_admission_policy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Disable admission policy instead of deleting it' USING ERRCODE='42501'; END IF;
 IF TG_OP='UPDATE' THEN NEW.revision:=OLD.revision+1; END IF;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,old_value,new_value)
 VALUES('portal_admission_policy','singleton',lower(TG_OP),session_user,
 CASE WHEN TG_OP='INSERT' THEN NULL ELSE to_jsonb(OLD) END,to_jsonb(NEW));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_portal_admission_policy() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER portal_admission_policy_audit BEFORE INSERT OR UPDATE OR DELETE ON private.acquisition_portal_admission_policy
 FOR EACH ROW EXECUTE FUNCTION private.audit_portal_admission_policy();
INSERT INTO private.acquisition_portal_admission_policy(singleton) VALUES(true);
INSERT INTO private.acquisition_portal_admission_totals(singleton) VALUES(true);

CREATE FUNCTION private.admit_acquisition_portal_request(p_attempt uuid,p_form_key text,p_network_hash text,p_purpose text,p_submission uuid,p_request_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE policy private.acquisition_portal_admission_policy%ROWTYPE; publication private.acquisition_form_publications%ROWTYPE;
 stamped timestamptz; all_count integer; form_count integer; network_count integer; retry_at timestamptz; retry_seconds integer;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'Portal admission unavailable' USING ERRCODE='42501'; END IF;
 IF p_attempt IS NULL OR p_form_key IS NULL OR p_form_key !~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$'
  OR p_network_hash IS NULL OR p_network_hash !~ '^[0-9a-f]{64}$' OR p_purpose IS NULL OR p_purpose NOT IN ('display','submit')
  OR (p_purpose='display' AND (p_submission IS NOT NULL OR p_request_hash IS NOT NULL))
  OR (p_purpose='submit' AND (p_submission IS NULL OR p_request_hash IS NULL OR p_request_hash !~ '^[0-9a-f]{64}$')) THEN
  RAISE EXCEPTION 'Invalid portal admission identity' USING ERRCODE='22023'; END IF;
 -- One global rolling-window lock bounds races and state growth across instances.
 PERFORM pg_advisory_xact_lock(hashtextextended('portal-request-admission',0));
 SELECT * INTO policy FROM private.acquisition_portal_admission_policy WHERE singleton FOR SHARE;
 IF NOT FOUND OR NOT policy.enabled THEN RAISE EXCEPTION 'Portal admission unavailable' USING ERRCODE='42501'; END IF;
 PERFORM private.read_acquisition_public_form(p_form_key);
 SELECT * INTO publication FROM private.acquisition_form_publications WHERE form_key=p_form_key;
 stamped:=clock_timestamp();
 IF policy.valid_from IS NULL OR policy.expires_at IS NULL OR policy.valid_from>stamped OR policy.expires_at<=stamped THEN
  RAISE EXCEPTION 'Portal admission unavailable' USING ERRCODE='42501'; END IF;
 -- Opportunistic retention is bounded by the maximum admissions over five minutes.
 DELETE FROM private.acquisition_portal_admissions WHERE retain_until<=stamped;
 IF EXISTS(SELECT 1 FROM private.acquisition_portal_admissions WHERE attempt_id=p_attempt) THEN
  RAISE EXCEPTION 'Fresh portal attempt required' USING ERRCODE='23505'; END IF;
 SELECT count(*),count(*) FILTER(WHERE form_key=p_form_key),count(*) FILTER(WHERE network_hash=p_network_hash)
 INTO all_count,form_count,network_count FROM private.acquisition_portal_admissions WHERE checked_at>stamped-interval '60 seconds';
 IF all_count>=policy.global_per_minute OR form_count>=policy.form_per_minute OR network_count>=policy.network_per_minute THEN
  SELECT min(checked_at)+interval '60 seconds' INTO retry_at FROM private.acquisition_portal_admissions
   WHERE checked_at>stamped-interval '60 seconds' AND
    (all_count>=policy.global_per_minute OR (form_count>=policy.form_per_minute AND form_key=p_form_key)
     OR (network_count>=policy.network_per_minute AND network_hash=p_network_hash));
  retry_seconds:=greatest(1,least(60,ceil(extract(epoch FROM retry_at-stamped))::integer));
  UPDATE private.acquisition_portal_admission_totals SET denied_total=least(denied_total+1,1000000000000),last_denied_at=stamped WHERE singleton;
  -- Return, do not raise: the operational denial counter must commit.
  RETURN jsonb_build_object('attempt_id',p_attempt,'form_key',p_form_key,'purpose',p_purpose,'admitted',false,
   'checked_at',stamped,'expires_at',NULL,'retry_after_seconds',retry_seconds,'policy_revision',policy.revision);
 END IF;
 INSERT INTO private.acquisition_portal_admissions(attempt_id,workspace_id,campaign_id,form_id,form_key,purpose,submission_id,request_hash,network_hash,policy_revision,checked_at,expires_at,retain_until)
 VALUES(p_attempt,publication.workspace_id,publication.campaign_id,publication.form_id,p_form_key,p_purpose,p_submission,p_request_hash,p_network_hash,policy.revision,stamped,stamped+interval '30 seconds',stamped+interval '5 minutes');
 RETURN jsonb_build_object('attempt_id',p_attempt,'form_key',p_form_key,'purpose',p_purpose,'admitted',true,
  'checked_at',stamped,'expires_at',stamped+interval '30 seconds','retry_after_seconds',0,'policy_revision',policy.revision);
END $$;
CREATE FUNCTION public.admit_acquisition_portal_request(p_attempt uuid,p_form_key text,p_network_hash text,p_purpose text,p_submission uuid,p_request_hash text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.admit_acquisition_portal_request(p_attempt,p_form_key,p_network_hash,p_purpose,p_submission,p_request_hash) $$;
REVOKE ALL ON FUNCTION private.admit_acquisition_portal_request(uuid,text,text,text,uuid,text),public.admit_acquisition_portal_request(uuid,text,text,text,uuid,text)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.admit_acquisition_portal_request(uuid,text,text,text,uuid,text),public.admit_acquisition_portal_request(uuid,text,text,text,uuid,text) TO service_role;

-- Explicit cleanup also works while disabled; no scheduler is activated here.
CREATE FUNCTION private.purge_acquisition_portal_admissions() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE removed integer;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'Portal cleanup unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('portal-request-admission',0));
 DELETE FROM private.acquisition_portal_admissions WHERE retain_until<=clock_timestamp();
 GET DIAGNOSTICS removed=ROW_COUNT; RETURN removed;
END $$;
CREATE FUNCTION public.purge_acquisition_portal_admissions() RETURNS integer
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.purge_acquisition_portal_admissions() $$;
REVOKE ALL ON FUNCTION private.purge_acquisition_portal_admissions(),public.purge_acquisition_portal_admissions() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.purge_acquisition_portal_admissions(),public.purge_acquisition_portal_admissions() TO service_role;
COMMIT;
