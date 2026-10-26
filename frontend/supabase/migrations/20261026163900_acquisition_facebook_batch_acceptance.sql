-- One durable transaction for one signed delivery, no worker/provider execution.
BEGIN;
CREATE FUNCTION private.accept_facebook_acquisition_batch(p_events jsonb,p_raw_body bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE event jsonb; receipts jsonb:='[]'::jsonb;
BEGIN
 IF p_events IS NULL OR jsonb_typeof(p_events)<>'array' THEN RAISE EXCEPTION 'Invalid Facebook batch' USING ERRCODE='22023'; END IF;
 IF jsonb_array_length(p_events) NOT BETWEEN 1 AND 100 OR octet_length(p_events::text)>1048576 THEN
  RAISE EXCEPTION 'Invalid Facebook batch size' USING ERRCODE='22023'; END IF;
 -- Deterministic lock order across simultaneous overlapping deliveries.
 FOR event IN SELECT value FROM jsonb_array_elements(p_events) ORDER BY value->>'page_id',value->>'leadgen_id',value::text LOOP
  IF jsonb_typeof(event)<>'object' OR coalesce(event->>'page_id','')!~'^[0-9]{1,200}$'
   OR coalesce(event->>'leadgen_id','')!~'^[0-9]{1,200}$' OR coalesce(event->>'form_id','')!~'^[0-9]{1,200}$' THEN
   RAISE EXCEPTION 'Invalid native event identity' USING ERRCODE='22023'; END IF;
  receipts:=receipts||jsonb_build_array(private.accept_acquisition_event('facebook',event->>'page_id',event->>'leadgen_id','leadgen',event,p_raw_body));
 END LOOP;
 RETURN receipts;
END $$;
CREATE FUNCTION public.accept_facebook_acquisition_batch(p_events jsonb,p_raw_body bytea)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.accept_facebook_acquisition_batch(p_events,p_raw_body) $$;
REVOKE ALL ON FUNCTION private.accept_facebook_acquisition_batch(jsonb,bytea),public.accept_facebook_acquisition_batch(jsonb,bytea) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.accept_facebook_acquisition_batch(jsonb,bytea),public.accept_facebook_acquisition_batch(jsonb,bytea) TO service_role;
COMMIT;
