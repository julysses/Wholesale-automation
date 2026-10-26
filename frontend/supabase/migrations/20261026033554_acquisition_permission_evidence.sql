-- Structured evidence is not a legal permission decision. No legacy receipt,
-- SMS recovery row or existing provider configuration is changed.
BEGIN;
CREATE TABLE public.acquisition_contact_permissions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL,
 lead_id uuid NOT NULL, contact_point_id uuid NOT NULL,
 channel text NOT NULL CHECK(channel IN ('sms','ai_voice')),
 scope text NOT NULL DEFAULT 'property_inquiry' CHECK(scope='property_inquiry'),
 source_kind text NOT NULL CHECK(source_kind IN ('website','facebook')),
 source_id uuid NOT NULL, source_form_id text,
 selection text NOT NULL CHECK(selection IN ('affirmative','declined','unknown')),
 review_status text NOT NULL DEFAULT 'unreviewed' CHECK(review_status='unreviewed'),
 disclosure_text text, disclosure_version text,
 asserted_at timestamptz, expires_at timestamptz CHECK(expires_at IS NULL),
 expiry_basis text NOT NULL DEFAULT 'not_reviewed' CHECK(expiry_basis='not_reviewed'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'), evidence_hash bytea NOT NULL,
 recorded_by uuid NOT NULL REFERENCES public.profiles(id), recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,source_kind,source_id,channel,evidence_hash),
 FOREIGN KEY(workspace_id,contact_point_id) REFERENCES public.acquisition_contact_points(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 CHECK(selection='unknown' OR (asserted_at IS NOT NULL AND disclosure_text IS NOT NULL AND length(disclosure_text)>0 AND disclosure_version IS NOT NULL))
);
CREATE INDEX acquisition_permissions_contact_idx ON public.acquisition_contact_permissions(workspace_id,contact_point_id,channel,asserted_at DESC);
CREATE TABLE public.acquisition_permission_revocations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, permission_id uuid NOT NULL,
 reason text NOT NULL CHECK(reason IN ('seller_revoked','invalid_evidence','wrong_identity')),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,permission_id),
 FOREIGN KEY(workspace_id,permission_id) REFERENCES public.acquisition_contact_permissions(workspace_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['acquisition_contact_permissions','acquisition_permission_revocations'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('CREATE POLICY acquisition_permission_read ON public.%I FOR SELECT TO authenticated USING(private.acquisition_role(workspace_id) IN (''owner'',''admin'',''operator''))',t);
  EXECUTE format('CREATE TRIGGER acquisition_permission_immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact()',t);
 END LOOP;
END $$;
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.acquisition_contact_permissions
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();
CREATE VIEW public.acquisition_permission_status WITH (security_invoker=true) AS
 SELECT p.*, r.created_at AS revoked_at, r.id AS revocation_id,
  CASE WHEN r.id IS NOT NULL THEN 'revoked' ELSE p.review_status END AS effective_status
 FROM public.acquisition_contact_permissions p LEFT JOIN public.acquisition_permission_revocations r
 ON r.workspace_id=p.workspace_id AND r.permission_id=p.id;
REVOKE ALL ON public.acquisition_permission_status FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_permission_status TO authenticated;

CREATE FUNCTION private.import_acquisition_permission(p_workspace uuid,p_lead uuid,p_contact uuid,p_source_kind text,p_source uuid,p_channel text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE point public.acquisition_contact_points%ROWTYPE; saved public.acquisition_contact_permissions%ROWTYPE;
 answers jsonb; consent jsonb; selected jsonb; form_id text; source_time text; source_phone text;
 occurred timestamptz; disclosure text; version text; selection text:='unknown'; evidence jsonb; digest bytea;
 matches integer; checked jsonb; consistent boolean:=false; field text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') OR
 NOT private.acquisition_can_evaluate(p_workspace,p_lead,p_contact) THEN
  RAISE EXCEPTION 'Workspace contact access required' USING ERRCODE='42501'; END IF;
 IF p_source_kind IS NULL OR p_source_kind NOT IN ('website','facebook') OR p_channel IS NULL OR p_channel NOT IN ('sms','ai_voice')
 OR (p_source_kind='website' AND p_channel<>'sms') THEN
  RAISE EXCEPTION 'Unsupported evidence source/channel' USING ERRCODE='22023'; END IF;
 SELECT * INTO point FROM public.acquisition_contact_points WHERE workspace_id=p_workspace AND id=p_contact;
 IF point.type<>'phone' THEN RAISE EXCEPTION 'Phone evidence required' USING ERRCODE='22023'; END IF;
 IF p_source_kind='website' THEN
  SELECT s.raw_answers,s.form_id::text,s.created_at::text INTO answers,form_id,source_time
  FROM public.lead_form_submissions s WHERE s.id=p_source AND s.lead_id=p_lead;
  IF NOT FOUND THEN RAISE EXCEPTION 'Receipt unavailable' USING ERRCODE='42501'; END IF;
  source_phone:=answers->>'phone'; consent:=answers->'_sms_consent'; selected:=consent;
  disclosure:=consent->>'disclosure';
  consistent:=consent->'rendered_disclosure_matches'='true'::jsonb
   AND consent->>'form_id'=form_id
   AND consent->>'disclosure_sha256'=encode(sha256(convert_to(disclosure,'UTF8')),'hex');
 ELSE
  SELECT raw_answers,s.form_id,s.submitted_at,s.phone_number INTO answers,form_id,source_time,source_phone
  FROM public.facebook_lead_submissions s WHERE s.id=p_source AND s.lead_id=p_lead;
  IF NOT FOUND THEN RAISE EXCEPTION 'Receipt unavailable' USING ERRCODE='42501'; END IF;
  consent:=answers->'_facebook_consent';
  field:=CASE WHEN p_channel='sms' THEN 'sms' ELSE 'ai_calls' END;
  selected:=consent->field; disclosure:=selected->>'disclosure';
  consistent:=consent->>'source'='facebook_native_form' AND consent->'recognized_form'='true'::jsonb
   AND consent->>'form_id'=form_id AND consent->>'submitted_at'=source_time
   AND private.acquisition_try_normalize('phone',consent->>'phone')=point.normalized_value;
  IF jsonb_typeof(consent->'raw_responses')='array' THEN
   SELECT count(*),jsonb_agg(v->'is_checked')->0 INTO matches,checked FROM jsonb_array_elements(consent->'raw_responses') v
    WHERE v->>'checkbox_key'=selected->>'checkbox_key';
   consistent:=consistent AND matches=1 AND selected->>'checkbox_key'=replace(lower(disclosure),' ','_')
    AND ((selected->'accepted'='true'::jsonb AND checked IN ('true'::jsonb,'1'::jsonb,'"1"'::jsonb))
     OR (selected->'accepted'='false'::jsonb AND checked IN ('false'::jsonb,'0'::jsonb,'"0"'::jsonb)));
  ELSE consistent:=false; END IF;
 END IF;
 IF private.acquisition_try_normalize('phone',source_phone) IS DISTINCT FROM point.normalized_value THEN
  RAISE EXCEPTION 'Receipt contact mismatch' USING ERRCODE='22023'; END IF;
 -- Require an explicit time zone. Ambiguous/invalid provider dates remain evidence,
 -- never become a fabricated consent time or the time of this import.
 BEGIN
  IF source_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)$' THEN occurred:=source_time::timestamptz; END IF;
 EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN occurred:=NULL;
 END;
 IF occurred>clock_timestamp() THEN occurred:=NULL; END IF;
 IF disclosure IS NOT NULL AND length(disclosure)>0 THEN version:='sha256:'||encode(sha256(convert_to(disclosure,'UTF8')),'hex'); END IF;
 IF consistent IS TRUE AND occurred IS NOT NULL AND version IS NOT NULL THEN
  IF selected->'accepted'='true'::jsonb THEN selection:='affirmative';
  ELSIF selected->'accepted'='false'::jsonb THEN selection:='declined'; END IF;
 END IF;
 evidence:=jsonb_build_object('source_kind',p_source_kind,'source_id',p_source,'source_form_id',form_id,
  'source_timestamp',source_time,'source_phone',source_phone,'channel',p_channel,'consent',consent,'consistent',coalesce(consistent,false));
 digest:=sha256(convert_to(evidence::text,'UTF8'));
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('permission:'||p_workspace::text||':'||p_source::text||':'||p_channel,0));
 SELECT * INTO saved FROM public.acquisition_contact_permissions p WHERE p.workspace_id=p_workspace AND p.source_kind=p_source_kind
  AND p.source_id=p_source AND p.channel=p_channel AND p.evidence_hash=digest;
 IF NOT FOUND THEN
  INSERT INTO public.acquisition_contact_permissions(workspace_id,lead_id,contact_point_id,channel,source_kind,source_id,source_form_id,
   selection,disclosure_text,disclosure_version,asserted_at,evidence,evidence_hash,recorded_by)
  VALUES(p_workspace,p_lead,p_contact,p_channel,p_source_kind,p_source,form_id,selection,disclosure,version,occurred,evidence,digest,auth.uid()) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('contact_permission',saved.id::text,'evidence_imported',auth.uid()::text,
   jsonb_build_object('source_id',p_source,'channel',p_channel,'selection',selection,'review_status','unreviewed'),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'channel',saved.channel,'scope',saved.scope,'selection',saved.selection,
  'review_status',saved.review_status,'disclosure_version',saved.disclosure_version,'asserted_at',saved.asserted_at,
  'expires_at',saved.expires_at,'expiry_basis',saved.expiry_basis,
  'revoked',EXISTS(SELECT 1 FROM public.acquisition_permission_revocations WHERE workspace_id=p_workspace AND permission_id=saved.id));
END $$;

CREATE FUNCTION private.revoke_acquisition_permission(p_id uuid,p_workspace uuid,p_permission uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE permission public.acquisition_contact_permissions%ROWTYPE; saved public.acquisition_permission_revocations%ROWTYPE;
BEGIN
 SELECT * INTO permission FROM public.acquisition_contact_permissions WHERE workspace_id=p_workspace AND id=p_permission;
 IF NOT FOUND OR NOT private.acquisition_can_evaluate(p_workspace,permission.lead_id,permission.contact_point_id) THEN
  RAISE EXCEPTION 'Workspace permission access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_reason IS NULL OR p_reason NOT IN ('seller_revoked','invalid_evidence','wrong_identity') THEN
  RAISE EXCEPTION 'Revocation identity and reason required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('permission-revoke:'||p_id::text,0));
 SELECT * INTO saved FROM public.acquisition_permission_revocations WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.permission_id<>p_permission OR saved.reason<>p_reason OR saved.actor_id<>auth.uid() THEN
   RAISE EXCEPTION 'Revocation identity conflict' USING ERRCODE='23505'; END IF;
  RETURN to_jsonb(saved);
 END IF;
 INSERT INTO public.acquisition_permission_revocations(id,workspace_id,permission_id,reason,actor_id)
 VALUES(p_id,p_workspace,p_permission,p_reason,auth.uid()) RETURNING * INTO saved;
 PERFORM private.record_acquisition_suppression(p_id,p_workspace,permission.lead_id,permission.contact_point_id,permission.channel,
  CASE WHEN p_reason='seller_revoked' THEN 'seller_opt_out' WHEN p_reason='wrong_identity' THEN 'wrong_number' ELSE 'legal_restriction' END);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('contact_permission',p_permission::text,'revoked',auth.uid()::text,to_jsonb(saved),p_workspace);
 RETURN to_jsonb(saved);
END $$;
REVOKE ALL ON FUNCTION private.import_acquisition_permission(uuid,uuid,uuid,text,uuid,text),
 private.revoke_acquisition_permission(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.import_acquisition_permission(uuid,uuid,uuid,text,uuid,text),
 private.revoke_acquisition_permission(uuid,uuid,uuid,text) TO authenticated;
CREATE FUNCTION public.import_acquisition_permission(p_workspace uuid,p_lead uuid,p_contact uuid,p_source_kind text,p_source uuid,p_channel text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.import_acquisition_permission(p_workspace,p_lead,p_contact,p_source_kind,p_source,p_channel) $$;
CREATE FUNCTION public.revoke_acquisition_permission(p_id uuid,p_workspace uuid,p_permission uuid,p_reason text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.revoke_acquisition_permission(p_id,p_workspace,p_permission,p_reason) $$;
REVOKE ALL ON FUNCTION public.import_acquisition_permission(uuid,uuid,uuid,text,uuid,text),
 public.revoke_acquisition_permission(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.import_acquisition_permission(uuid,uuid,uuid,text,uuid,text),
 public.revoke_acquisition_permission(uuid,uuid,uuid,text) TO authenticated;
COMMIT;
