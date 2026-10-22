-- Proposed server-only buyer CSV transaction. No provider, cron or consent activation.
CREATE TABLE private.buyer_csv_imports (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT now(), fingerprint text NOT NULL,
 options jsonb NOT NULL, result jsonb NOT NULL
);
ALTER TABLE private.buyer_csv_imports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_csv_imports FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.buyer_csv_imports TO service_role;
CREATE TRIGGER buyer_csv_import_immutable BEFORE UPDATE OR DELETE ON private.buyer_csv_imports
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();

CREATE FUNCTION public.import_buyer_csv(p_id uuid,p_operator uuid,p_fingerprint text,p_groups jsonb,p_options jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE
 prior private.buyer_csv_imports; g jsonb; b jsonb; tx jsonb; columns_sql text;
 v_buyer_id uuid; transaction_id uuid; candidates uuid[]; existing_tx public.buyer_transactions;
 created_count integer:=0; existing_count integer:=0; tx_created integer:=0; tx_existing integer:=0;
 mapping jsonb:='[]'; result jsonb; log_id uuid:=p_id; tx_ids uuid[];
 buyer_fields text[]:=ARRAY['first_name','last_name','company','entity_name','phone','email','market','cash_buyer',
 'repeat_buyer','source','active','email_opt_in','sms_opt_in','deals_closed','pof_verified','tier','ibie_score',
 'ibie_tier','tags','total_purchases_12mo','properties_owned','avg_purchase_price','last_purchase_date'];
BEGIN
 IF p_id IS NULL OR p_operator IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF p_fingerprint IS NULL OR p_fingerprint !~ '^[0-9a-f]{64}$' OR jsonb_typeof(p_groups) IS DISTINCT FROM 'array'
 OR jsonb_array_length(p_groups)>5000 OR jsonb_typeof(p_options) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'Invalid buyer import' USING ERRCODE='22023'; END IF;
 IF coalesce((p_options->>'rows_total')::integer,-1) NOT BETWEEN 0 AND 5000
 OR coalesce((p_options->>'rows_skipped')::integer,-1) NOT BETWEEN 0 AND (p_options->>'rows_total')::integer
 OR (SELECT coalesce(sum(jsonb_array_length(value->'transactions')),0) FROM jsonb_array_elements(p_groups))
    <> (p_options->>'rows_total')::integer-(p_options->>'rows_skipped')::integer
 THEN RAISE EXCEPTION 'Invalid import row totals' USING ERRCODE='22023'; END IF;
 -- Serialize retries before table locks; all data writes and the receipt are one transaction.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('buyer-csv:'||p_id::text,0));
 SELECT * INTO prior FROM private.buyer_csv_imports WHERE id=p_id;
 IF FOUND THEN
   IF prior.operator_id<>p_operator THEN RAISE EXCEPTION 'Import belongs to another operator' USING ERRCODE='42501'; END IF;
   IF prior.fingerprint<>p_fingerprint OR prior.options<>p_options THEN
     RAISE EXCEPTION 'Import reference changed' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('import_id',p_id,'operator_id',p_operator,'fingerprint',p_fingerprint,'options',p_options,
     'replayed',true,'result',prior.result,'outreach_authorized',false);
 END IF;
 -- Existing tables have no reliable natural buyer key. These bounded locks also
 -- prevent a browser insert/update from racing the identity decision. Volume/lock
 -- acceptance is required before production application; never silently retry.
 PERFORM pg_catalog.set_config('lock_timeout','3s',true);
 LOCK TABLE public.buyers,public.buyer_transactions IN SHARE ROW EXCLUSIVE MODE;
 INSERT INTO public.buyer_import_log(id,imported_by,source,filename,market,status)
 VALUES(log_id,p_operator,'county_csv',p_options->>'filename',p_options->>'market','processing');
 FOR g IN SELECT value FROM jsonb_array_elements(p_groups) LOOP
   b:=g->'buyer';
   IF jsonb_typeof(b) IS DISTINCT FROM 'object' OR jsonb_typeof(g->'transactions') IS DISTINCT FROM 'array'
     OR jsonb_array_length(g->'transactions')=0
     OR coalesce(b->>'first_name','')='' OR coalesce(b->>'last_name','') IS NULL
     OR EXISTS(SELECT 1 FROM jsonb_object_keys(b) AS k WHERE NOT k=ANY(buyer_fields))
   THEN RAISE EXCEPTION 'Invalid buyer group' USING ERRCODE='22023'; END IF;
   -- Do not guess between different entity/contact matches or same-name people.
   SELECT array_agg(x.id) INTO candidates FROM public.buyers x WHERE
     (nullif(btrim(b->>'entity_name'),'') IS NOT NULL AND lower(btrim(x.entity_name))=lower(btrim(b->>'entity_name')))
     OR (nullif(b->>'phone','') IS NOT NULL AND regexp_replace(x.phone,'[^0-9]','','g')=regexp_replace(b->>'phone','[^0-9]','','g'))
     OR (nullif(btrim(b->>'email'),'') IS NOT NULL AND lower(btrim(x.email))=lower(btrim(b->>'email')));
   IF coalesce(cardinality(candidates),0)>1 THEN RAISE EXCEPTION 'Conflicting buyer identities require review' USING ERRCODE='22023'; END IF;
   v_buyer_id:=candidates[1];
   IF v_buyer_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.buyers x WHERE x.id=v_buyer_id AND
     ((nullif(x.entity_name,'') IS NOT NULL AND lower(btrim(x.entity_name))<>lower(btrim(coalesce(b->>'entity_name','')))) OR
      (nullif(x.entity_name,'') IS NULL AND (lower(btrim(x.first_name))<>lower(btrim(b->>'first_name')) OR lower(btrim(x.last_name))<>lower(btrim(b->>'last_name'))))))
   THEN RAISE EXCEPTION 'Shared contact has conflicting buyer identity' USING ERRCODE='22023'; END IF;
   IF v_buyer_id IS NULL THEN
     IF nullif(btrim(b->>'entity_name'),'') IS NULL AND EXISTS(SELECT 1 FROM public.buyers x
       WHERE lower(btrim(x.first_name))=lower(btrim(b->>'first_name')) AND lower(btrim(x.last_name))=lower(btrim(b->>'last_name')))
     THEN RAISE EXCEPTION 'Same-name buyer requires confirmed contact identity' USING ERRCODE='22023'; END IF;
     b:=b||jsonb_build_object('sms_opt_in',false,'email_opt_in',false,'active',true);
     SELECT string_agg(format('%I',k),',' ORDER BY k) INTO columns_sql FROM jsonb_object_keys(b) AS k;
     EXECUTE format('INSERT INTO public.buyers(%s) SELECT %s FROM jsonb_populate_record(NULL::public.buyers,$1) RETURNING id',columns_sql,columns_sql)
       INTO v_buyer_id USING b;
     UPDATE public.buyers SET import_log_id=log_id WHERE id=v_buyer_id;
     created_count:=created_count+1;
   ELSE
     -- Only fill blank contact context. Preserve all consent, availability,
     -- preferences, scores, notes, outreach counters, classification and history.
     UPDATE public.buyers SET
       company=coalesce(nullif(company,''),nullif(b->>'company',''),company),
       entity_name=coalesce(nullif(entity_name,''),nullif(b->>'entity_name',''),entity_name),
       phone=CASE WHEN sms_opt_in IS TRUE THEN phone ELSE coalesce(nullif(phone,''),nullif(b->>'phone',''),phone) END,
       email=CASE WHEN email_opt_in IS TRUE THEN email ELSE coalesce(nullif(email,''),nullif(b->>'email',''),email) END,
       market=coalesce(nullif(market,''),nullif(b->>'market',''),market)
     WHERE id=v_buyer_id AND (
       (coalesce(company,'')='' AND coalesce(b->>'company','')<>'') OR
       (coalesce(entity_name,'')='' AND coalesce(b->>'entity_name','')<>'') OR
       (coalesce(phone,'')='' AND sms_opt_in IS NOT TRUE AND coalesce(b->>'phone','')<>'') OR
       (coalesce(email,'')='' AND email_opt_in IS NOT TRUE AND coalesce(b->>'email','')<>'') OR
       (coalesce(market,'')='' AND coalesce(b->>'market','')<>''));
     existing_count:=existing_count+1;
   END IF;
   IF mapping @> jsonb_build_array(v_buyer_id) THEN RAISE EXCEPTION 'Distinct groups resolve to one buyer; review required' USING ERRCODE='22023'; END IF;
   FOR tx IN SELECT value FROM jsonb_array_elements(g->'transactions') LOOP
     IF jsonb_typeof(tx) IS DISTINCT FROM 'object' OR nullif(btrim(tx->>'property_address'),'') IS NULL
       OR tx ?| ARRAY['id','buyer_id','created_at']
     THEN RAISE EXCEPTION 'Invalid purchase record' USING ERRCODE='22023'; END IF;
     -- APN uniqueness is a production constraint. A different event on the same
     -- parcel must be reviewed, never overwritten or inserted by fallback.
     SELECT array_agg(x.id) INTO tx_ids FROM public.buyer_transactions x WHERE x.buyer_id=v_buyer_id AND
       ((nullif(tx->>'apn','') IS NOT NULL AND x.apn=tx->>'apn') OR
        (nullif(tx->>'apn','') IS NULL AND x.apn IS NULL AND
         lower(btrim(x.property_address))=lower(btrim(tx->>'property_address')) AND
         lower(coalesce(x.city,''))=lower(coalesce(tx->>'city','')) AND
         lower(coalesce(x.state,''))=lower(coalesce(tx->>'state','')) AND
         coalesce(x.zip_code,'')=coalesce(tx->>'zip_code','') AND
         x.purchase_date IS NOT DISTINCT FROM (tx->>'purchase_date')::date));
     IF coalesce(cardinality(tx_ids),0)>1 THEN RAISE EXCEPTION 'Ambiguous purchase history requires review' USING ERRCODE='22023'; END IF;
     IF cardinality(tx_ids)=1 THEN
       SELECT * INTO existing_tx FROM public.buyer_transactions WHERE id=tx_ids[1];
       IF existing_tx.purchase_date IS DISTINCT FROM (tx->>'purchase_date')::date OR
          existing_tx.purchase_price IS DISTINCT FROM (tx->>'purchase_price')::numeric OR
          lower(btrim(existing_tx.property_address))<>lower(btrim(tx->>'property_address')) OR
          lower(coalesce(existing_tx.city,''))<>lower(coalesce(tx->>'city','')) OR
          lower(coalesce(existing_tx.state,''))<>lower(coalesce(tx->>'state','')) OR
          coalesce(existing_tx.zip_code,'')<>coalesce(tx->>'zip_code','')
       THEN RAISE EXCEPTION 'Conflicting purchase history requires review' USING ERRCODE='22023'; END IF;
       tx_existing:=tx_existing+1;
     ELSE
       SELECT string_agg(format('%I',k),',' ORDER BY k) INTO columns_sql FROM jsonb_object_keys(tx) AS k;
       -- Only real transaction columns are accepted by the typed record; unknown
       -- columns in this explicit identifier list fail the whole transaction.
       EXECUTE format('INSERT INTO public.buyer_transactions(buyer_id,%s) SELECT $2,%s FROM jsonb_populate_record(NULL::public.buyer_transactions,$1) RETURNING id',columns_sql,columns_sql)
         INTO transaction_id USING tx,v_buyer_id;
       tx_created:=tx_created+1;
     END IF;
   END LOOP;
   mapping:=mapping||jsonb_build_array(v_buyer_id);
 END LOOP;
 result:=jsonb_build_object('buyers_created',created_count,'buyers_existing',existing_count,
   'transactions_created',tx_created,'transactions_existing',tx_existing,'buyer_ids',mapping,
   'rows_total',(p_options->>'rows_total')::integer,'rows_skipped',(p_options->>'rows_skipped')::integer);
 UPDATE public.buyer_import_log SET rows_total=(p_options->>'rows_total')::integer,
   rows_imported=(p_options->>'rows_total')::integer-(p_options->>'rows_skipped')::integer,
   rows_skipped=(p_options->>'rows_skipped')::integer,buyers_created=created_count,buyers_updated=existing_count,
   transactions_created=tx_created,status='complete',completed_at=now() WHERE id=log_id;
 INSERT INTO private.buyer_csv_imports(id,operator_id,fingerprint,options,result)
 VALUES(p_id,p_operator,p_fingerprint,p_options,result);
 RETURN jsonb_build_object('import_id',p_id,'operator_id',p_operator,'fingerprint',p_fingerprint,'options',p_options,
   'replayed',false,'result',result,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.import_buyer_csv(uuid,uuid,text,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.import_buyer_csv(uuid,uuid,text,jsonb,jsonb) TO service_role;
