-- Additive correction; original split rehearsal migrations must not be replayed.
BEGIN;
CREATE OR REPLACE FUNCTION public.resolve_list_record(p_run uuid,p_batch int,p_ordinal int,p_operator uuid,p_county text,p_evidence_url text,p_lead uuid DEFAULT NULL,p_active boolean DEFAULT true) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r wholesale_ingest.records; s wholesale_ingest.sources; v jsonb; prop uuid; lid uuid; sig uuid;
 aliases text[]; prefix text; matches uuid[]; host text; a text; new_lead boolean:=false;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 -- All identity mutations share a lock; aliases cannot be claimed by concurrent reviews.
 PERFORM pg_advisory_xact_lock(hashtextextended('wholesaleos:list-identity',0));
 SELECT * INTO r FROM wholesale_ingest.records WHERE run_id=p_run AND batch_index=p_batch AND ordinal=p_ordinal FOR UPDATE;
 IF r.run_id IS NULL THEN RAISE EXCEPTION 'Record missing'; END IF;
 IF r.resolved_at IS NOT NULL THEN RETURN jsonb_build_object('replayed',true,'property_id',r.property_id); END IF;
 -- Match the ingress lock so a review cannot race receipt writes for this run.
 PERFORM pg_advisory_xact_lock(hashtextextended(p_run::text,0));
 IF NOT EXISTS (
  SELECT 1 FROM wholesale_ingest.ingest_runs i WHERE i.id=p_run
  AND (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches
  AND NOT EXISTS (SELECT 1 FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id
   AND (b.batch_index>=i.expected_batches OR b.expires_at<=now()))
 ) THEN RAISE EXCEPTION 'Complete unexpired batch set required before property review'; END IF;

 SELECT src.* INTO s FROM wholesale_ingest.sources src JOIN wholesale_ingest.ingest_runs i ON i.source_id=src.id WHERE i.id=p_run;
 v:=r.record;
 IF p_county IS DISTINCT FROM s.county OR p_county NOT IN ('Dallas','Collin') THEN RAISE EXCEPTION 'County mismatch'; END IF;
 host:=substring(lower(p_evidence_url) from '^https://([^/:?#]+)(?:[/:?#]|$)');
 IF host IS NULL OR NOT (host=ANY(CASE WHEN p_county='Dallas' THEN ARRAY['www.dallascad.org','dallascad.org','www.dallascounty.org'] ELSE ARRAY['www.collincad.org','collincad.org','www.collincountytx.gov','gis.collincountytx.gov'] END)) THEN RAISE EXCEPTION 'Official county/title evidence required'; END IF;
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
 INSERT INTO wholesale_ingest.review_events(run_id,batch_index,ordinal,operator_id,action,evidence_url,property_id)
 VALUES(p_run,p_batch,p_ordinal,p_operator,'verified_property',p_evidence_url,prop);
 UPDATE wholesale_ingest.ingest_runs SET records_new=records_new+new_lead::int,records_stacked=records_stacked+(NOT new_lead)::int WHERE id=p_run;
 RETURN jsonb_build_object('replayed',false,'property_id',prop,'lead_id',lid,'new_lead',new_lead,
 'stack_count',(SELECT count(DISTINCT list_type) FROM wholesale_ingest.distress_signals WHERE property_id=prop AND active));
END; $$;

REVOKE ALL ON FUNCTION public.resolve_list_record(uuid,int,int,uuid,text,text,uuid,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.resolve_list_record(uuid,int,int,uuid,text,text,uuid,boolean) TO service_role;
COMMIT;
