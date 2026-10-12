-- Bind enrichment to current verified CRM input and store contacts with billing atomically.
ALTER TABLE wholesale_ingest.skip_trace_requests ADD COLUMN input_snapshot jsonb;
CREATE FUNCTION wholesale_ingest.protect_trace_snapshot() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF OLD.input_snapshot IS NOT NULL AND NEW.input_snapshot IS DISTINCT FROM OLD.input_snapshot THEN RAISE EXCEPTION 'Trace input snapshot is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.protect_trace_snapshot() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER trace_snapshot_immutable BEFORE UPDATE ON wholesale_ingest.skip_trace_requests FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.protect_trace_snapshot();
ALTER TABLE wholesale_ingest.contacts ADD COLUMN trace_request_id uuid REFERENCES wholesale_ingest.skip_trace_requests(id), ADD COLUMN trace_ordinal integer;
CREATE UNIQUE INDEX trace_contact_receipt ON wholesale_ingest.contacts(trace_request_id,trace_ordinal) WHERE trace_request_id IS NOT NULL;

CREATE FUNCTION public.list_trace_input(p_lead uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE l jsonb; property wholesale_ingest.properties; doc jsonb;
BEGIN
 SELECT to_jsonb(leads) INTO l FROM public.leads WHERE id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','lead_missing'); END IF;
 SELECT * INTO property FROM wholesale_ingest.properties WHERE lead_id=p_lead;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','unverified_pipeline_property'); END IF;
 IF coalesce(nullif(trim(l->>'owner_phone_1'),''),nullif(trim(l->>'owner_phone_2'),''),nullif(trim(l->>'owner_phone_3'),''),nullif(trim(l->>'owner_email'),'')) IS NOT NULL
 OR EXISTS(SELECT 1 FROM wholesale_ingest.contacts WHERE lead_id=p_lead AND expires_at>clock_timestamp())
 THEN RETURN jsonb_build_object('blocked','already_enriched'); END IF;
 doc:=jsonb_build_object('owner_name',coalesce(nullif(trim(concat_ws(' ',l->>'owner_first_name',l->>'owner_last_name')),''),l->>'owner_name'),
  'property_address',l->>'property_address','city',coalesce(nullif(l->>'city',''),property.city),
  'state',property.state,'county',property.county,'property_id',property.id,'parcel_id',property.parcel_id,
  'zip_code',coalesce(nullif(l->>'zip_code',''),property.zip));
 IF coalesce(length(trim(doc->>'owner_name')),0)=0 OR coalesce(length(trim(doc->>'property_address')),0)=0
 OR coalesce(length(trim(doc->>'city')),0)=0 THEN RETURN jsonb_build_object('blocked','identity_incomplete'); END IF;
 RETURN jsonb_build_object('input',doc,'input_hash',encode(sha256(convert_to(doc::text,'UTF8')),'hex'));
END $$;
CREATE FUNCTION public.prepare_list_trace(p_id uuid,p_lead uuid,p_provider text,p_max_cents integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE snapshot jsonb; result jsonb; saved wholesale_ingest.skip_trace_requests;
BEGIN
 IF p_id IS NULL OR p_lead IS NULL THEN RETURN jsonb_build_object('blocked','invalid_request'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-lead:'||p_lead::text,0));
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id IS DISTINCT FROM p_lead OR saved.provider IS DISTINCT FROM p_provider OR saved.reserved_cents IS DISTINCT FROM p_max_cents
  THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('request',to_jsonb(saved),'input',saved.input_snapshot,'replayed',true,'dispatch',false,
   'contacts_saved',(SELECT count(*) FROM wholesale_ingest.contacts WHERE trace_request_id=p_id));
 END IF;
 snapshot:=public.list_trace_input(p_lead);
 IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
 result:=public.reserve_list_trace(p_id,p_lead,p_provider,snapshot->>'input_hash',p_max_cents);
 IF result ? 'blocked' THEN RETURN result; END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET input_snapshot=snapshot->'input' WHERE id=p_id RETURNING * INTO saved;
 RETURN result||jsonb_build_object('request',to_jsonb(saved),'input',snapshot->'input');
END $$;
CREATE OR REPLACE FUNCTION public.claim_list_trace(p_id uuid,p_input_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests; snapshot jsonb;
BEGIN
 IF coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$' THEN RETURN jsonb_build_object('blocked','invalid_input_identity'); END IF;
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF saved.input_snapshot IS NULL THEN RETURN jsonb_build_object('blocked','input_snapshot_missing'); END IF;
 IF saved.input_hash IS DISTINCT FROM p_input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 IF saved.state<>'reserved' THEN RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',false); END IF;
 IF saved.spend_day<>(clock_timestamp() AT TIME ZONE 'America/Chicago')::date THEN RETURN jsonb_build_object('blocked','reservation_expired'); END IF;
 snapshot:=public.list_trace_input(saved.lead_id);
 IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
 IF snapshot->>'input_hash'<>saved.input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET state='submitted' WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('request',to_jsonb(saved),'input',snapshot->'input','dispatch',true);
END $$;
CREATE FUNCTION public.complete_list_trace(p_id uuid,p_provider text,p_input_hash text,p_actual_cents integer,p_provider_receipt text,p_contacts jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests; snapshot jsonb; item jsonb; result jsonb; ordinal integer:=0; fingerprint text;
BEGIN
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF saved.provider IS DISTINCT FROM p_provider OR saved.input_hash IS DISTINCT FROM p_input_hash
 THEN RETURN jsonb_build_object('blocked','receipt_identity_mismatch'); END IF;
 IF jsonb_typeof(p_contacts) IS DISTINCT FROM 'array' THEN RETURN jsonb_build_object('blocked','invalid_contacts'); END IF;
 IF jsonb_array_length(p_contacts)>20 THEN RETURN jsonb_build_object('blocked','invalid_contacts'); END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_contacts) LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR item-ARRAY['phone','email','phone_type','name']<>'{}'::jsonb
  OR (item->>'phone' IS NULL AND item->>'email' IS NULL)
  OR (item->>'phone' IS NOT NULL AND (jsonb_typeof(item->'phone')<>'string' OR item->>'phone' !~ '^\+1[2-9][0-9]{9}$'))
  OR (item->>'email' IS NOT NULL AND (jsonb_typeof(item->'email')<>'string' OR length(item->>'email')>320 OR item->>'email' !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'))
  OR (item->>'name' IS NOT NULL AND (jsonb_typeof(item->'name')<>'string' OR length(item->>'name')>200))
  OR coalesce(item->>'phone_type','unknown') NOT IN ('mobile','landline','voip','unknown')
  THEN RETURN jsonb_build_object('blocked','invalid_contacts'); END IF;
 END LOOP;
 fingerprint:=encode(sha256(convert_to(p_contacts::text,'UTF8')),'hex');
 IF saved.state<>'completed' THEN
  snapshot:=public.list_trace_input(saved.lead_id);
  IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
  IF snapshot->>'input_hash'<>saved.input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 END IF;
 result:=public.settle_list_trace(p_id,'completed',p_actual_cents,p_provider_receipt,fingerprint);
 IF result ? 'blocked' THEN RETURN result; END IF;
 IF result->>'replayed'='false' THEN
  FOR item IN SELECT value FROM jsonb_array_elements(p_contacts) LOOP
   INSERT INTO wholesale_ingest.contacts(lead_id,provider,traced_at,expires_at,name,phone,email,phone_type,dnc_status,trace_request_id,trace_ordinal)
   VALUES(saved.lead_id,saved.provider,clock_timestamp(),clock_timestamp()+interval '30 days',item->>'name',item->>'phone',item->>'email',coalesce(item->>'phone_type','unknown'),'unknown',p_id,ordinal);
   ordinal:=ordinal+1;
  END LOOP;
 END IF;
 IF (SELECT count(*) FROM wholesale_ingest.contacts WHERE trace_request_id=p_id)<>jsonb_array_length(p_contacts)
 THEN RAISE EXCEPTION 'Trace contact persistence mismatch'; END IF;
 RETURN result||jsonb_build_object('contacts_saved',jsonb_array_length(p_contacts));
END $$;
REVOKE ALL ON FUNCTION public.list_trace_input(uuid),public.prepare_list_trace(uuid,uuid,text,integer),public.complete_list_trace(uuid,text,text,integer,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_trace_input(uuid),public.prepare_list_trace(uuid,uuid,text,integer),public.complete_list_trace(uuid,text,text,integer,text,jsonb) TO service_role;
