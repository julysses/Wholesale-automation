BEGIN;
CREATE TABLE wholesale_ingest.propstream_batches (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL REFERENCES public.profiles,
 payload_hash text NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE wholesale_ingest.propstream_batches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.propstream_batches FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.propstream_batches TO service_role;
CREATE FUNCTION public.propstream_bulk_action(p_batch uuid,p_operator uuid,p_items jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE old wholesale_ingest.propstream_batches; item jsonb; results jsonb:='[]'; result jsonb; fingerprint text; action text; quote bigint; balance bigint;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_batch IS NULL OR jsonb_typeof(p_items) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Batch items required'; END IF;
 IF jsonb_array_length(p_items) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Batch requires 1 to 500 leads'; END IF;
 fingerprint:=encode(sha256(convert_to(p_items::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('propstream-batch:'||p_batch::text,0));
 IF EXISTS(SELECT 1 FROM wholesale_ingest.propstream_abandoned_events WHERE id=p_batch) THEN RAISE EXCEPTION 'Batch abandoned during recovery'; END IF;
 SELECT * INTO old FROM wholesale_ingest.propstream_batches WHERE id=p_batch;
 IF FOUND THEN
  IF old.operator_id<>p_operator OR old.payload_hash<>fingerprint THEN RAISE EXCEPTION 'Batch reference conflict'; END IF;
  RETURN old.result||jsonb_build_object('replayed',true,'dispatch',false);
 END IF;
 SELECT min(v->>'action') INTO action FROM jsonb_array_elements(p_items) v;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_items) v WHERE v->>'action' IS DISTINCT FROM action)
 OR (SELECT count(DISTINCT v->>'lead_id') FROM jsonb_array_elements(p_items) v)<>jsonb_array_length(p_items)
 OR (SELECT count(DISTINCT v->>'event_id') FROM jsonb_array_elements(p_items) v)<>jsonb_array_length(p_items)
 OR (SELECT count(DISTINCT v->>'request_id') FROM jsonb_array_elements(p_items) v)<>jsonb_array_length(p_items)
 THEN RAISE EXCEPTION 'One action and unique lead, request and event per batch required'; END IF;
 IF action='prepare' THEN
  SELECT sum((v->'payload'->>'quote_cents')::bigint),min((v->'payload'->>'prepaid_balance_cents')::bigint) INTO quote,balance FROM jsonb_array_elements(p_items) v;
  IF quote>balance OR quote>5000 THEN RAISE EXCEPTION 'Batch quote exceeds confirmed balance or total cap'; END IF;
 END IF;
 -- All member locks are ordered; one failed row rolls back every member.
 FOR item IN SELECT v FROM jsonb_array_elements(p_items) v ORDER BY v->>'lead_id' LOOP
  result:=public.propstream_handoff_action((item->>'event_id')::uuid,p_operator,(item->>'request_id')::uuid,(item->>'lead_id')::uuid,item->>'action',item->'payload');
  IF coalesce((result->>'replayed')::boolean,false) THEN RAISE EXCEPTION 'Member action already used; recover its original batch'; END IF;
  IF action='start' AND result->'dispatch' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'Batch member is not newly submitted'; END IF;
  results:=results||jsonb_build_array(result);
 END LOOP;
 result:=jsonb_build_object('batch_id',p_batch,'operator_id',p_operator,'action',action,'count',jsonb_array_length(p_items),'results',results,'dispatch',action='start','replayed',false,'outreach_authorized',false);
 INSERT INTO wholesale_ingest.propstream_batches(id,operator_id,payload_hash,result) VALUES(p_batch,p_operator,fingerprint,result);
 RETURN result;
END $$;
CREATE FUNCTION public.propstream_bulk_recover(p_batch uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE old wholesale_ingest.propstream_batches;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('propstream-batch:'||p_batch::text,0));
 SELECT * INTO old FROM wholesale_ingest.propstream_batches WHERE id=p_batch;
 IF FOUND AND old.operator_id<>p_operator THEN RAISE EXCEPTION 'Actor mismatch'; END IF;
 IF old.id IS NULL THEN
  INSERT INTO wholesale_ingest.propstream_abandoned_events(id,operator_id) VALUES(p_batch,p_operator) ON CONFLICT DO NOTHING;
  IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.propstream_abandoned_events WHERE id=p_batch AND operator_id=p_operator) THEN RAISE EXCEPTION 'Actor mismatch'; END IF;
 END IF;
 RETURN jsonb_build_object('batch_id',p_batch,'settled',true,'result',old.result);
END $$;
REVOKE ALL ON FUNCTION public.propstream_bulk_action(uuid,uuid,jsonb),public.propstream_bulk_recover(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.propstream_bulk_action(uuid,uuid,jsonb),public.propstream_bulk_recover(uuid,uuid) TO service_role;
COMMIT;
