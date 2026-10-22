-- Candidate only. Preserve existing rows; new manual records grant no outreach consent.
ALTER TABLE public.buyers ALTER COLUMN sms_opt_in SET DEFAULT false;
ALTER TABLE public.buyers ALTER COLUMN email_opt_in SET DEFAULT false;
CREATE TABLE private.buyer_manual_receipts (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL, payload jsonb,
 outcome text NOT NULL CHECK(outcome IN ('saved','canceled')), snapshot jsonb,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK ((outcome='saved' AND payload IS NOT NULL AND snapshot IS NOT NULL)
     OR (outcome='canceled' AND payload IS NULL AND snapshot IS NULL))
);
ALTER TABLE private.buyer_manual_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_manual_receipts FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON private.buyer_manual_receipts TO service_role;
CREATE TRIGGER buyer_manual_receipt_immutable BEFORE UPDATE OR DELETE ON private.buyer_manual_receipts
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();

CREATE FUNCTION public.manual_buyer_receipt(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_manual_receipts;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 SELECT * INTO r FROM private.buyer_manual_receipts WHERE id=p_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('id',p_id,'state','pending','saved',false); END IF;
 IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request belongs to another operator' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('id',p_id,'state',r.outcome,'saved',r.outcome='saved',
   'buyer_id',CASE WHEN r.outcome='saved' THEN p_id END,'buyer',r.snapshot,
   'current_exists',EXISTS(SELECT 1 FROM public.buyers WHERE id=p_id));
END $$;
REVOKE ALL ON FUNCTION public.manual_buyer_receipt(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.manual_buyer_receipt(uuid,uuid) TO service_role;

CREATE FUNCTION public.cancel_manual_buyer(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('manual-buyer:'||p_id::text,0));
 IF NOT EXISTS(SELECT 1 FROM private.buyer_manual_receipts WHERE id=p_id) THEN
   INSERT INTO private.buyer_manual_receipts(id,operator_id,outcome) VALUES(p_id,p_operator,'canceled');
 END IF;
 -- Recover a committed save, never delete it. Cancellation blocks a late POST.
 RETURN public.manual_buyer_receipt(p_id,p_operator);
END $$;
REVOKE ALL ON FUNCTION public.cancel_manual_buyer(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_manual_buyer(uuid,uuid) TO service_role;

CREATE FUNCTION public.create_manual_buyer(p_id uuid,p_operator uuid,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_manual_receipts; b public.buyers; columns_sql text; data jsonb;
 fields text[]:=ARRAY['first_name','last_name','company','email','phone','source','tier','target_zips',
 'min_price','max_price','strategy','property_types','close_speed_days','pof_verified','pof_amount',
 'notes','active','buys_land','buys_infill','land_buyer_type']; v_phone text; v_email text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR octet_length(p_payload::text)>30000
 THEN RAISE EXCEPTION 'Invalid manual buyer' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('manual-buyer:'||p_id::text,0));
 SELECT * INTO r FROM private.buyer_manual_receipts WHERE id=p_id;
 IF FOUND THEN
   IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request belongs to another operator' USING ERRCODE='42501'; END IF;
   IF r.outcome='saved' AND r.payload<>p_payload THEN RAISE EXCEPTION 'Request details changed' USING ERRCODE='22023'; END IF;
   RETURN public.manual_buyer_receipt(p_id,p_operator);
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_payload) k WHERE NOT k=ANY(fields))
 OR nullif(btrim(p_payload->>'first_name'),'') IS NULL OR nullif(btrim(p_payload->>'last_name'),'') IS NULL
 THEN RAISE EXCEPTION 'Invalid manual buyer fields' USING ERRCODE='22023'; END IF;
 PERFORM set_config('lock_timeout','3s',true);
 -- Also serialize with CSV imports and browser writes during identity review.
 LOCK TABLE public.buyers IN SHARE ROW EXCLUSIVE MODE;
 v_phone:=private.buyer_phone(p_payload->>'phone');v_email:=nullif(lower(btrim(p_payload->>'email')),'');
 IF EXISTS(SELECT 1 FROM public.buyers x WHERE
   (v_phone IS NOT NULL AND private.buyer_phone(x.phone)=v_phone)
   OR (v_email IS NOT NULL AND lower(btrim(x.email))=v_email)
   OR (v_phone IS NULL AND v_email IS NULL AND lower(btrim(x.first_name))=lower(btrim(p_payload->>'first_name'))
       AND lower(btrim(x.last_name))=lower(btrim(p_payload->>'last_name'))))
 THEN RAISE EXCEPTION 'Existing buyer identity requires review' USING ERRCODE='23505'; END IF;
 data:=p_payload||jsonb_build_object('id',p_id,'sms_opt_in',false,'email_opt_in',false);
 SELECT string_agg(format('%I',k),',' ORDER BY k) INTO columns_sql FROM jsonb_object_keys(data) k;
 EXECUTE format('INSERT INTO public.buyers(%s) SELECT %s FROM jsonb_populate_record(NULL::public.buyers,$1) RETURNING *',columns_sql,columns_sql)
 INTO b USING data;
 INSERT INTO private.buyer_manual_receipts(id,operator_id,payload,outcome,snapshot)
 VALUES(p_id,p_operator,p_payload,'saved',to_jsonb(b));
 RETURN public.manual_buyer_receipt(p_id,p_operator);
END $$;
REVOKE ALL ON FUNCTION public.create_manual_buyer(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.create_manual_buyer(uuid,uuid,jsonb) TO service_role;
