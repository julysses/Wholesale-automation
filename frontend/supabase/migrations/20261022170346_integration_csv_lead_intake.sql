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

-- Durable intent and one-way provider claims, separate from confirmed data.
-- PostgreSQL never calls a provider. Unknown attempts stay held for review.
CREATE TABLE private.csv_import_scoring (
 import_id uuid PRIMARY KEY REFERENCES private.csv_lead_imports(id),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','submitting','completed','review')),
 lead_ids uuid[] NOT NULL,
 claim_id uuid,
 snapshots jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(snapshots)='array'),
 scores jsonb,
 result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX csv_scoring_lead_reservations ON private.csv_import_scoring USING gin(lead_ids);
ALTER TABLE private.csv_import_scoring ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.csv_import_scoring FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON private.csv_import_scoring TO service_role;


CREATE TABLE private.csv_import_scoring_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 import_id uuid NOT NULL REFERENCES private.csv_lead_imports(id),
 batch_index integer NOT NULL,
 lead_ids uuid[] NOT NULL CHECK(cardinality(lead_ids) BETWEEN 1 AND 25),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','submitting','completed','review')),
 claim_id uuid UNIQUE,
 snapshots jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(snapshots)='array'),
 scores jsonb,
 result jsonb,
 response jsonb,
 halt boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(import_id,batch_index)
);
ALTER TABLE private.csv_import_scoring_batches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.csv_import_scoring_batches FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON private.csv_import_scoring_batches TO service_role;
CREATE FUNCTION private.protect_csv_scoring_batch() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Scoring batch evidence cannot be deleted'; END IF;
 IF OLD.state IN ('completed','review') OR
  (NEW.id,NEW.import_id,NEW.batch_index,NEW.lead_ids,NEW.created_at) IS DISTINCT FROM
  (OLD.id,OLD.import_id,OLD.batch_index,OLD.lead_ids,OLD.created_at) OR
  (OLD.state='submitting' AND (NEW.claim_id,NEW.snapshots) IS DISTINCT FROM (OLD.claim_id,OLD.snapshots))
 THEN RAISE EXCEPTION 'Scoring batch evidence is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_csv_scoring_batch() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER csv_scoring_batch_evidence BEFORE UPDATE OR DELETE ON private.csv_import_scoring_batches
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_scoring_batch();

CREATE FUNCTION private.csv_scoring_summary(p_id uuid) RETURNS jsonb
LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path='' AS $$
 WITH totals AS (
  SELECT coalesce(sum((result->>'scored')::integer) FILTER(WHERE state IN ('completed','review')),0)::integer scored,
   coalesce(sum((result->>'held')::integer) FILTER(WHERE state IN ('completed','review')),0)::integer held,
   coalesce(sum(cardinality(lead_ids)) FILTER(WHERE state='pending'),0)::integer remaining,
   coalesce(sum(cardinality(lead_ids)) FILTER(WHERE state='submitting'),0)::integer in_flight,
   coalesce(bool_or(halt),false) halted
  FROM private.csv_import_scoring_batches WHERE import_id=p_id
 ) SELECT jsonb_build_object('state',CASE WHEN in_flight>0 THEN 'submitting' WHEN halted THEN 'review'
  WHEN remaining>0 THEN 'pending' WHEN held>0 THEN 'review' ELSE 'completed' END,
  'result',jsonb_build_object('scored',scored,'held',held,'remaining',remaining,'in_flight',in_flight)) FROM totals
$$;
REVOKE ALL ON FUNCTION private.csv_scoring_summary(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.csv_scoring_summary(uuid) TO service_role;

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
   AND NOT EXISTS(SELECT 1 FROM private.csv_import_scoring s WHERE s.lead_ids @> ARRAY[l.id]))
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
  'owner_review',owner_review,'intake_owner_id',owner_id,'rows',mappings,'list_id',list_id,'scored',scored,'scoring_eligible',cardinality(score_ids),'scoring_state',scoring_state)) RETURNING * INTO saved;
 IF scoring_state='pending' THEN
  INSERT INTO private.csv_import_scoring(import_id,lead_ids,state,result) VALUES(p_id,score_ids,
   CASE WHEN cardinality(score_ids)=0 THEN 'completed' ELSE 'pending' END,
   jsonb_build_object('scored',0,'held',0,'remaining',cardinality(score_ids),'in_flight',0));
  INSERT INTO private.csv_import_scoring_batches(import_id,batch_index,lead_ids)
   SELECT p_id,((ordinal-1)/25)::integer,array_agg(lead_id ORDER BY ordinal)
   FROM unnest(score_ids) WITH ORDINALITY ids(lead_id,ordinal) GROUP BY ((ordinal-1)/25)::integer;
 END IF;
 RETURN jsonb_build_object('receipt',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.import_csv_leads(uuid,uuid,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.import_csv_leads(uuid,uuid,jsonb,jsonb) TO service_role;

CREATE FUNCTION public.claim_csv_import_scoring(p_id uuid,p_operator uuid,p_claim uuid,p_initial_only boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE parent private.csv_import_scoring; operation private.csv_import_scoring_batches;
 receipt private.csv_lead_imports; candidate public.leads; v_snapshots jsonb:='[]'; summary jsonb; no_dispatch_reply jsonb;
BEGIN
 IF p_claim IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator and claim reference required' USING ERRCODE='22023'; END IF;
 SELECT * INTO receipt FROM private.csv_lead_imports WHERE id=p_id;
 IF NOT FOUND OR receipt.operator_id<>p_operator OR receipt.options->>'engine'<>'ai'
  OR receipt.options->>'score_on_import'<>'true'
 THEN RAISE EXCEPTION 'Scoring intent does not match operator/import' USING ERRCODE='22023'; END IF;
 SELECT * INTO parent FROM private.csv_import_scoring WHERE import_id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Scoring intent missing' USING ERRCODE='22023'; END IF;
 summary:=private.csv_scoring_summary(p_id);
 IF summary->>'state'<>'pending' OR EXISTS(SELECT 1 FROM private.csv_import_scoring_batches WHERE claim_id=p_claim)
  OR (p_initial_only AND EXISTS(SELECT 1 FROM private.csv_import_scoring_batches WHERE import_id=p_id AND claim_id IS NOT NULL)) THEN
  RETURN jsonb_build_object('import_id',p_id,'operator_id',p_operator,'claimed',false,
   'claim_id',parent.claim_id,'state',summary->>'state','result',summary->'result');
 END IF;
 SELECT * INTO operation FROM private.csv_import_scoring_batches
  WHERE import_id=p_id AND state='pending' ORDER BY batch_index LIMIT 1 FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Pending scoring batch missing' USING ERRCODE='22023'; END IF;
 FOR candidate IN SELECT * FROM public.leads WHERE id=ANY(operation.lead_ids) ORDER BY id FOR UPDATE LOOP
  PERFORM 1 FROM public.tasks WHERE lead_id=candidate.id FOR SHARE;
  IF NOT coalesce(candidate.dnc,false) AND coalesce(candidate.contact_attempts,0)=0
   AND coalesce(candidate.status,'new') IN ('new','scoring_error')
   AND candidate.score_motivation IS NULL AND candidate.score_timeline IS NULL
   AND candidate.score_equity IS NULL AND candidate.score_condition IS NULL AND candidate.score_flexibility IS NULL
   AND nullif(candidate.ai_qualification_summary,'') IS NULL
   AND NOT EXISTS(SELECT 1 FROM public.tasks WHERE lead_id=candidate.id AND (status='completed' OR completed_at IS NOT NULL))
  THEN
   v_snapshots:=v_snapshots||jsonb_build_array(to_jsonb(candidate)-ARRAY[
    'updated_at','priority_rank','retention_rule','retention_action','retention_due_at','retention_deletable','retention_reason']);
  END IF;
 END LOOP;
 IF jsonb_array_length(v_snapshots)=0 THEN
  no_dispatch_reply:=jsonb_build_object('import_id',p_id,'operator_id',p_operator,'claim_id',p_claim,'batch_id',operation.id,
   'state',CASE WHEN (summary->'result'->>'remaining')::integer>cardinality(operation.lead_ids) THEN 'pending' ELSE 'review' END,
   'result',jsonb_build_object('scored',(summary->'result'->>'scored')::integer,
    'held',(summary->'result'->>'held')::integer+cardinality(operation.lead_ids),
    'remaining',(summary->'result'->>'remaining')::integer-cardinality(operation.lead_ids),'in_flight',0));
 END IF;
 UPDATE private.csv_import_scoring_batches SET claim_id=p_claim,snapshots=v_snapshots,
  state=CASE WHEN jsonb_array_length(v_snapshots)>0 THEN 'submitting' ELSE 'review' END,
  result=CASE WHEN jsonb_array_length(v_snapshots)>0 THEN NULL
   ELSE jsonb_build_object('scored',0,'held',cardinality(lead_ids)) END, response=no_dispatch_reply
  WHERE id=operation.id RETURNING * INTO operation;
 summary:=private.csv_scoring_summary(p_id);
 UPDATE private.csv_import_scoring SET claim_id=p_claim,snapshots=v_snapshots,
  state=summary->>'state',result=summary->'result',updated_at=now() WHERE import_id=p_id;
 RETURN jsonb_build_object('import_id',p_id,'operator_id',p_operator,'claimed',operation.state='submitting',
  'claim_id',p_claim,'state',summary->>'state','snapshots',v_snapshots,
  'batch_id',operation.id,'batch_lead_ids',to_jsonb(operation.lead_ids),'result',summary->'result');
END $$;
REVOKE ALL ON FUNCTION public.claim_csv_import_scoring(uuid,uuid,uuid,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_csv_import_scoring(uuid,uuid,uuid,boolean) TO service_role;

CREATE FUNCTION public.finish_csv_import_scoring(p_id uuid,p_operator uuid,p_claim uuid,p_scores jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE operation private.csv_import_scoring_batches; receipt private.csv_lead_imports; summary jsonb; reply jsonb;
 snapshot jsonb; current_row public.leads; assessment jsonb; field text;
 valid boolean:=true; expected_ids text[]; received_ids text[]; total integer; tier text;
 scored integer:=0; applied uuid[]:='{}';
BEGIN
 IF p_claim IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator and claim reference required' USING ERRCODE='22023'; END IF;
 SELECT * INTO receipt FROM private.csv_lead_imports WHERE id=p_id;
 IF NOT FOUND OR receipt.operator_id<>p_operator
 THEN RAISE EXCEPTION 'Scoring result does not match operator/import' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM private.csv_import_scoring WHERE import_id=p_id FOR UPDATE;
 SELECT * INTO operation FROM private.csv_import_scoring_batches WHERE import_id=p_id AND claim_id=p_claim FOR UPDATE;
 IF NOT FOUND OR operation.claim_id IS DISTINCT FROM p_claim
 THEN RAISE EXCEPTION 'Scoring claim does not match' USING ERRCODE='22023'; END IF;
 IF operation.state IN ('completed','review') THEN
  IF operation.scores IS DISTINCT FROM p_scores
  THEN RAISE EXCEPTION 'Scoring result conflicts with saved evidence' USING ERRCODE='22023'; END IF;
  RETURN operation.response;
 END IF;
 IF operation.state<>'submitting' THEN RAISE EXCEPTION 'Scoring claim is not submitting' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_scores) IS DISTINCT FROM 'object' THEN
  valid:=false;
 ELSE
  SELECT array_agg(value->>'id' ORDER BY value->>'id') INTO expected_ids FROM jsonb_array_elements(operation.snapshots);
  SELECT array_agg(key ORDER BY key) INTO received_ids FROM jsonb_object_keys(p_scores) key;
  valid:=received_ids IS NOT DISTINCT FROM expected_ids;
  IF valid THEN
   FOR assessment IN SELECT value FROM jsonb_each(p_scores) LOOP
    IF jsonb_typeof(assessment) IS DISTINCT FROM 'object' OR assessment-ARRAY[
     'score_motivation','score_timeline','score_equity','score_condition','score_flexibility',
     'ai_qualification_summary','status','precision_tier']<>'{}'::jsonb
    THEN valid:=false; EXIT; END IF;
    FOREACH field IN ARRAY ARRAY['score_motivation','score_timeline','score_equity','score_condition','score_flexibility'] LOOP
     IF jsonb_typeof(assessment->field) IS DISTINCT FROM 'number' OR coalesce(assessment->>field,'') !~ '^[123]$'
     THEN valid:=false; EXIT; END IF;
    END LOOP;
    IF NOT valid THEN EXIT; END IF;
    total:=(assessment->>'score_motivation')::integer+(assessment->>'score_timeline')::integer+
     (assessment->>'score_equity')::integer+(assessment->>'score_condition')::integer+(assessment->>'score_flexibility')::integer;
    tier:=CASE WHEN total>=13 THEN 'hot' WHEN total>=8 THEN 'warm' ELSE 'cold' END;
    IF jsonb_typeof(assessment->'ai_qualification_summary') IS DISTINCT FROM 'string'
     OR coalesce(btrim(assessment->>'ai_qualification_summary'),'')=''
     OR length(assessment->>'ai_qualification_summary')>500
     OR (assessment->>'status') IS DISTINCT FROM 'qualified_'||tier
     OR (assessment->'precision_tier') IS DISTINCT FROM to_jsonb(CASE tier WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 ELSE 3 END)
    THEN valid:=false; EXIT; END IF;
   END LOOP;
  END IF;
 END IF;
 IF valid THEN
  FOR snapshot IN SELECT value FROM jsonb_array_elements(operation.snapshots) ORDER BY value->>'id' LOOP
   SELECT * INTO current_row FROM public.leads WHERE id=(snapshot->>'id')::uuid FOR UPDATE;
   IF NOT FOUND THEN CONTINUE; END IF;
   PERFORM 1 FROM public.tasks WHERE lead_id=current_row.id FOR SHARE;
   IF (to_jsonb(current_row)-ARRAY['updated_at','priority_rank','retention_rule','retention_action',
     'retention_due_at','retention_deletable','retention_reason']) IS DISTINCT FROM snapshot
    OR EXISTS(SELECT 1 FROM public.tasks WHERE lead_id=current_row.id AND (status='completed' OR completed_at IS NOT NULL))
   THEN CONTINUE; END IF;
   assessment:=p_scores->(snapshot->>'id');
   UPDATE public.leads SET score_motivation=(assessment->>'score_motivation')::integer,
    score_timeline=(assessment->>'score_timeline')::integer,score_equity=(assessment->>'score_equity')::integer,
    score_condition=(assessment->>'score_condition')::integer,score_flexibility=(assessment->>'score_flexibility')::integer,
    ai_qualification_summary=assessment->>'ai_qualification_summary',status=assessment->>'status',
    precision_tier=(assessment->>'precision_tier')::integer WHERE id=current_row.id;
   scored:=scored+1; applied:=array_append(applied,current_row.id);
  END LOOP;
  IF scored>0 THEN
   PERFORM public.recompute_priority_ranks();
   PERFORM public.refresh_lead_retention(applied);
  END IF;
 END IF;
 summary:=private.csv_scoring_summary(p_id);
 summary:=jsonb_build_object('scored',(summary->'result'->>'scored')::integer+scored,
  'held',(summary->'result'->>'held')::integer+cardinality(operation.lead_ids)-scored,
  'remaining',(summary->'result'->>'remaining')::integer,'in_flight',0);
 reply:=jsonb_build_object('import_id',p_id,'operator_id',p_operator,'claim_id',p_claim,
  'batch_id',operation.id,'state',CASE WHEN NOT valid THEN 'review'
   WHEN (summary->>'remaining')::integer>0 THEN 'pending'
   WHEN (summary->>'held')::integer>0 THEN 'review' ELSE 'completed' END,'result',summary);
 UPDATE private.csv_import_scoring_batches SET scores=p_scores,halt=NOT valid,
  state=CASE WHEN valid AND scored=cardinality(lead_ids) THEN 'completed' ELSE 'review' END,
  result=jsonb_build_object('scored',scored,'held',cardinality(lead_ids)-scored),response=reply
  WHERE id=operation.id;
 UPDATE private.csv_import_scoring SET scores=p_scores,state=reply->>'state',result=summary,updated_at=now()
  WHERE import_id=p_id;
 RETURN reply;
END $$;
REVOKE ALL ON FUNCTION public.finish_csv_import_scoring(uuid,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_csv_import_scoring(uuid,uuid,uuid,jsonb) TO service_role;


CREATE FUNCTION public.csv_import_scoring_status(p_id uuid,p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE receipt private.csv_lead_imports; eligible integer; summary jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='22023'; END IF;
 SELECT * INTO receipt FROM private.csv_lead_imports WHERE id=p_id;
 IF NOT FOUND OR receipt.operator_id<>p_operator OR receipt.options->>'engine'<>'ai'
  OR receipt.options->>'score_on_import'<>'true'
 THEN RAISE EXCEPTION 'AI import does not match operator' USING ERRCODE='22023'; END IF;
 SELECT cardinality(lead_ids) INTO eligible FROM private.csv_import_scoring WHERE import_id=p_id;
 IF eligible IS NULL THEN RAISE EXCEPTION 'Scoring intent missing' USING ERRCODE='22023'; END IF;
 summary:=private.csv_scoring_summary(p_id);
 RETURN jsonb_build_object('import_id',p_id,'operator_id',p_operator,'eligible',eligible,
  'state',summary->>'state','result',summary->'result');
END $$;
REVOKE ALL ON FUNCTION public.csv_import_scoring_status(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.csv_import_scoring_status(uuid,uuid) TO service_role;
