-- Preserve original source data while showing the context needed for tax review.
BEGIN;
CREATE OR REPLACE FUNCTION public.list_pipeline_snapshot_filtered(p_day date,p_offset int,p_source_key text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
 'day',p_day,'settings',(SELECT to_jsonb(s) FROM wholesale_ingest.settings s),
 'sources',(SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY source_key),'[]') FROM wholesale_ingest.sources s),
 'runs',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY received_at DESC),'[]') FROM wholesale_ingest.ingest_runs r WHERE scheduled_for=p_day),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]') FROM (
   SELECT r.run_id,r.batch_index,r.ordinal,r.source_record_id,r.review_reason,r.record->>'property_address' AS property_address,
    s.source_key,r.record->>'source_url' AS source_url,md5(r.record::text) AS source_fingerprint,
    r.record->>'city' AS city,r.record->>'state' AS state,r.record->>'zip' AS zip,
    r.record->>'parcel_id' AS parcel_id,r.record->>'unit' AS unit,
    CASE WHEN s.list_type='tax_delinquent' THEN jsonb_build_object(
      'snapshot_date',r.record->'raw'->'snapshot_date',
      'amount_cents',CASE WHEN s.county='Dallas' THEN r.record->'raw'->'remaining_levy_cents' ELSE r.record->'raw'->'snapshot_balance_cents' END,
      'amount_kind',CASE WHEN s.county='Dallas' THEN 'remaining_levy' ELSE 'balance' END,
      'review_flags',r.record->'raw'->'review_flags',
      'situs_missing',r.record->'raw'->'situs_missing') ELSE NULL END AS tax_snapshot
   FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id
   JOIN wholesale_ingest.sources s ON s.id=i.source_id
   WHERE r.review_reason IS NOT NULL AND r.resolved_at IS NULL
    AND (p_source_key IS NULL OR s.source_key=p_source_key)
   ORDER BY i.received_at,i.id,r.batch_index,r.ordinal
   LIMIT 100 OFFSET greatest(0,p_offset)) q),
 'review_count',(SELECT count(*) FROM wholesale_ingest.records r
   JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id JOIN wholesale_ingest.sources s ON s.id=i.source_id
   WHERE r.review_reason IS NOT NULL AND r.resolved_at IS NULL AND (p_source_key IS NULL OR s.source_key=p_source_key)),
 'total_review_count',(SELECT count(*) FROM wholesale_ingest.records WHERE review_reason IS NOT NULL AND resolved_at IS NULL),
 'digest',(SELECT to_jsonb(d) FROM wholesale_ingest.daily_digests d WHERE day=p_day));
$$;
REVOKE ALL ON FUNCTION public.list_pipeline_snapshot_filtered(date,int,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_pipeline_snapshot_filtered(date,int,text) TO service_role;
-- Existing callers retain their all-source contract and gain stable pagination.
CREATE OR REPLACE FUNCTION public.list_pipeline_snapshot(p_day date,p_offset int DEFAULT 0) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT public.list_pipeline_snapshot_filtered(p_day,p_offset,NULL);
$$;
-- Accept only the exact Collin CAD daily owner/property dataset and matching
-- parcel query. No other data.texas.gov resource, query or county is allowed.
DO $evidence$
DECLARE definition text; revised text;
 needle text:='END)) THEN RAISE EXCEPTION ''Official county/title evidence required''; END IF;';
 replacement text:='END) OR (p_county=''Collin'' AND coalesce(identity->>''parcel_id'','''') ~ ''^[0-9]+$'' AND p_evidence_url = (''https://data.texas.gov/resource/ahis-pci3.json?propid='' || (identity->>''parcel_id'')))) THEN RAISE EXCEPTION ''Official county/title evidence required''; END IF;';
 address_needle text:='coalesce(length(trim(identity->>''property_address'')),0) NOT BETWEEN 1 AND 300 OR';
BEGIN
 definition:=pg_get_functiondef('public.resolve_reviewed_list_record(uuid,integer,integer,uuid,text,text,uuid,boolean,jsonb)'::regprocedure);
 IF strpos(definition,needle)=0 OR strpos(definition,address_needle)=0 THEN RAISE EXCEPTION 'Expected reviewed identity guards missing'; END IF;
 revised:=replace(definition,needle,replacement);
 revised:=replace(revised,address_needle,address_needle||' trim(identity->>''property_address'') ~ ''^0+$'' OR');
 EXECUTE revised;
END $evidence$;

COMMIT;
