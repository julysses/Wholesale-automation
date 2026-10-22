-- Candidate only. Retain edits/deletes atomically; never replay against production.
CREATE TABLE private.buyer_mutation_receipts (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL, kind text CHECK(kind IN ('update','delete')),
 buyer_id uuid, expected jsonb, patch jsonb, snapshot jsonb,
 transaction_count integer NOT NULL DEFAULT 0,
 outcome text NOT NULL CHECK(outcome IN ('updated','deleted','stale','missing','canceled')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE private.buyer_mutation_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_mutation_receipts FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON private.buyer_mutation_receipts TO service_role;
CREATE TRIGGER buyer_mutation_receipt_immutable BEFORE UPDATE OR DELETE ON private.buyer_mutation_receipts
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();

CREATE FUNCTION public.buyer_mutation_receipt(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_mutation_receipts;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 SELECT * INTO r FROM private.buyer_mutation_receipts WHERE id=p_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('id',p_id,'state','pending'); END IF;
 IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request owner mismatch' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('id',p_id,'state',r.outcome,'kind',r.kind,'buyer_id',r.buyer_id,
 'buyer',r.snapshot,'transaction_count',r.transaction_count,
 'current_exists',EXISTS(SELECT 1 FROM public.buyers WHERE id=r.buyer_id));
END $$;

CREATE FUNCTION public.cancel_buyer_mutation(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_id IS NULL THEN RAISE EXCEPTION 'Invalid request' USING ERRCODE='22023'; END IF;
 PERFORM public.buyer_mutation_receipt(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-mutation:'||p_id::text,0));
 INSERT INTO private.buyer_mutation_receipts(id,operator_id,outcome) VALUES(p_id,p_operator,'canceled') ON CONFLICT DO NOTHING;
 RETURN public.buyer_mutation_receipt(p_id,p_operator);
END $$;

CREATE FUNCTION public.mutate_buyer(p_id uuid,p_operator uuid,p_kind text,p_buyer uuid,p_expected jsonb,p_patch jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_mutation_receipts; b public.buyers; data jsonb; cols text; state text; count_tx int:=0;
 fields text[]:=ARRAY['first_name','last_name','company','email','phone','source','tier','target_zips',
 'min_price','max_price','strategy','property_types','close_speed_days','pof_verified','pof_amount',
 'notes','active','buys_land','buys_infill','land_buyer_type'];
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_buyer IS NULL OR p_kind NOT IN ('update','delete') OR p_kind IS NULL
 OR jsonb_typeof(p_expected) IS DISTINCT FROM 'object' OR p_expected->>'id' IS DISTINCT FROM p_buyer::text
 OR jsonb_typeof(p_patch) IS DISTINCT FROM 'object' OR octet_length(p_expected::text)+octet_length(p_patch::text)>100000
 THEN RAISE EXCEPTION 'Invalid buyer mutation' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_patch) k WHERE NOT k=ANY(fields))
 OR (p_kind='delete' AND p_patch<>'{}'::jsonb)
 OR (p_kind='update' AND (nullif(btrim(p_patch->>'first_name'),'') IS NULL OR nullif(btrim(p_patch->>'last_name'),'') IS NULL))
 THEN RAISE EXCEPTION 'Invalid editable fields' USING ERRCODE='22023'; END IF;
 IF p_kind='update' AND (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(p_patch) k) IS DISTINCT FROM
 (SELECT array_agg(k ORDER BY k) FROM unnest(fields) k)
 THEN RAISE EXCEPTION 'All profile fields must be explicit' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-mutation:'||p_id::text,0));
 SELECT * INTO r FROM private.buyer_mutation_receipts WHERE id=p_id;
 IF FOUND THEN
  IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request owner mismatch' USING ERRCODE='42501'; END IF;
  IF r.outcome<>'canceled' AND (r.kind<>p_kind OR r.buyer_id<>p_buyer OR r.expected<>p_expected OR r.patch<>p_patch)
  THEN RAISE EXCEPTION 'Original mutation changed' USING ERRCODE='22023'; END IF;
  RETURN public.buyer_mutation_receipt(p_id,p_operator);
 END IF;
 PERFORM set_config('lock_timeout','3s',true);
 -- Short identity decision also serializes with manual creates and CSV imports.
 LOCK TABLE public.buyers IN SHARE ROW EXCLUSIVE MODE;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 state:=CASE WHEN NOT FOUND THEN 'missing' WHEN to_jsonb(b)<>p_expected THEN 'stale'
             WHEN p_kind='update' THEN 'updated' ELSE 'deleted' END;
 IF state='updated' THEN
  IF EXISTS(SELECT 1 FROM public.buyers x WHERE x.id<>p_buyer AND
    ((private.buyer_phone(p_patch->>'phone') IS NOT NULL AND private.buyer_phone(x.phone)=private.buyer_phone(p_patch->>'phone'))
    OR (nullif(lower(btrim(p_patch->>'email')),'') IS NOT NULL AND lower(btrim(x.email))=lower(btrim(p_patch->>'email')))))
  THEN RAISE EXCEPTION 'Buyer identity requires review' USING ERRCODE='23505'; END IF;
  data:=p_patch;
  -- Consent is tied to its recipient; contact changes can revoke, never grant it.
  IF private.buyer_phone(b.phone) IS DISTINCT FROM private.buyer_phone(p_patch->>'phone') THEN data:=data||'{"sms_opt_in":false}'::jsonb; END IF;
  IF nullif(lower(btrim(b.email)),'') IS DISTINCT FROM nullif(lower(btrim(p_patch->>'email')),'') THEN data:=data||'{"email_opt_in":false}'::jsonb; END IF;
  SELECT string_agg(format('%I',k),',' ORDER BY k) INTO cols FROM jsonb_object_keys(data) k;
  EXECUTE format('UPDATE public.buyers SET (%s)=(SELECT %s FROM jsonb_populate_record(NULL::public.buyers,$1)) WHERE id=$2 RETURNING *',cols,cols)
  INTO b USING data,p_buyer;
 ELSIF state='deleted' THEN
  SELECT count(*) INTO count_tx FROM public.buyer_transactions WHERE buyer_id=p_buyer;
  DELETE FROM public.buyers WHERE id=p_buyer;
 END IF;
 INSERT INTO private.buyer_mutation_receipts(id,operator_id,kind,buyer_id,expected,patch,snapshot,transaction_count,outcome)
 VALUES(p_id,p_operator,p_kind,p_buyer,p_expected,p_patch,CASE WHEN b.id IS NOT NULL THEN to_jsonb(b) END,count_tx,state);
 RETURN public.buyer_mutation_receipt(p_id,p_operator);
END $$;
DO $$ DECLARE f regprocedure; BEGIN
 FOR f IN SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname=ANY(ARRAY['buyer_mutation_receipt','cancel_buyer_mutation','mutate_buyer']) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',f);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',f);
 END LOOP;
END $$;
