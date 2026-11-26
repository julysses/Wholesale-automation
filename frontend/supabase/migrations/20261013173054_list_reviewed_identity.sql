-- Audited situs review preserves original county payloads. No outreach authorization.
BEGIN;
ALTER TABLE wholesale_ingest.review_events ADD COLUMN review_details jsonb;
CREATE OR REPLACE FUNCTION public.resolve_reviewed_list_record(p_run uuid,p_batch int,p_ordinal int,p_operator uuid,p_county text,p_evidence_url text,p_lead uuid,p_active boolean,p_review jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r wholesale_ingest.records; s wholesale_ingest.sources; v jsonb; prop uuid; lid uuid; sig uuid;
 aliases text[]; prefix text; matches uuid[]; host text; a text; new_lead boolean:=false; identity jsonb; prior wholesale_ingest.review_events;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 -- All identity mutations share a lock; aliases cannot be claimed by concurrent reviews.
 PERFORM pg_advisory_xact_lock(hashtextextended('wholesaleos:list-identity',0));
 SELECT * INTO r FROM wholesale_ingest.records WHERE run_id=p_run AND batch_index=p_batch AND ordinal=p_ordinal FOR UPDATE;
 IF r.run_id IS NULL THEN RAISE EXCEPTION 'Record missing'; END IF;
 IF jsonb_typeof(p_review) IS DISTINCT FROM 'object' OR
    coalesce(p_review->>'source_fingerprint','') IS DISTINCT FROM md5(r.record::text) OR
    coalesce(length(trim(p_review->>'notes')),0) NOT BETWEEN 10 AND 2000 OR
    jsonb_typeof(p_review->'identity') IS DISTINCT FROM 'object' OR
    EXISTS(SELECT 1 FROM jsonb_object_keys(p_review) k WHERE k NOT IN ('source_fingerprint','notes','identity'))
 THEN RAISE EXCEPTION 'Current source fingerprint, identity and review notes required'; END IF;
 identity:=p_review->'identity';
 IF EXISTS(SELECT 1 FROM jsonb_object_keys(identity) k WHERE k NOT IN ('property_address','city','state','zip','parcel_id','unit')) OR
    EXISTS(SELECT 1 FROM jsonb_each(identity) e WHERE jsonb_typeof(e.value) NOT IN ('string','null')) OR
    coalesce(length(trim(identity->>'property_address')),0) NOT BETWEEN 1 AND 300 OR
    coalesce(length(trim(identity->>'city')),0) NOT BETWEEN 1 AND 100 OR identity->>'state' IS DISTINCT FROM 'TX' OR
    coalesce(identity->>'zip','') !~ '^[0-9]{5}(-[0-9]{4})?$' OR
    coalesce(length(identity->>'parcel_id'),0)>100 OR coalesce(length(identity->>'unit'),0)>100
 THEN RAISE EXCEPTION 'Verified Texas situs address, city and ZIP required'; END IF;
 IF p_active IS NULL THEN RAISE EXCEPTION 'Explicit signal status required'; END IF;
 IF r.resolved_at IS NOT NULL THEN
  SELECT * INTO prior FROM wholesale_ingest.review_events WHERE run_id=p_run AND batch_index=p_batch AND ordinal=p_ordinal AND action='verified_property' ORDER BY created_at DESC LIMIT 1;
  IF prior.review_details IS DISTINCT FROM jsonb_build_object('review',p_review,'active_signal',p_active,'lead_id',p_lead,'county',p_county) OR prior.evidence_url IS DISTINCT FROM p_evidence_url OR prior.operator_id IS DISTINCT FROM p_operator
  THEN RAISE EXCEPTION 'Already resolved with different review evidence'; END IF;
  SELECT lead_id INTO lid FROM wholesale_ingest.properties WHERE id=r.property_id;
  RETURN jsonb_build_object('replayed',true,'property_id',r.property_id,'lead_id',lid,'outreach_authorized',false,'run_id',p_run,'batch_index',p_batch,'ordinal',p_ordinal,'review',p_review);
 END IF;
 -- Match the ingress lock so a review cannot race receipt writes for this run.
 PERFORM pg_advisory_xact_lock(hashtextextended(p_run::text,0));
 IF NOT EXISTS (
  SELECT 1 FROM wholesale_ingest.ingest_runs i WHERE i.id=p_run
  AND (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches
  AND NOT EXISTS (SELECT 1 FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id
   AND (b.batch_index>=i.expected_batches OR b.expires_at<=now()))
 ) THEN RAISE EXCEPTION 'Complete unexpired batch set required before property review'; END IF;

 SELECT src.* INTO s FROM wholesale_ingest.sources src JOIN wholesale_ingest.ingest_runs i ON i.source_id=src.id WHERE i.id=p_run;
 v:=r.record||identity; -- Original county record and raw payload hashes remain unchanged.
 IF p_county IS DISTINCT FROM s.county OR p_county NOT IN ('Dallas','Collin') THEN RAISE EXCEPTION 'County mismatch'; END IF;
 host:=substring(lower(p_evidence_url) from '^https://([^/:?#]+)(?:[/:?#]|$)');
 IF host IS NULL OR NOT (host=ANY(CASE WHEN p_county='Dallas' THEN ARRAY['www.dallascad.org','dallascad.org','www.dallascounty.org'] ELSE ARRAY['www.collincad.org','collincad.org','www.collincountytx.gov','gis.collincountytx.gov'] END)) THEN RAISE EXCEPTION 'Official county/title evidence required'; END IF;
 IF p_lead IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead AND lower(trim(property_address))=lower(trim(v->>'property_address')) AND lower(trim(city))=lower(trim(v->>'city')) AND state='TX' AND zip_code=v->>'zip') THEN RAISE EXCEPTION 'Selected CRM lead does not match verified property'; END IF;
 IF r.source_record_id IS NULL OR nullif(trim(v->>'property_address'),'') IS NULL OR nullif(trim(v->>'city'),'') IS NULL OR v->>'state' IS DISTINCT FROM 'TX' THEN RAISE EXCEPTION 'Stable source ID and verified property address required'; END IF;
 IF s.list_type='pre_foreclosure' AND v->>'filed_date' IS NULL THEN RAISE EXCEPTION 'Notice filing date required'; END IF;
 prefix:='tx|'||lower(s.county)||'|';
 aliases:=ARRAY[prefix||'address|'||lower(regexp_replace(trim(v->>'property_address'),'\s+',' ','g'))||'|'||lower(coalesce(v->>'unit',''))||'|'||lower(v->>'city')||'|'||coalesce(v->>'zip','')];
 IF nullif(trim(v->>'parcel_id'),'') IS NOT NULL THEN aliases:=array_append(aliases,prefix||'parcel|'||lower(trim(v->>'parcel_id'))); END IF;
 SELECT array_agg(DISTINCT property_id) INTO matches FROM wholesale_ingest.property_aliases WHERE alias_key=ANY(aliases);
 IF cardinality(matches)>1 THEN RAISE EXCEPTION 'Conflicting identities require reconciliation'; END IF;
 prop:=matches[1];
 IF prop IS NOT NULL THEN
  SELECT lead_id INTO lid FROM wholesale_ingest.properties WHERE id=prop;
  IF p_lead IS NOT NULL AND p_lead IS DISTINCT FROM lid THEN RAISE EXCEPTION 'Existing property has another lead'; END IF;
 ELSE
  lid:=p_lead;
  IF lid IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.leads WHERE id=lid) THEN RAISE EXCEPTION 'Lead missing'; END IF;
  IF lid IS NULL THEN
   -- Existing legacy leads have no verified county key: ask operator to choose rather than duplicate.
   IF EXISTS(SELECT 1 FROM public.leads WHERE lower(trim(property_address))=lower(trim(v->>'property_address')) AND lower(trim(city))=lower(trim(v->>'city'))) THEN RAISE EXCEPTION 'Existing CRM address requires explicit lead selection'; END IF;
   INSERT INTO public.leads(property_address,city,state,zip_code,source,motivation_tag,status,owner_mailing_address,sms_sequence_active,email_sequence_active)
    VALUES(v->>'property_address',v->>'city','TX',v->>'zip',s.source_key,s.list_type,'new',v->>'mailing_address',false,false) RETURNING id INTO lid;
   new_lead:=true;
  END IF;
  INSERT INTO wholesale_ingest.properties(state,county,parcel_id,address_std,unit,city,zip,lead_id)
   VALUES('TX',s.county,v->>'parcel_id',v->>'property_address',v->>'unit',v->>'city',v->>'zip',lid) RETURNING id INTO prop;
 END IF;
 FOREACH a IN ARRAY aliases LOOP
  INSERT INTO wholesale_ingest.property_aliases(alias_key,property_id,evidence_url) VALUES(a,prop,p_evidence_url) ON CONFLICT(alias_key) DO NOTHING;
 END LOOP;
 INSERT INTO wholesale_ingest.distress_signals(property_id,source_id,source_record_id,list_type,case_number,filed_date,auction_date,amount,amount_type,source_url,first_run_id,last_run_id,active)
 VALUES(prop,s.id,r.source_record_id,s.list_type,v->>'case_number',(v->>'filed_date')::date,(v->>'auction_date')::date,(v->>'amount_owed')::numeric,v->>'amount_type',v->>'source_url',p_run,p_run,p_active)
 ON CONFLICT(property_id,source_id,source_record_id) DO UPDATE SET last_run_id=p_run,last_seen_at=now(),active=p_active,amount=excluded.amount
 RETURNING id INTO sig;
 INSERT INTO wholesale_ingest.signal_observations(signal_id,run_id,source_url,pulled_at)
 SELECT sig,p_run,v->>'source_url',pulled_at FROM wholesale_ingest.ingest_runs WHERE id=p_run ON CONFLICT DO NOTHING;
 UPDATE wholesale_ingest.records SET property_id=prop,resolved_at=now(),reviewed_by=p_operator,reviewed_at=now(),evidence_url=p_evidence_url,review_reason=NULL
 WHERE run_id=p_run AND batch_index=p_batch AND ordinal=p_ordinal;
 INSERT INTO wholesale_ingest.review_events(run_id,batch_index,ordinal,operator_id,action,evidence_url,property_id,review_details)
 VALUES(p_run,p_batch,p_ordinal,p_operator,'verified_property',p_evidence_url,prop,jsonb_build_object('review',p_review,'active_signal',p_active,'lead_id',p_lead,'county',p_county));
 UPDATE wholesale_ingest.ingest_runs SET records_new=records_new+new_lead::int,records_stacked=records_stacked+(NOT new_lead)::int WHERE id=p_run;
 RETURN jsonb_build_object('replayed',false,'property_id',prop,'lead_id',lid,'new_lead',new_lead,'outreach_authorized',false,'run_id',p_run,'batch_index',p_batch,'ordinal',p_ordinal,'review',p_review,
 'stack_count',(SELECT count(DISTINCT list_type) FROM wholesale_ingest.distress_signals WHERE property_id=prop AND active));
END; $$;

REVOKE ALL ON FUNCTION public.resolve_reviewed_list_record(uuid,int,int,uuid,text,text,uuid,boolean,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.resolve_reviewed_list_record(uuid,int,int,uuid,text,text,uuid,boolean,jsonb) TO service_role;
CREATE OR REPLACE FUNCTION public.list_pipeline_snapshot(p_day date,p_offset int DEFAULT 0) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
 'day',p_day,'settings',(SELECT to_jsonb(s) FROM wholesale_ingest.settings s),
 'sources',(SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY source_key),'[]') FROM wholesale_ingest.sources s),
 'runs',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY received_at DESC),'[]') FROM wholesale_ingest.ingest_runs r WHERE scheduled_for=p_day),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]') FROM (
   SELECT r.run_id,r.batch_index,r.ordinal,r.source_record_id,r.review_reason,r.record->>'property_address' AS property_address,
    s.source_key,r.record->>'source_url' AS source_url,md5(r.record::text) AS source_fingerprint,
    r.record->>'city' AS city,r.record->>'state' AS state,r.record->>'zip' AS zip,
    r.record->>'parcel_id' AS parcel_id,r.record->>'unit' AS unit
   FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id
   JOIN wholesale_ingest.sources s ON s.id=i.source_id
   WHERE r.review_reason IS NOT NULL AND r.resolved_at IS NULL ORDER BY i.received_at,r.batch_index,r.ordinal
   LIMIT 100 OFFSET greatest(0,p_offset)) q),
 'review_count',(SELECT count(*) FROM wholesale_ingest.records WHERE review_reason IS NOT NULL AND resolved_at IS NULL),
 'digest',(SELECT to_jsonb(d) FROM wholesale_ingest.daily_digests d WHERE day=p_day));
$$;
COMMIT;
