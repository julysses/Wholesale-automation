-- Proposed forward-only manual CSV repair. Unapplied in production.
-- Never replays source migrations or grants contact permission.
CREATE TABLE private.manual_land_imports (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 operator_id uuid NOT NULL REFERENCES public.profiles(id),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='array'),
 result jsonb NOT NULL CHECK(jsonb_typeof(result)='object')
);
ALTER TABLE private.manual_land_imports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.manual_land_imports FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.manual_land_imports TO service_role;
CREATE FUNCTION private.protect_manual_land_import() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Manual land import receipts are immutable'; END $$;
REVOKE ALL ON FUNCTION private.protect_manual_land_import() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER manual_land_import_immutable BEFORE UPDATE OR DELETE ON private.manual_land_imports
 FOR EACH ROW EXECUTE FUNCTION private.protect_manual_land_import();

CREATE INDEX land_manual_import_identity ON public.land_leads
 (lower(regexp_replace(btrim(property_address),'[[:space:]]+',' ','g')),
  lower(regexp_replace(btrim(city),'[[:space:]]+',' ','g')),upper(coalesce(state,'TX')));

CREATE FUNCTION public.import_manual_land_leads(p_id uuid,p_operator uuid,p_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved private.manual_land_imports; item jsonb; land uuid; task uuid; matches integer;
 imported integer:=0; existing integer:=0; mappings jsonb:='[]';
 address text; city_name text; state_name text; existing_apn text; existing_county text;
BEGIN
 IF p_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator and import reference required' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' OR jsonb_array_length(p_rows) NOT BETWEEN 1 AND 10000
 THEN RAISE EXCEPTION 'Import requires 1 to 10000 rows' USING ERRCODE='22023'; END IF;
 -- Serialize bounded manual imports, including requests with different references.
 -- Existing county handoff identity and its receipts are never rewritten here.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('manual-land-import',0));
 SELECT * INTO saved FROM private.manual_land_imports WHERE id=p_id;
 IF FOUND THEN
   IF saved.operator_id<>p_operator OR saved.payload<>p_rows
   THEN RAISE EXCEPTION 'Import reference conflicts with saved evidence' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('receipt',to_jsonb(saved),'replayed',true,'outreach_authorized',false);
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_rows) LOOP
   IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR
    item-ARRAY['owner_name','property_address','city','state','zip_code','county','apn','external_id',
      'owner_phone_1','owner_phone_2','owner_mailing_address','owner_email','lot_size_acres','lot_size_sqft','tav','zoning_raw'] <> '{}'::jsonb
   THEN RAISE EXCEPTION 'Unsupported land import fields' USING ERRCODE='22023'; END IF;
   IF jsonb_typeof(item->'owner_name') IS DISTINCT FROM 'string' OR coalesce(btrim(item->>'owner_name'),'')='' OR
    jsonb_typeof(item->'property_address') IS DISTINCT FROM 'string' OR coalesce(btrim(item->>'property_address'),'')='' OR
    jsonb_typeof(item->'city') IS DISTINCT FROM 'string' OR coalesce(btrim(item->>'city'),'')=''
   THEN RAISE EXCEPTION 'Owner, property address and verified city required' USING ERRCODE='22023'; END IF;
   address:=lower(regexp_replace(btrim(item->>'property_address'),'[[:space:]]+',' ','g'));
   city_name:=lower(regexp_replace(btrim(item->>'city'),'[[:space:]]+',' ','g'));
   state_name:=upper(coalesce(item->>'state','TX'));
   IF state_name !~ '^[A-Z]{2}$' THEN RAISE EXCEPTION 'Invalid state' USING ERRCODE='22023'; END IF;
   SELECT count(*),(array_agg(id))[1] INTO matches,land FROM public.land_leads
    WHERE lower(regexp_replace(btrim(property_address),'[[:space:]]+',' ','g'))=address
      AND lower(regexp_replace(btrim(city),'[[:space:]]+',' ','g'))=city_name AND upper(coalesce(state,'TX'))=state_name;
   IF matches>1 THEN RAISE EXCEPTION 'Multiple existing land records require review' USING ERRCODE='22023'; END IF;
   task:=NULL;
   IF matches=1 THEN
     SELECT apn,county INTO existing_apn,existing_county FROM public.land_leads WHERE id=land FOR SHARE;
     IF NOT FOUND OR
      (coalesce(btrim(existing_apn),'')<>'' AND coalesce(btrim(item->>'apn'),'')<>'' AND
       regexp_replace(upper(existing_apn),'[^A-Z0-9]','','g')<>regexp_replace(upper(item->>'apn'),'[^A-Z0-9]','','g')) OR
      (coalesce(btrim(existing_county),'')<>'' AND coalesce(btrim(item->>'county'),'')<>'' AND
       lower(btrim(existing_county))<>lower(btrim(item->>'county')))
     THEN RAISE EXCEPTION 'Existing parcel identity requires review' USING ERRCODE='22023'; END IF;
     -- Do not overwrite DNC, owner assignment, contact details, pricing or worked status.
     existing:=existing+1;
   ELSE
     INSERT INTO public.land_leads(source,owner_name,property_address,city,state,zip_code,county,apn,xleads_id,
      owner_phone_1,owner_phone_2,owner_mailing_address,owner_email,lot_size_acres,lot_size_sqft,tav,zoning_raw,
      status,assigned_to,sms_sequence_active)
     VALUES('csv_import',btrim(item->>'owner_name'),btrim(item->>'property_address'),btrim(item->>'city'),state_name,
      item->>'zip_code',item->>'county',item->>'apn',item->>'external_id',item->>'owner_phone_1',item->>'owner_phone_2',
      item->>'owner_mailing_address',item->>'owner_email',(item->>'lot_size_acres')::numeric,
      (item->>'lot_size_sqft')::integer,(item->>'tav')::numeric,item->>'zoning_raw','new',p_operator,false) RETURNING id INTO land;
     task:=gen_random_uuid();
     INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
     VALUES(task,'Review imported land','Land record '||land::text||': '||(item->>'property_address')||', '||(item->>'city')||
      '. Review property and owner evidence. This CSV import grants no contact permission.','pending','medium','follow_up',p_operator,now());
     imported:=imported+1;
   END IF;
   mappings:=mappings||jsonb_build_array(jsonb_build_object('land_lead_id',land,'task_id',task,'created',matches=0));
 END LOOP;
 INSERT INTO private.manual_land_imports(id,operator_id,payload,result)
 VALUES(p_id,p_operator,p_rows,jsonb_build_object('imported',imported,'existing',existing,'rows',mappings)) RETURNING * INTO saved;
 RETURN jsonb_build_object('receipt',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.import_manual_land_leads(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.import_manual_land_leads(uuid,uuid,jsonb) TO service_role;
