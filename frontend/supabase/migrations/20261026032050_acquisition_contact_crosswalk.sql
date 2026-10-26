-- Typed endpoint crosswalk over existing CRM/skip-trace observations. No consent
-- or owner verification is inferred and no legacy record is rewritten.
BEGIN;
CREATE TABLE public.acquisition_contact_points (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 type text NOT NULL CHECK(type IN ('phone','email')),
 normalized_value text NOT NULL,
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status='unverified'),
 created_by uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,type,normalized_value),
 CHECK((type='phone' AND normalized_value ~ '^\+[1-9][0-9]{7,14}$') OR
       (type='email' AND normalized_value=lower(trim(normalized_value)) AND
        normalized_value ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' AND length(normalized_value)<=254))
);
CREATE TABLE public.acquisition_contact_observations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 contact_point_id uuid NOT NULL,
 lead_id uuid NOT NULL,
 source_kind text NOT NULL CHECK(source_kind IN ('lead','skip_trace')),
 source_id uuid NOT NULL,
 source_field text NOT NULL,
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 evidence_hash bytea NOT NULL,
 imported_by uuid NOT NULL REFERENCES public.profiles(id),
 imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,contact_point_id) REFERENCES public.acquisition_contact_points(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 UNIQUE(workspace_id,source_kind,source_id,source_field,evidence_hash)
);
-- source_id is intentionally a retained provenance ID, not a foreign key to
-- expiring skip-trace rows. Evidence survives the existing retention procedure.
CREATE INDEX acquisition_contact_observations_lead_idx ON public.acquisition_contact_observations(workspace_id,lead_id,contact_point_id);
CREATE INDEX acquisition_contact_observations_point_idx ON public.acquisition_contact_observations(workspace_id,contact_point_id);
ALTER TABLE public.acquisition_contact_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.acquisition_contact_observations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contact_points,public.acquisition_contact_observations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contact_points,public.acquisition_contact_observations TO authenticated;
CREATE POLICY acquisition_contact_points_read ON public.acquisition_contact_points FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE POLICY acquisition_contact_observations_read ON public.acquisition_contact_observations FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE FUNCTION private.preserve_acquisition_contact() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Contact provenance is append only'; END $$;
REVOKE ALL ON FUNCTION private.preserve_acquisition_contact() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_contact_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contact_points
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE TRIGGER acquisition_contact_observation_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contact_observations
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.acquisition_contact_points
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.acquisition_contact_observations
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();

CREATE FUNCTION private.normalize_acquisition_contact(p_type text,p_value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE v text; digits text;
BEGIN
 v:=trim(p_value);
 IF v IS NULL OR v='' THEN RAISE EXCEPTION 'Contact unavailable' USING ERRCODE='22023'; END IF;
 IF p_type='phone' THEN
  -- Never remove letters/extensions or guess a country for an ambiguous number.
  IF v !~ '^\+?[0-9 ().-]+$' THEN RAISE EXCEPTION 'Ambiguous phone format' USING ERRCODE='22023'; END IF;
  digits:=regexp_replace(v,'[^0-9]','','g');
  IF left(v,1)='+' THEN v:='+'||digits;
  ELSIF length(digits)=10 THEN v:='+1'||digits;
  ELSIF length(digits)=11 AND left(digits,1)='1' THEN v:='+'||digits;
  ELSE RAISE EXCEPTION 'Explicit country code required' USING ERRCODE='22023'; END IF;
  IF v !~ '^\+[1-9][0-9]{7,14}$' THEN RAISE EXCEPTION 'Invalid phone format' USING ERRCODE='22023'; END IF;
 ELSIF p_type='email' THEN
  v:=lower(v);
  IF length(v)>254 OR v !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' THEN
   RAISE EXCEPTION 'Invalid email format' USING ERRCODE='22023'; END IF;
 ELSE RAISE EXCEPTION 'Invalid contact type' USING ERRCODE='22023'; END IF;
 RETURN v;
END $$;
REVOKE ALL ON FUNCTION private.normalize_acquisition_contact(text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.import_acquisition_contact(p_workspace uuid,p_lead uuid,p_source_contact uuid,p_field text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE raw_value text; kind text; v_source_kind text; v_source_id uuid; evidence jsonb;
 endpoint public.acquisition_contact_points%ROWTYPE; observation public.acquisition_contact_observations%ROWTYPE;
 normalized text; digest bytea;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') OR NOT EXISTS(
  SELECT 1 FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=p_lead
 ) THEN RAISE EXCEPTION 'Workspace lead access required' USING ERRCODE='42501'; END IF;
 IF p_source_contact IS NULL THEN
  IF p_field IS NULL OR p_field NOT IN ('owner_phone_1','owner_phone_2','owner_phone_3','owner_email') THEN
   RAISE EXCEPTION 'Invalid source field' USING ERRCODE='22023'; END IF;
  SELECT to_jsonb(l)->>p_field INTO raw_value FROM public.leads l WHERE id=p_lead;
  v_source_kind:='lead'; v_source_id:=p_lead;
  kind:=CASE WHEN p_field='owner_email' THEN 'email' ELSE 'phone' END;
  evidence:=jsonb_build_object('source','public.leads','field',p_field,'raw_value',raw_value,'lead_id',p_lead);
 ELSE
  IF p_field IS NULL OR p_field NOT IN ('phone','email') THEN
   RAISE EXCEPTION 'Invalid source field' USING ERRCODE='22023'; END IF;
  SELECT to_jsonb(c)->>p_field,jsonb_build_object('source','wholesale_ingest.contacts','field',p_field,
   'raw_value',to_jsonb(c)->>p_field,'lead_id',c.lead_id,'provider',c.provider,'traced_at',c.traced_at,
   'expires_at',c.expires_at,'dnc_status',c.dnc_status,'dnc_checked_at',c.dnc_checked_at,
   'trace_request_id',c.trace_request_id,'trace_ordinal',c.trace_ordinal)
  INTO raw_value,evidence FROM wholesale_ingest.contacts c WHERE id=p_source_contact AND lead_id=p_lead;
  IF NOT FOUND THEN RAISE EXCEPTION 'Source contact unavailable' USING ERRCODE='42501'; END IF;
  v_source_kind:='skip_trace'; v_source_id:=p_source_contact; kind:=p_field;
 END IF;
 normalized:=private.normalize_acquisition_contact(kind,raw_value);
 digest:=sha256(convert_to(evidence::text,'UTF8'));
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_workspace::text||':'||kind||':'||normalized,0));
 SELECT * INTO endpoint FROM public.acquisition_contact_points WHERE workspace_id=p_workspace AND type=kind AND normalized_value=normalized;
 IF NOT FOUND THEN
  INSERT INTO public.acquisition_contact_points(workspace_id,type,normalized_value,created_by)
  VALUES(p_workspace,kind,normalized,auth.uid()) RETURNING * INTO endpoint;
 END IF;
 SELECT * INTO observation FROM public.acquisition_contact_observations o WHERE o.workspace_id=p_workspace
  AND o.source_kind=v_source_kind AND o.source_id=v_source_id
  AND o.source_field=p_field AND o.evidence_hash=digest;
 IF NOT FOUND THEN
  INSERT INTO public.acquisition_contact_observations(workspace_id,contact_point_id,lead_id,source_kind,source_id,source_field,evidence,evidence_hash,imported_by)
  VALUES(p_workspace,endpoint.id,p_lead,v_source_kind,v_source_id,p_field,evidence,digest,auth.uid()) RETURNING * INTO observation;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_contact',endpoint.id::text,'source_imported',auth.uid()::text,
   jsonb_build_object('observation_id',observation.id,'lead_id',p_lead,'verification_status','unverified'),p_workspace);
 END IF;
 RETURN jsonb_build_object('contact_point_id',endpoint.id,'observation_id',observation.id,'type',kind,'verification_status','unverified');
END $$;
REVOKE ALL ON FUNCTION private.import_acquisition_contact(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.import_acquisition_contact(uuid,uuid,uuid,text) TO authenticated;
CREATE FUNCTION public.import_acquisition_contact(p_workspace uuid,p_lead uuid,p_source_contact uuid,p_field text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.import_acquisition_contact(p_workspace,p_lead,p_source_contact,p_field) $$;
REVOKE ALL ON FUNCTION public.import_acquisition_contact(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.import_acquisition_contact(uuid,uuid,uuid,text) TO authenticated;
COMMIT;
