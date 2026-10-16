BEGIN;
-- Minimal durable identity receipt: contains no owner/contact/address data and
-- survives raw-record retention so another import cannot become a new notice.
CREATE TABLE wholesale_ingest.foreclosure_first_seen (
 source_id uuid NOT NULL REFERENCES wholesale_ingest.sources,
 source_record_id text NOT NULL,
 first_seen_at timestamptz NOT NULL,
 PRIMARY KEY(source_id,source_record_id)
);
ALTER TABLE wholesale_ingest.foreclosure_first_seen ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.foreclosure_first_seen FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.foreclosure_first_seen TO wholesale_ingestor,wholesale_worker,service_role;
CREATE POLICY receipt_read ON wholesale_ingest.foreclosure_first_seen FOR SELECT TO wholesale_ingestor,wholesale_worker USING(true);
CREATE POLICY receipt_insert ON wholesale_ingest.foreclosure_first_seen FOR INSERT TO wholesale_ingestor,wholesale_worker WITH CHECK(true);
INSERT INTO wholesale_ingest.foreclosure_first_seen
 SELECT i.source_id,r.source_record_id,min(i.received_at)
 FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id
 JOIN wholesale_ingest.sources s ON s.id=i.source_id
 WHERE s.list_type='pre_foreclosure' AND nullif(trim(r.source_record_id),'') IS NOT NULL
 GROUP BY i.source_id,r.source_record_id;
CREATE FUNCTION wholesale_ingest.remember_foreclosure_notice() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 INSERT INTO wholesale_ingest.foreclosure_first_seen(source_id,source_record_id,first_seen_at)
 SELECT i.source_id,NEW.source_record_id,i.received_at FROM wholesale_ingest.ingest_runs i
 JOIN wholesale_ingest.sources s ON s.id=i.source_id
 WHERE i.id=NEW.run_id AND s.list_type='pre_foreclosure' AND nullif(trim(NEW.source_record_id),'') IS NOT NULL
 ON CONFLICT DO NOTHING;
 RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION wholesale_ingest.remember_foreclosure_notice() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER remember_foreclosure_notice AFTER INSERT ON wholesale_ingest.records
 FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.remember_foreclosure_notice();
CREATE INDEX records_notice_lookup ON wholesale_ingest.records(source_record_id,run_id);
CREATE FUNCTION public.foreclosure_daily_actions(p_day date,p_county text DEFAULT NULL,p_offset int DEFAULT 0)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 WITH notices AS (
 SELECT f.*,s.county,s.source_key FROM wholesale_ingest.foreclosure_first_seen f
 JOIN wholesale_ingest.sources s ON s.id=f.source_id
 WHERE (p_county IS NULL OR s.county=p_county)
 AND f.first_seen_at < (p_day+1)::timestamp AT TIME ZONE 'America/Chicago'
 ), pending AS (
 SELECT n.*,r.run_id,r.batch_index,r.ordinal,r.review_reason,r.record,
 (n.first_seen_at AT TIME ZONE 'America/Chicago')::date=p_day AS new_today
 FROM notices n JOIN LATERAL (
 SELECT r.* FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs i ON i.id=r.run_id
 WHERE i.source_id=n.source_id AND r.source_record_id=n.source_record_id
 AND r.resolved_at IS NULL AND r.review_reason IS NOT NULL
 ORDER BY i.received_at DESC,r.run_id,r.batch_index,r.ordinal LIMIT 1
 ) r ON true
 WHERE NOT EXISTS(SELECT 1 FROM wholesale_ingest.records done JOIN wholesale_ingest.ingest_runs i ON i.id=done.run_id
 WHERE i.source_id=n.source_id AND done.source_record_id=n.source_record_id AND done.resolved_at IS NOT NULL)
 ), page AS (
 SELECT source_id,source_key,county,source_record_id,first_seen_at,new_today,run_id,batch_index,ordinal,review_reason,
 record->>'property_address' AS property_address,record->>'city' AS city,record->>'state' AS state,
 record->>'zip' AS zip,record->>'parcel_id' AS parcel_id,record->>'unit' AS unit,
 record->>'source_url' AS source_url,md5(record::text) AS source_fingerprint,
 record->'raw'->>'indexed_address' AS indexed_address,record->>'filed_date' AS filed_date,
 record->>'auction_date' AS auction_date
 FROM pending ORDER BY new_today DESC,first_seen_at DESC,source_id,source_record_id
 LIMIT 50 OFFSET greatest(p_offset,0)
 ) SELECT jsonb_build_object('day',p_day,'total',(SELECT count(*) FROM pending),
 'new_today',(SELECT count(*) FROM pending WHERE new_today),
 'backlog',(SELECT count(*) FROM pending WHERE NOT new_today),
 'items',(SELECT coalesce(jsonb_agg(to_jsonb(page)),'[]') FROM page));
$$;
REVOKE ALL ON FUNCTION public.foreclosure_daily_actions(date,text,int) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.foreclosure_daily_actions(date,text,int) TO service_role;
COMMIT;
