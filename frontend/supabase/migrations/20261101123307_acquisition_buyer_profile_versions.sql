-- Versioned operator-entered buyer details. No verified funds, consent,
-- matching, package distribution or transaction authority is conferred.
BEGIN;
CREATE FUNCTION private.valid_acquisition_buyer_details(p jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; value text; maximum integer; item jsonb;
BEGIN
 IF p IS NULL OR jsonb_typeof(p)<>'object' OR NOT (p ?& ARRAY['first_name','last_name','company','email','phone','target_zips','property_types','strategies','min_price_cents','max_price_cents','max_repairs_cents','close_speed_days','active','source_note'])
  OR (SELECT count(*) FROM jsonb_object_keys(p))<>14 THEN RETURN false; END IF;
 FOREACH name IN ARRAY ARRAY['first_name','last_name','company','email','phone','source_note'] LOOP
  IF name IN ('company','email','phone') AND jsonb_typeof(p->name)='null' THEN CONTINUE; END IF;
  IF jsonb_typeof(p->name)<>'string' THEN RETURN false; END IF;
  value:=p->>name;
  maximum:=CASE name WHEN 'company' THEN 160 WHEN 'email' THEN 320 WHEN 'phone' THEN 16 WHEN 'source_note' THEN 2000 ELSE 120 END;
  IF value<>btrim(value) OR value ~ '[[:cntrl:]]' OR length(value) NOT BETWEEN (CASE WHEN name='source_note' THEN 20 ELSE 1 END) AND maximum THEN RETURN false; END IF;
  IF name='phone' AND value !~ '^\+[1-9][0-9]{7,14}$' THEN RETURN false; END IF;
  IF name='email' AND (value<>lower(value) OR value !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$') THEN RETURN false; END IF;
 END LOOP;
 FOREACH name IN ARRAY ARRAY['target_zips','property_types','strategies'] LOOP
  maximum:=CASE name WHEN 'target_zips' THEN 100 WHEN 'property_types' THEN 5 ELSE 6 END;
  IF jsonb_typeof(p->name)<>'array' OR jsonb_array_length(p->name)>maximum THEN RETURN false; END IF;
  IF (SELECT count(*)<>count(DISTINCT v) FROM jsonb_array_elements(p->name) v) THEN RETURN false; END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(p->name) v LOOP
   IF jsonb_typeof(item)<>'string' THEN RETURN false; END IF;
   value:=item#>>'{}';
   IF (name='target_zips' AND value !~ '^[0-9]{5}$') OR
    (name='property_types' AND value<>ALL(ARRAY['SFR','duplex','MFR','land','condo'])) OR
    (name='strategies' AND value<>ALL(ARRAY['fix_flip','buy_hold','brrrr','str','development','wholesale'])) THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 FOREACH name IN ARRAY ARRAY['min_price_cents','max_price_cents','max_repairs_cents','close_speed_days'] LOOP
  IF jsonb_typeof(p->name)='null' THEN CONTINUE; END IF;
  IF jsonb_typeof(p->name)<>'number' OR p->>name !~ '^[0-9]+$' THEN RETURN false; END IF;
  IF name='close_speed_days' THEN
   IF (p->>name)::numeric NOT BETWEEN 1 AND 365 THEN RETURN false; END IF;
  ELSIF (p->>name)::numeric NOT BETWEEN 0 AND 999999999999 THEN RETURN false;
  END IF;
 END LOOP;
 IF jsonb_typeof(p->'active')<>'boolean' THEN RETURN false; END IF;
 IF (p->>'min_price_cents')::numeric>(p->>'max_price_cents')::numeric THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_acquisition_buyer_details(jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE private.acquisition_buyer_versions (
 request_id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 buyer_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0),
 details jsonb NOT NULL CHECK(private.valid_acquisition_buyer_details(details)),
 actor_id uuid NOT NULL,
 session_id uuid NOT NULL,
 actor_membership_updated_at timestamptz NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,buyer_id,revision),
 FOREIGN KEY(buyer_id,workspace_id) REFERENCES public.buyers(id,workspace_id)
);
ALTER TABLE private.acquisition_buyer_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_buyer_versions FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.preserve_acquisition_buyer_versions() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Buyer versions are immutable' USING ERRCODE='42501'; END $$;
REVOKE ALL ON FUNCTION private.preserve_acquisition_buyer_versions() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_buyer_versions_immutable BEFORE UPDATE OR DELETE ON private.acquisition_buyer_versions
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_buyer_versions();

CREATE FUNCTION private.lock_acquisition_buyer_context(p_workspace uuid,p_buyer uuid)
RETURNS TABLE(actor_updated timestamptz,session_expires timestamptz)
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_workspace IS NULL OR p_buyer IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
  OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Buyer workspace authority required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-ref:'||p_buyer::text,0));
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,s.not_after INTO actor_updated,session_expires FROM public.workspace_memberships m
 JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin')
  AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer workspace authority changed' USING ERRCODE='42501'; END IF;
 RETURN NEXT;
END $$;
REVOKE ALL ON FUNCTION private.lock_acquisition_buyer_context(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_acquisition_buyer(p_id uuid,p_workspace uuid,p_buyer uuid,p_expected_revision integer,p_details jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved private.acquisition_buyer_versions%ROWTYPE; buyer public.buyers%ROWTYPE;
 fingerprint text; duplicate boolean:=false; enabled boolean;
BEGIN
 IF p_id IS NULL OR p_expected_revision IS NULL OR p_expected_revision NOT BETWEEN 0 AND 2147483646
  OR NOT private.valid_acquisition_buyer_details(p_details) THEN
  RAISE EXCEPTION 'Exact bounded buyer details required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_acquisition_buyer_context(p_workspace,p_buyer);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-request:'||p_id::text,0));
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Buyer session expired' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_buyer,p_expected_revision,p_details,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 SELECT * INTO saved FROM private.acquisition_buyer_versions WHERE request_id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Buyer request conflict' USING ERRCODE='23505'; END IF;
  duplicate:=true;
 ELSE
  SELECT a.enabled INTO enabled FROM private.acquisition_activation a WHERE singleton FOR SHARE;
  IF enabled IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
  SELECT * INTO buyer FROM public.buyers WHERE id=p_buyer FOR UPDATE;
  IF FOUND THEN
   IF buyer.workspace_id IS DISTINCT FROM p_workspace THEN RAISE EXCEPTION 'Buyer unavailable in this workspace' USING ERRCODE='42501'; END IF;
   IF buyer.acquisition_revision IS DISTINCT FROM p_expected_revision THEN RAISE EXCEPTION 'Buyer revision changed' USING ERRCODE='40001'; END IF;
   IF NOT EXISTS(SELECT 1 FROM private.acquisition_buyer_versions v WHERE v.workspace_id=p_workspace AND v.buyer_id=p_buyer AND v.revision=p_expected_revision) THEN
    RAISE EXCEPTION 'Buyer profile history unavailable' USING ERRCODE='55000'; END IF;
  ELSIF p_expected_revision<>0 THEN RAISE EXCEPTION 'Buyer revision changed' USING ERRCODE='40001';
  END IF;
  IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
   RAISE EXCEPTION 'Buyer session expired before save' USING ERRCODE='42501'; END IF;
  IF buyer.id IS NULL THEN
  INSERT INTO public.buyers(id,workspace_id,acquisition_revision,first_name,last_name,company,email,phone,target_zips,property_types,strategy,
   min_price,max_price,max_repairs,close_speed_days,active,notes,pof_verified,email_opt_in,sms_opt_in)
  VALUES(p_buyer,p_workspace,p_expected_revision+1,p_details->>'first_name',p_details->>'last_name',p_details->>'company',p_details->>'email',p_details->>'phone',
   ARRAY(SELECT jsonb_array_elements_text(p_details->'target_zips')),ARRAY(SELECT jsonb_array_elements_text(p_details->'property_types')),
   ARRAY(SELECT jsonb_array_elements_text(p_details->'strategies')),(p_details->>'min_price_cents')::numeric/100,
   (p_details->>'max_price_cents')::numeric/100,(p_details->>'max_repairs_cents')::numeric/100,(p_details->>'close_speed_days')::integer,
   (p_details->>'active')::boolean,p_details->>'source_note',false,false,false);
  ELSE
   UPDATE public.buyers SET acquisition_revision=p_expected_revision+1,
    first_name=p_details->>'first_name',
    last_name=p_details->>'last_name',
    company=p_details->>'company',
    email=p_details->>'email',
    phone=p_details->>'phone',
    target_zips=ARRAY(SELECT jsonb_array_elements_text(p_details->'target_zips')),
    property_types=ARRAY(SELECT jsonb_array_elements_text(p_details->'property_types')),
    strategy=ARRAY(SELECT jsonb_array_elements_text(p_details->'strategies')),
    min_price=(p_details->>'min_price_cents')::numeric/100,
    max_price=(p_details->>'max_price_cents')::numeric/100,
    max_repairs=(p_details->>'max_repairs_cents')::numeric/100,
    close_speed_days=(p_details->>'close_speed_days')::integer,
    active=(p_details->>'active')::boolean,
    notes=p_details->>'source_note' WHERE id=p_buyer AND workspace_id=p_workspace;
  END IF;
  INSERT INTO private.acquisition_buyer_versions(request_id,workspace_id,buyer_id,revision,details,actor_id,session_id,actor_membership_updated_at,request_hash)
   VALUES(p_id,p_workspace,p_buyer,p_expected_revision+1,p_details,auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,fingerprint)
   RETURNING * INTO saved;
 END IF;
 RETURN jsonb_build_object('request_id',saved.request_id,'workspace_id',saved.workspace_id,'buyer_id',saved.buyer_id,'revision',saved.revision,
  'details',saved.details,'duplicate',duplicate,'profile_recorded',true,'buyer_verified',false,'contact_authorized',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_buyer(uuid,uuid,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_buyer(uuid,uuid,uuid,integer,jsonb) TO authenticated;
CREATE FUNCTION public.record_acquisition_buyer(p_id uuid,p_workspace uuid,p_buyer uuid,p_expected_revision integer,p_details jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_buyer(p_id,p_workspace,p_buyer,p_expected_revision,p_details)
$$;
REVOKE ALL ON FUNCTION public.record_acquisition_buyer(uuid,uuid,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_acquisition_buyer(uuid,uuid,uuid,integer,jsonb) TO authenticated;
COMMIT;
