-- Proposed forward migration, unapplied in production. CSV never grants consent.
-- This transaction is server-only; the operator identity must come from verified Auth.
CREATE FUNCTION private.csv_lead_key(address text, city text, state text)
RETURNS text LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT coalesce((SELECT string_agg(CASE token
   WHEN 'street' THEN 'st' WHEN 'avenue' THEN 'ave' WHEN 'drive' THEN 'dr'
   WHEN 'lane' THEN 'ln' WHEN 'road' THEN 'rd' WHEN 'court' THEN 'ct'
   WHEN 'boulevard' THEN 'blvd' WHEN 'place' THEN 'pl' WHEN 'circle' THEN 'cir'
   WHEN 'trail' THEN 'trl' WHEN 'parkway' THEN 'pkwy' WHEN 'highway' THEN 'hwy'
   WHEN 'terrace' THEN 'ter' WHEN 'square' THEN 'sq' WHEN 'loop' THEN 'lp'
   ELSE token END,' ' ORDER BY position)
 FROM regexp_split_to_table(btrim(regexp_replace(lower(coalesce(address,'')),'[.,#]',' ','g')),
   '[[:space:]]+') WITH ORDINALITY AS words(token,position) WHERE token<>''),'')
 ||'|'||lower(btrim(regexp_replace(coalesce(city,''),'[[:space:]]+',' ','g')))
 ||'|'||upper(regexp_replace(coalesce(nullif(state,''),'TX'),'^[[:space:]]+|[[:space:]]+$','','g'))
$$;
REVOKE ALL ON FUNCTION private.csv_lead_key(text,text,text) FROM PUBLIC,anon,authenticated;
-- This pure immutable normalizer reads no data. Authenticated writers need EXECUTE
-- to maintain the functional index; no import/receipt operation is exposed to them.
GRANT EXECUTE ON FUNCTION private.csv_lead_key(text,text,text) TO service_role,authenticated;
CREATE INDEX leads_csv_import_identity ON public.leads
 (private.csv_lead_key(property_address,city,state));

CREATE TABLE private.csv_lead_imports (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 operator_id uuid NOT NULL REFERENCES public.profiles(id),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='array'),
 options jsonb NOT NULL CHECK(jsonb_typeof(options)='object'),
 result jsonb NOT NULL CHECK(jsonb_typeof(result)='object')
);
ALTER TABLE private.csv_lead_imports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.csv_lead_imports FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.csv_lead_imports TO service_role;
CREATE FUNCTION private.protect_csv_lead_import() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'CSV lead import receipts are immutable'; END $$;
REVOKE ALL ON FUNCTION private.protect_csv_lead_import() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER csv_lead_import_immutable BEFORE UPDATE OR DELETE ON private.csv_lead_imports
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();

-- Durable pending intent, separate from confirmed data. Provider claim/finish is
-- required before wiring optional AI scoring into the API. No provider work here.
CREATE TABLE private.csv_import_scoring (
 import_id uuid PRIMARY KEY REFERENCES private.csv_lead_imports(id),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','submitting','completed','review')),
 lead_ids uuid[] NOT NULL,
 claim_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.csv_import_scoring ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.csv_import_scoring FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON private.csv_import_scoring TO service_role;

CREATE FUNCTION public.import_csv_leads(p_id uuid,p_operator uuid,p_rows jsonb,p_options jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved private.csv_lead_imports; item jsonb; incoming public.leads; previous public.leads;
 owner_id uuid; owner_setting text; lead uuid; task uuid; list_id uuid; matches integer;
 imported integer:=0; existing integer:=0; owner_review integer:=0; mappings jsonb:='[]';
 score_ids uuid[]:='{}'; score_result jsonb; scored integer:=0; scoring_state text;
 identity text; seen text[]:='{}'; field text; source_value text; notes_value text;
BEGIN
 IF p_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator and import reference required' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' OR jsonb_array_length(p_rows) NOT BETWEEN 1 AND 10000
 THEN RAISE EXCEPTION 'Import requires 1 to 10000 normalized rows' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_options) IS DISTINCT FROM 'object' OR
  p_options-ARRAY['score_on_import','engine','list_name','filename']<>'{}'::jsonb OR
  jsonb_typeof(p_options->'score_on_import') IS DISTINCT FROM 'boolean' OR
  coalesce(p_options->>'engine','') NOT IN ('rules','ai') OR
  (p_options ? 'list_name' AND jsonb_typeof(p_options->'list_name') NOT IN ('string','null')) OR
  (p_options ? 'filename' AND jsonb_typeof(p_options->'filename') NOT IN ('string','null'))
 THEN RAISE EXCEPTION 'Invalid import options' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('manual-lead-import',0));
 SELECT * INTO saved FROM private.csv_lead_imports WHERE id=p_id;
 IF FOUND THEN
  IF saved.operator_id<>p_operator OR saved.payload<>p_rows OR saved.options<>p_options
  THEN RAISE EXCEPTION 'Import reference conflicts with saved evidence' USING ERRCODE='22023'; END IF;
  RETURN jsonb_build_object('receipt',to_jsonb(saved),'replayed',true,'outreach_authorized',false);
 END IF;
 SELECT value INTO owner_setting FROM public.app_settings WHERE key='lead_owner_user_id';
 IF coalesce(owner_setting,'') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
 THEN RAISE EXCEPTION 'Approved intake owner must be configured' USING ERRCODE='22023'; END IF;
 owner_id:=owner_setting::uuid;
 PERFORM 1 FROM public.profiles WHERE id=owner_id AND status='approved' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Configured intake owner is not approved' USING ERRCODE='22023'; END IF;
 IF coalesce(btrim(p_options->>'list_name'),'')<>'' THEN
  INSERT INTO public.lead_lists(name,filename,row_count)
  VALUES(left(btrim(p_options->>'list_name'),120),nullif(left(p_options->>'filename',200),''),jsonb_array_length(p_rows))
  RETURNING id INTO list_id;
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_rows) LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR item-ARRAY[
   'property_address','city','state','zip_code','owner_first_name','owner_last_name',
   'owner_phone_1','owner_phone_2','owner_phone_3','owner_email','owner_mailing_address',
   'property_type','bedrooms','bathrooms','sqft','year_built','asking_price','source','status',
   'motivation_tag','seller_notes','internal_notes']<>'{}'::jsonb
  THEN RAISE EXCEPTION 'Unsupported CSV import fields' USING ERRCODE='22023'; END IF;
  FOR field IN SELECT jsonb_object_keys(item) LOOP
   IF item->field<>'null'::jsonb THEN
    IF field IN ('bedrooms','bathrooms','sqft','year_built','asking_price') THEN
     IF jsonb_typeof(item->field)<>'number' OR (item->>field)::numeric<0 OR
      (field IN ('bedrooms','sqft','year_built') AND (item->>field)::numeric<>trunc((item->>field)::numeric))
     THEN RAISE EXCEPTION 'Invalid numeric import field' USING ERRCODE='22023'; END IF;
    ELSIF jsonb_typeof(item->field)<>'string' THEN
     RAISE EXCEPTION 'Import text fields must be strings' USING ERRCODE='22023';
    END IF;
   END IF;
  END LOOP;
  incoming:=jsonb_populate_record(NULL::public.leads,item);
  IF coalesce(btrim(incoming.property_address),'')='' OR coalesce(btrim(incoming.city),'')=''
  THEN RAISE EXCEPTION 'Property address and verified city required' USING ERRCODE='22023'; END IF;
  incoming.state:=upper(coalesce(nullif(btrim(incoming.state),''),'TX'));
  IF incoming.state !~ '^[A-Z]{2}$' THEN RAISE EXCEPTION 'Invalid state' USING ERRCODE='22023'; END IF;
  identity:=private.csv_lead_key(incoming.property_address,incoming.city,incoming.state);
  IF identity=ANY(seen) THEN RAISE EXCEPTION 'Consolidate repeated property identities before import' USING ERRCODE='22023'; END IF;
  seen:=array_append(seen,identity);
  SELECT count(*),(array_agg(id))[1] INTO matches,lead FROM public.leads
   WHERE private.csv_lead_key(property_address,city,state)=identity;
  IF matches>1 THEN RAISE EXCEPTION 'Multiple existing properties require review' USING ERRCODE='22023'; END IF;
  task:=NULL;
  IF matches=1 THEN
   SELECT * INTO previous FROM public.leads WHERE id=lead FOR UPDATE;
   IF NOT FOUND OR private.csv_lead_key(previous.property_address,previous.city,previous.state)<>identity
   THEN RAISE EXCEPTION 'Property changed during import; retry original reference' USING ERRCODE='40001'; END IF;
   source_value:=previous.source;
   IF coalesce(btrim(incoming.source),'')<>'' THEN
   SELECT left(string_agg(token,' | ' ORDER BY ordinal),250) INTO source_value FROM (
    SELECT btrim(value) token,min(ordinal) ordinal
    FROM unnest(string_to_array(coalesce(previous.source,'')||'|'||coalesce(incoming.source,''),'|'))
     WITH ORDINALITY parts(value,ordinal) WHERE btrim(value)<>'' GROUP BY btrim(value)) ordered;
   END IF;
   notes_value:=CASE WHEN coalesce(incoming.internal_notes,'')='' THEN previous.internal_notes
    WHEN coalesce(previous.internal_notes,'')='' THEN incoming.internal_notes
    WHEN coalesce(incoming.internal_notes,'')='' OR strpos(previous.internal_notes,incoming.internal_notes)>0 THEN previous.internal_notes
    ELSE previous.internal_notes||E'\n'||incoming.internal_notes END;
   -- Match historical fill-blank semantics. Status, consent, assignment, sequences,
   -- contact attempts, scores, existing list membership and completed tasks survive.
   incoming:=jsonb_populate_record(previous,(SELECT coalesce(jsonb_object_agg(key,value),'{}') FROM jsonb_each(item)
    WHERE key NOT IN ('status','source','internal_notes') AND value<>'null'::jsonb AND value<>'""'::jsonb
     AND (to_jsonb(previous)->key IS NULL OR to_jsonb(previous)->key IN ('null'::jsonb,'""'::jsonb))));
   UPDATE public.leads SET property_address=incoming.property_address,city=incoming.city,state=incoming.state,
    zip_code=incoming.zip_code,owner_first_name=incoming.owner_first_name,owner_last_name=incoming.owner_last_name,
    owner_phone_1=incoming.owner_phone_1,owner_phone_2=incoming.owner_phone_2,owner_phone_3=incoming.owner_phone_3,
    owner_email=incoming.owner_email,owner_mailing_address=incoming.owner_mailing_address,
    property_type=incoming.property_type,bedrooms=incoming.bedrooms,bathrooms=incoming.bathrooms,sqft=incoming.sqft,
    year_built=incoming.year_built,asking_price=incoming.asking_price,source=source_value,
    motivation_tag=incoming.motivation_tag,seller_notes=incoming.seller_notes,internal_notes=notes_value
   WHERE id=lead AND (to_jsonb(previous)-ARRAY['updated_at']) IS DISTINCT FROM
    ((to_jsonb(incoming)||jsonb_build_object('source',source_value,'internal_notes',notes_value))-ARRAY['updated_at']);
   existing:=existing+1;
   IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=previous.assigned_to AND status='approved')
   THEN owner_review:=owner_review+1; END IF;
  ELSE
   INSERT INTO public.leads(property_address,city,state,zip_code,owner_first_name,owner_last_name,
    owner_phone_1,owner_phone_2,owner_phone_3,owner_email,owner_mailing_address,property_type,
    bedrooms,bathrooms,sqft,year_built,asking_price,source,status,motivation_tag,seller_notes,internal_notes,
    list_id,assigned_to,ai_calling_paused,sms_sequence_active,email_sequence_active)
   VALUES(btrim(incoming.property_address),btrim(incoming.city),incoming.state,incoming.zip_code,
    incoming.owner_first_name,incoming.owner_last_name,incoming.owner_phone_1,incoming.owner_phone_2,incoming.owner_phone_3,
    incoming.owner_email,incoming.owner_mailing_address,incoming.property_type,incoming.bedrooms,incoming.bathrooms,
    incoming.sqft,incoming.year_built,incoming.asking_price,coalesce(nullif(incoming.source,''),'csv_import'),
    coalesce(nullif(incoming.status,''),'new'),incoming.motivation_tag,incoming.seller_notes,incoming.internal_notes,
    list_id,owner_id,true,false,false) RETURNING id INTO lead;
   INSERT INTO public.tasks(title,description,status,priority,type,lead_id,assigned_to,due_date)
   VALUES('Review imported lead','Review property and owner evidence. This CSV import grants no contact permission.',
    'pending','medium','follow_up',lead,owner_id,now()) RETURNING id INTO task;
   imported:=imported+1;
  END IF;
  -- Only untouched, unscored, unsuppressed records qualify for automatic scoring.
  IF EXISTS(SELECT 1 FROM public.leads l WHERE l.id=lead AND NOT coalesce(l.dnc,false)
   AND coalesce(l.contact_attempts,0)=0 AND coalesce(l.status,'new') IN ('new','scoring_error')
   AND l.score_motivation IS NULL AND l.score_timeline IS NULL AND l.score_equity IS NULL
   AND l.score_condition IS NULL AND l.score_flexibility IS NULL AND nullif(l.ai_qualification_summary,'') IS NULL
   AND NOT EXISTS(SELECT 1 FROM public.tasks t WHERE t.lead_id=l.id AND (t.status='completed' OR t.completed_at IS NOT NULL))
   AND NOT EXISTS(SELECT 1 FROM private.csv_import_scoring s WHERE l.id=ANY(s.lead_ids)))
  THEN score_ids:=array_append(score_ids,lead); END IF;
  mappings:=mappings||jsonb_build_array(jsonb_build_object('lead_id',lead,'task_id',task,'created',matches=0));
 END LOOP;
 scoring_state:=CASE WHEN NOT (p_options->>'score_on_import')::boolean THEN 'disabled'
  WHEN p_options->>'engine'='rules' THEN 'completed' ELSE 'pending' END;
 IF scoring_state='completed' AND cardinality(score_ids)>0 THEN
  score_result:=public.score_leads_rules(score_ids,NULL,false,true);
  scored:=(score_result->>'scored')::integer;
 END IF;
 INSERT INTO private.csv_lead_imports(id,operator_id,payload,options,result)
 VALUES(p_id,p_operator,p_rows,p_options,jsonb_build_object('imported',imported,'existing',existing,
  'owner_review',owner_review,'intake_owner_id',owner_id,'rows',mappings,'list_id',list_id,'scored',scored,'scoring_state',scoring_state)) RETURNING * INTO saved;
 IF scoring_state='pending' THEN
  INSERT INTO private.csv_import_scoring(import_id,lead_ids) VALUES(p_id,score_ids);
 END IF;
 RETURN jsonb_build_object('receipt',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.import_csv_leads(uuid,uuid,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.import_csv_leads(uuid,uuid,jsonb,jsonb) TO service_role;
