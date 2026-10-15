-- Service-only RPCs bridge private intake to existing CRM. No seller dispatch.
BEGIN;
GRANT USAGE ON SCHEMA wholesale_ingest TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA wholesale_ingest TO service_role;
ALTER TABLE wholesale_ingest.records ADD COLUMN reviewed_by uuid REFERENCES public.profiles(id),
 ADD COLUMN evidence_url text, ADD COLUMN reviewed_at timestamptz;
CREATE TABLE wholesale_ingest.review_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL,
 batch_index int NOT NULL, ordinal int NOT NULL, operator_id uuid NOT NULL REFERENCES public.profiles(id),
 action text NOT NULL, evidence_url text NOT NULL, property_id uuid,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE wholesale_ingest.review_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.review_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.review_events TO service_role;
CREATE TABLE wholesale_ingest.settings (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), score_threshold int NOT NULL DEFAULT 70 CHECK(score_threshold BETWEEN 0 AND 100),
 daily_trace_cap_cents int NOT NULL DEFAULT 0 CHECK(daily_trace_cap_cents>=0),
 outreach_enabled boolean NOT NULL DEFAULT false
);
ALTER TABLE wholesale_ingest.settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.settings FROM PUBLIC,anon,authenticated;
GRANT SELECT,UPDATE ON wholesale_ingest.settings TO service_role;
INSERT INTO wholesale_ingest.settings DEFAULT VALUES;

INSERT INTO wholesale_ingest.sources(source_key,state,county,jurisdiction,list_type,method,source_url,allowed_hosts,lookback_days,backfill_days,schedule_cron) VALUES
('tx-dallas-pre_foreclosure','TX','Dallas','Dallas County','pre_foreclosure','browser','https://www.dallascounty.org/government/county-clerk/recording/foreclosures.php',ARRAY['www.dallascounty.org'],30,30,'0 5 * * *'),
('tx-collin-pre_foreclosure','TX','Collin','Collin County','pre_foreclosure','browser','https://apps2.collincountytx.gov/ForeclosureNotices/',ARRAY['apps2.collincountytx.gov','www.collincountytx.gov'],30,30,'5 5 * * *'),
('tx-dallas-probate','TX','Dallas','Dallas County','probate','browser','https://www.dallascounty.org/government/county-clerk/probate-courts/',ARRAY['www.dallascounty.org'],7,30,'10 5 * * *'),
('tx-collin-probate','TX','Collin','Collin County','probate','browser','https://www.collincountytx.gov/services/case-information',ARRAY['www.collincountytx.gov'],7,30,'15 5 * * *'),
('tx-dallas-tax_delinquent','TX','Dallas','Dallas County','tax_delinquent','export','https://www.dallascounty.org/departments/tax/tax-roll.php',ARRAY['www.dallascounty.org'],30,30,'20 5 * * *'),
('tx-collin-tax_delinquent','TX','Collin','Collin County','tax_delinquent','export','https://www.collincountytx.gov/Tax-Assessor/property-taxes',ARRAY['www.collincountytx.gov'],30,30,'25 5 * * *'),
('tx-dallas-code_violation-dallas','TX','Dallas','Dallas','code_violation','api','https://www.dallasopendata.com/Archive/Code-Violations/x9pz-kdq9/data',ARRAY['www.dallasopendata.com','www.dallasopendata.com'],7,30,'30 5 * * *'),
('tx-collin-code_violation-mckinney','TX','Collin','McKinney','code_violation','api','https://maps.mckinneytexas.org/mckinney/rest/services/MapServices/CodeServices/MapServer/1',ARRAY['maps.mckinneytexas.org'],7,30,'35 5 * * *');

CREATE FUNCTION public.list_pipeline_snapshot(p_day date,p_offset int DEFAULT 0) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
 'day',p_day,'settings',(SELECT to_jsonb(s) FROM wholesale_ingest.settings s),
 'sources',(SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY source_key),'[]') FROM wholesale_ingest.sources s),
 'runs',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY received_at DESC),'[]') FROM wholesale_ingest.ingest_runs r WHERE scheduled_for=p_day),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]') FROM (
   SELECT r.run_id,r.batch_index,r.ordinal,r.source_record_id,r.review_reason,r.record->>'property_address' AS property_address,
    s.source_key,r.record->>'source_url' AS source_url
   FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id
   JOIN wholesale_ingest.sources s ON s.id=i.source_id
   WHERE r.review_reason IS NOT NULL AND r.resolved_at IS NULL ORDER BY i.received_at,r.batch_index,r.ordinal
   LIMIT 100 OFFSET greatest(0,p_offset)) q),
 'review_count',(SELECT count(*) FROM wholesale_ingest.records WHERE review_reason IS NOT NULL AND resolved_at IS NULL),
 'digest',(SELECT to_jsonb(d) FROM wholesale_ingest.daily_digests d WHERE day=p_day));
$$;
CREATE FUNCTION public.configure_list_source(p_key text,p_operator uuid,p_enabled boolean,p_lookback int,p_procedure text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s wholesale_ingest.sources;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_enabled AND (p_procedure IS NULL OR length(trim(p_procedure))<3) THEN RAISE EXCEPTION 'Reviewed procedure version required'; END IF;
 UPDATE wholesale_ingest.sources SET enabled=p_enabled,lookback_days=p_lookback,
 procedure_version=p_procedure,procedure_approved_at=CASE WHEN p_enabled THEN now() ELSE procedure_approved_at END
 WHERE source_key=p_key RETURNING * INTO s;
 IF s.id IS NULL THEN RAISE EXCEPTION 'Unknown source'; END IF;
 RETURN to_jsonb(s);
END; $$;

CREATE FUNCTION public.resolve_list_record(p_run uuid,p_batch int,p_ordinal int,p_operator uuid,p_county text,p_evidence_url text,p_lead uuid DEFAULT NULL,p_active boolean DEFAULT true) RETURNS jsonb
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

CREATE FUNCTION public.scan_list_pipeline() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE today date:=(now() AT TIME ZONE 'America/Chicago')::date; owner uuid; e record; summary jsonb; missing int;
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:list-monitor',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value WHERE a.key='lead_owner_user_id' AND p.status='approved';
 INSERT INTO wholesale_ingest.expected_runs(source_id,day,due_at)
 SELECT id,today,(today+deadline_local) AT TIME ZONE timezone FROM wholesale_ingest.sources WHERE enabled ON CONFLICT DO NOTHING;
 FOR e IN SELECT x.* FROM wholesale_ingest.expected_runs x JOIN wholesale_ingest.sources s ON s.id=x.source_id
 WHERE s.enabled AND x.day=today AND x.due_at<now() AND x.alert_task_id IS NULL
 AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.ingest_runs i WHERE i.source_id=x.source_id AND i.scheduled_for=x.day
   AND (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches)
 LOOP
  IF owner IS NOT NULL THEN
   UPDATE wholesale_ingest.expected_runs SET alert_task_id=gen_random_uuid() WHERE source_id=e.source_id AND day=e.day RETURNING alert_task_id INTO e.alert_task_id;
   INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
   VALUES(e.alert_task_id,'Daily list delivery missing','Source '||e.source_id||': no complete batch set by deadline. Review collection/delivery; do not infer zero records.','pending','high','follow_up',owner,now());
  END IF;
 END LOOP;
 UPDATE wholesale_ingest.ingest_runs i SET processing_status=CASE WHEN EXISTS(SELECT 1 FROM wholesale_ingest.records r WHERE r.run_id=i.id AND r.resolved_at IS NULL) OR i.status<>'success' THEN 'review' ELSE 'completed' END,
 completed_at=CASE WHEN NOT EXISTS(SELECT 1 FROM wholesale_ingest.records r WHERE r.run_id=i.id AND r.resolved_at IS NULL) AND i.status='success' THEN now() ELSE NULL END
 WHERE (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches AND i.processing_status<>'completed';
 UPDATE wholesale_ingest.jobs j SET state=CASE WHEN i.processing_status='completed' THEN 'done' ELSE 'review' END
 FROM wholesale_ingest.ingest_runs i WHERE j.run_id=i.id AND i.processing_status IN ('review','completed') AND j.state='pending';
 SELECT count(*) INTO missing FROM wholesale_ingest.expected_runs x JOIN wholesale_ingest.sources s ON s.id=x.source_id WHERE s.enabled AND x.day=today AND x.due_at<now() AND NOT EXISTS(
 SELECT 1 FROM wholesale_ingest.ingest_runs i WHERE i.source_id=x.source_id AND i.scheduled_for=x.day AND (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches);
 SELECT jsonb_build_object('day',today,'missing_sources',missing,'owner_configured',owner IS NOT NULL,
 'new_leads',coalesce(sum(records_new),0),'stacked_records',coalesce(sum(records_stacked),0),
 'runs',coalesce(jsonb_agg(jsonb_build_object('run_id',id,'source_id',source_id,'status',status,'processing_status',processing_status,'records_in',(SELECT coalesce(sum(b.records_in),0) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id))),'[]'))
 INTO summary FROM wholesale_ingest.ingest_runs i WHERE scheduled_for=today;
 INSERT INTO wholesale_ingest.daily_digests(day,generated_at,status,summary) VALUES(today,now(),'generated',summary)
 ON CONFLICT(day) DO UPDATE SET generated_at=now(),summary=excluded.summary;
 -- Raw records cascade away after audit retention; normalized evidence/provenance remains.
 DELETE FROM wholesale_ingest.raw_payloads WHERE expires_at<now();
 DELETE FROM wholesale_ingest.contacts WHERE expires_at<now();
 RETURN summary;
END; $$;

DO $$ DECLARE f regprocedure; BEGIN
 FOR f IN SELECT oid::regprocedure FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname IN ('list_pipeline_snapshot','configure_list_source','resolve_list_record','scan_list_pipeline') LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',f);
 EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',f);
 END LOOP;
END $$;
COMMIT;
