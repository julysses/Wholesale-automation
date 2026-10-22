-- Candidate only: retained operator requests; PostgreSQL never calls an AI provider.
CREATE TABLE private.buyer_analysis_requests (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('score','classify')),
 selected_buyer uuid, paid_confirmed boolean NOT NULL, targets uuid[] NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), CHECK(cardinality(targets)<=20000)
);
CREATE TABLE private.buyer_analysis_claims (
 request_id uuid REFERENCES private.buyer_analysis_requests(id), buyer_id uuid, claim_id uuid NOT NULL UNIQUE,
 snapshot jsonb, blocked boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(request_id,buyer_id), CHECK((blocked AND snapshot IS NULL) OR (NOT blocked AND snapshot IS NOT NULL))
);
CREATE INDEX buyer_analysis_claim_buyer ON private.buyer_analysis_claims(buyer_id);
CREATE TABLE private.buyer_analysis_authorizations (
 request_id uuid, buyer_id uuid, claim_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(request_id,buyer_id),
 FOREIGN KEY(request_id,buyer_id) REFERENCES private.buyer_analysis_claims(request_id,buyer_id)
);
CREATE TABLE private.buyer_analysis_results (
 request_id uuid, buyer_id uuid, claim_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN ('valid','invalid','failed','unknown','stale','missing')),
 patch jsonb NOT NULL, metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(request_id,buyer_id), FOREIGN KEY(request_id,buyer_id) REFERENCES private.buyer_analysis_claims(request_id,buyer_id)
);
CREATE TABLE private.buyer_analysis_commits (
 request_id uuid, buyer_id uuid, state text NOT NULL CHECK(state IN ('applied','failed','unknown','stale','missing','canceled')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(request_id,buyer_id),
 FOREIGN KEY(request_id,buyer_id) REFERENCES private.buyer_analysis_results(request_id,buyer_id)
);
CREATE TABLE private.buyer_analysis_cancellations (
 request_id uuid PRIMARY KEY, operator_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['buyer_analysis_requests','buyer_analysis_claims','buyer_analysis_authorizations',
 'buyer_analysis_results','buyer_analysis_commits','buyer_analysis_cancellations'] LOOP
  EXECUTE format('ALTER TABLE private.%I ENABLE ROW LEVEL SECURITY',name);
  EXECUTE format('REVOKE ALL ON private.%I FROM PUBLIC,anon,authenticated,service_role',name);
  EXECUTE format('GRANT SELECT,INSERT ON private.%I TO service_role',name);
  EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON private.%I FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import()',name||'_immutable',name);
 END LOOP;
END $$;

CREATE FUNCTION private.buyer_analysis_snapshot(p_buyer uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object('buyer',(SELECT to_jsonb(b) FROM public.buyers b WHERE b.id=p_buyer),
 'transactions',coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id) FROM public.buyer_transactions t WHERE t.buyer_id=p_buyer),'[]'::jsonb));
$$;
REVOKE ALL ON FUNCTION private.buyer_analysis_snapshot(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.buyer_analysis_snapshot(uuid) TO service_role;

CREATE FUNCTION public.buyer_analysis_status(p_id uuid,p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_analysis_requests; v_done int; v_applied int; v_failed int; v_stale int; v_missing int;
 v_unknown int; v_blocked int; v_held int; v_ready int; v_next jsonb; v_items jsonb; v_stopped boolean; v_state text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id AND operator_id<>p_operator)
 THEN RAISE EXCEPTION 'Request owner mismatch' USING ERRCODE='42501'; END IF;
 v_stopped:=EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id);
 SELECT * INTO r FROM private.buyer_analysis_requests WHERE id=p_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('id',p_id,'state',CASE WHEN v_stopped THEN 'stopped' ELSE 'unconfirmed' END); END IF;
 IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request owner mismatch' USING ERRCODE='42501'; END IF;
 IF p_offset<0 OR p_offset>20000 THEN RAISE EXCEPTION 'Invalid result page' USING ERRCODE='22023'; END IF;
 SELECT count(*) FILTER(WHERE m.request_id IS NOT NULL OR c.blocked),count(*) FILTER(WHERE m.state='applied'),
 count(*) FILTER(WHERE m.state='failed'),count(*) FILTER(WHERE m.state='stale'),count(*) FILTER(WHERE m.state='missing'),
 count(*) FILTER(WHERE m.state='unknown'),count(*) FILTER(WHERE c.blocked),
 count(*) FILTER(WHERE r.kind='classify' AND c.request_id IS NOT NULL AND NOT c.blocked AND o.request_id IS NULL),
 count(*) FILTER(WHERE o.request_id IS NOT NULL AND m.request_id IS NULL)
 INTO v_done,v_applied,v_failed,v_stale,v_missing,v_unknown,v_blocked,v_held,v_ready
 FROM unnest(r.targets) t(id) LEFT JOIN private.buyer_analysis_claims c ON c.request_id=p_id AND c.buyer_id=t.id
 LEFT JOIN private.buyer_analysis_results o ON o.request_id=p_id AND o.buyer_id=t.id
 LEFT JOIN private.buyer_analysis_commits m ON m.request_id=p_id AND m.buyer_id=t.id;
 SELECT coalesce(jsonb_agg(id ORDER BY n),'[]'::jsonb) INTO v_next FROM
 (SELECT t.id,t.n FROM unnest(r.targets) WITH ORDINALITY t(id,n)
 WHERE NOT EXISTS(SELECT 1 FROM private.buyer_analysis_commits m WHERE m.request_id=p_id AND m.buyer_id=t.id)
 AND NOT EXISTS(SELECT 1 FROM private.buyer_analysis_claims c WHERE c.request_id=p_id AND c.buyer_id=t.id AND c.blocked)
 ORDER BY t.n LIMIT 20) x;
 v_state:=CASE WHEN v_stopped THEN 'stopped' WHEN v_unknown>0 OR v_blocked>0 OR (v_held>0 AND v_ready=0) THEN 'review'
 WHEN v_done=cardinality(r.targets) THEN 'complete' ELSE 'running' END;
 SELECT coalesce(jsonb_agg(value ORDER BY n),'[]'::jsonb) INTO v_items FROM
 (SELECT t.n,jsonb_build_object('buyer_id',t.id,'name',coalesce(c.snapshot->'buyer'->>'first_name',b.first_name,'Deleted buyer')||' '||coalesce(c.snapshot->'buyer'->>'last_name',b.last_name,''),
 'state',coalesce(m.state,CASE WHEN c.blocked THEN 'blocked' WHEN o.request_id IS NOT NULL THEN 'ready' WHEN c.request_id IS NOT NULL THEN 'unconfirmed' ELSE 'pending' END),
 'metadata',coalesce(o.metadata,'{}'::jsonb)) value
 FROM unnest(r.targets) WITH ORDINALITY t(id,n) LEFT JOIN public.buyers b ON b.id=t.id
 LEFT JOIN private.buyer_analysis_claims c ON c.request_id=p_id AND c.buyer_id=t.id
 LEFT JOIN private.buyer_analysis_results o ON o.request_id=p_id AND o.buyer_id=t.id
 LEFT JOIN private.buyer_analysis_commits m ON m.request_id=p_id AND m.buyer_id=t.id
 ORDER BY t.n OFFSET p_offset LIMIT 20) page;
 RETURN jsonb_build_object('id',p_id,'kind',r.kind,'selected_buyer',r.selected_buyer,'state',v_state,
 'total',cardinality(r.targets),'processed',v_done,'applied',v_applied,'failed',v_failed,'stale',v_stale,'missing',v_missing,
 'unknown',v_unknown,'blocked',v_blocked,'held',v_held,'ready',v_ready,'pending',cardinality(r.targets)-v_done,'items',v_items,'offset',p_offset,
 'next_ids',v_next,'can_run',NOT v_stopped AND v_unknown=0 AND (r.kind='score' OR v_held=0 OR v_ready>0) AND jsonb_array_length(v_next)>0);
END $$;

CREATE FUNCTION public.start_buyer_analysis(p_id uuid,p_operator uuid,p_kind text,p_buyer uuid,p_confirmed boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_analysis_requests; ids uuid[];
BEGIN
 IF p_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF p_kind NOT IN ('score','classify') OR (p_kind='classify' AND (p_buyer IS NULL OR p_confirmed IS DISTINCT FROM true))
 THEN RAISE EXCEPTION 'Review one paid classification explicitly' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id) THEN RETURN public.buyer_analysis_status(p_id,p_operator); END IF;
 SELECT * INTO r FROM private.buyer_analysis_requests WHERE id=p_id;
 IF FOUND THEN
  IF r.operator_id<>p_operator THEN RAISE EXCEPTION 'Request owner mismatch' USING ERRCODE='42501'; END IF;
  IF r.kind<>p_kind OR r.selected_buyer IS DISTINCT FROM p_buyer OR r.paid_confirmed IS DISTINCT FROM p_confirmed THEN RAISE EXCEPTION 'Request scope changed' USING ERRCODE='22023'; END IF;
 ELSE
  SELECT coalesce(array_agg(b.id ORDER BY b.id),'{}'::uuid[]) INTO ids FROM public.buyers b
  WHERE (p_buyer IS NOT NULL AND b.id=p_buyer) OR (p_buyer IS NULL AND b.active IS TRUE);
  IF cardinality(ids)>20000 OR (p_buyer IS NOT NULL AND cardinality(ids)<>1) THEN RAISE EXCEPTION 'Buyer scope unavailable or too large' USING ERRCODE='22023'; END IF;
  INSERT INTO private.buyer_analysis_requests(id,operator_id,kind,selected_buyer,paid_confirmed,targets) VALUES(p_id,p_operator,p_kind,p_buyer,p_confirmed,ids);
 END IF;
 RETURN public.buyer_analysis_status(p_id,p_operator);
END $$;

CREATE FUNCTION public.cancel_buyer_analysis(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 PERFORM public.buyer_analysis_status(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 INSERT INTO private.buyer_analysis_cancellations(request_id,operator_id) VALUES(p_id,p_operator) ON CONFLICT DO NOTHING;
 RETURN public.buyer_analysis_status(p_id,p_operator);
END $$;

CREATE FUNCTION public.claim_buyer_analysis(p_id uuid,p_operator uuid,p_buyer uuid,p_claim uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r private.buyer_analysis_requests; c private.buyer_analysis_claims; snap jsonb; v_blocked boolean:=false; v_new boolean:=false;
BEGIN
 PERFORM public.buyer_analysis_status(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 SELECT * INTO r FROM private.buyer_analysis_requests WHERE id=p_id;
 IF r.id IS NULL OR NOT (p_buyer=ANY(r.targets)) OR p_claim IS NULL THEN RAISE EXCEPTION 'Invalid analysis member' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id) THEN RETURN jsonb_build_object('stopped',true); END IF;
 SELECT * INTO c FROM private.buyer_analysis_claims WHERE request_id=p_id AND buyer_id=p_buyer;
 IF NOT FOUND THEN
  IF r.kind='classify' THEN
   PERFORM pg_advisory_xact_lock(hashtextextended('buyer-classification:'||p_buyer::text,0));
   SELECT EXISTS(SELECT 1 FROM private.buyer_analysis_claims x JOIN private.buyer_analysis_requests q ON q.id=x.request_id
    LEFT JOIN private.buyer_analysis_results o ON o.request_id=x.request_id AND o.buyer_id=x.buyer_id
    WHERE x.buyer_id=p_buyer AND q.kind='classify' AND NOT x.blocked AND
    (o.state='unknown' OR (o.request_id IS NULL AND
     (EXISTS(SELECT 1 FROM private.buyer_analysis_authorizations a WHERE a.request_id=x.request_id AND a.buyer_id=x.buyer_id)
      OR NOT EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations z WHERE z.request_id=x.request_id))))) INTO v_blocked;
  END IF;
  IF NOT v_blocked THEN
   snap:=private.buyer_analysis_snapshot(p_buyer);
   IF octet_length(snap::text)>5000000 THEN RAISE EXCEPTION 'Complete buyer input exceeds analysis bound' USING ERRCODE='22023'; END IF;
  END IF;
  INSERT INTO private.buyer_analysis_claims(request_id,buyer_id,claim_id,snapshot,blocked) VALUES(p_id,p_buyer,p_claim,snap,v_blocked) RETURNING * INTO c;
  v_new:=true;
 END IF;
 RETURN jsonb_build_object('owned',v_new,'kind',r.kind,'blocked',c.blocked,'claim_id',c.claim_id,'snapshot',c.snapshot,
 'as_of',c.created_at,'result',(SELECT to_jsonb(o) FROM private.buyer_analysis_results o WHERE o.request_id=p_id AND o.buyer_id=p_buyer));
END $$;

CREATE FUNCTION public.authorize_buyer_classification(p_id uuid,p_operator uuid,p_buyer uuid,p_claim uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.buyer_analysis_claims;
BEGIN
 PERFORM public.buyer_analysis_status(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 SELECT * INTO c FROM private.buyer_analysis_claims WHERE request_id=p_id AND buyer_id=p_buyer;
 IF c.claim_id IS DISTINCT FROM p_claim OR c.blocked OR NOT EXISTS(SELECT 1 FROM private.buyer_analysis_requests WHERE id=p_id AND kind='classify' AND paid_confirmed)
 THEN RAISE EXCEPTION 'Invalid classification claim' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_authorizations WHERE request_id=p_id AND buyer_id=p_buyer) THEN RETURN jsonb_build_object('authorized',false); END IF;
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id) THEN RETURN jsonb_build_object('authorized',false,'state','stale'); END IF;
 IF private.buyer_analysis_snapshot(p_buyer)<>c.snapshot THEN RETURN jsonb_build_object('authorized',false,'state','stale'); END IF;
 INSERT INTO private.buyer_analysis_authorizations(request_id,buyer_id,claim_id) VALUES(p_id,p_buyer,p_claim);
 RETURN jsonb_build_object('authorized',true);
END $$;

CREATE FUNCTION public.store_buyer_analysis_result(p_id uuid,p_operator uuid,p_buyer uuid,p_claim uuid,p_state text,p_patch jsonb,p_metadata jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.buyer_analysis_claims; r private.buyer_analysis_requests; prior private.buyer_analysis_results; fields text[];
BEGIN
 PERFORM public.buyer_analysis_status(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 SELECT * INTO c FROM private.buyer_analysis_claims WHERE request_id=p_id AND buyer_id=p_buyer;
 SELECT * INTO r FROM private.buyer_analysis_requests WHERE id=p_id;
 IF c.claim_id IS DISTINCT FROM p_claim OR c.blocked OR jsonb_typeof(p_patch) IS DISTINCT FROM 'object' OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object'
 OR octet_length(p_patch::text)+octet_length(p_metadata::text)>32000 OR p_state NOT IN ('valid','invalid','failed','unknown','stale','missing')
 THEN RAISE EXCEPTION 'Invalid retained analysis result' USING ERRCODE='22023'; END IF;
 SELECT * INTO prior FROM private.buyer_analysis_results WHERE request_id=p_id AND buyer_id=p_buyer;
 IF FOUND THEN
  IF prior.claim_id<>p_claim OR prior.state<>p_state OR prior.patch<>p_patch OR prior.metadata<>p_metadata THEN RAISE EXCEPTION 'Retained result changed' USING ERRCODE='22023'; END IF;
  RETURN jsonb_build_object('saved',true);
 END IF;
 fields:=CASE WHEN r.kind='classify' THEN ARRAY['buyer_type_ibie','ai_classified_at','tags'] ELSE
 ARRAY['ibie_score','ibie_tier','tags','last_scored_at','score_version','total_purchases_12mo','properties_owned','avg_purchase_price','last_purchase_date','cash_buyer','repeat_buyer'] END;
 IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_patch) k WHERE NOT k=ANY(fields)) OR (p_state<>'valid' AND p_patch<>'{}'::jsonb)
 THEN RAISE EXCEPTION 'Analysis cannot change buyer controls' USING ERRCODE='22023'; END IF;
 IF p_state='valid' AND (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(p_patch) k) IS DISTINCT FROM
 (SELECT array_agg(k ORDER BY k) FROM unnest(fields) k) THEN RAISE EXCEPTION 'Incomplete analysis result' USING ERRCODE='22023'; END IF;
 IF p_state='valid' AND (NOT p_patch ? 'tags' OR jsonb_typeof(p_patch->'tags')<>'array') THEN RAISE EXCEPTION 'Missing analysis tags' USING ERRCODE='22023'; END IF;
 IF p_state='valid' AND r.kind='score' AND (p_patch->>'score_version')::int<>coalesce((c.snapshot->'buyer'->>'score_version')::int,0)+1
 THEN RAISE EXCEPTION 'Score version changed' USING ERRCODE='22023'; END IF;
 IF p_state='valid' AND r.kind='classify' AND (NOT EXISTS(SELECT 1 FROM private.buyer_analysis_authorizations WHERE request_id=p_id AND buyer_id=p_buyer)
 OR coalesce(p_patch->>'buyer_type_ibie','') NOT IN ('flipper','landlord','institutional','builder')) THEN RAISE EXCEPTION 'Classification was not authorized' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_analysis_results(request_id,buyer_id,claim_id,state,patch,metadata) VALUES(p_id,p_buyer,p_claim,p_state,p_patch,p_metadata);
 RETURN jsonb_build_object('saved',true);
END $$;

CREATE FUNCTION public.apply_buyer_analysis(p_id uuid,p_operator uuid,p_buyer uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.buyer_analysis_claims; o private.buyer_analysis_results; m private.buyer_analysis_commits; v_state text; cols text; changed int;
BEGIN
 PERFORM public.buyer_analysis_status(p_id,p_operator);
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-analysis:'||p_id::text,0));
 SELECT * INTO m FROM private.buyer_analysis_commits WHERE request_id=p_id AND buyer_id=p_buyer;
 IF FOUND THEN RETURN jsonb_build_object('state',m.state); END IF;
 SELECT * INTO c FROM private.buyer_analysis_claims WHERE request_id=p_id AND buyer_id=p_buyer;
 SELECT * INTO o FROM private.buyer_analysis_results WHERE request_id=p_id AND buyer_id=p_buyer;
 IF o.request_id IS NULL THEN RETURN jsonb_build_object('state','unconfirmed'); END IF;
 v_state:=CASE WHEN o.state='valid' THEN 'applied' WHEN o.state='invalid' THEN 'failed' ELSE o.state END;
 IF EXISTS(SELECT 1 FROM private.buyer_analysis_cancellations WHERE request_id=p_id) THEN v_state:='canceled'; END IF;
 IF v_state='applied' THEN
  SELECT string_agg(format('%I',k),',' ORDER BY k) INTO cols FROM jsonb_object_keys(o.patch) k;
  EXECUTE format($sql$UPDATE public.buyers b SET (%s)=(SELECT %s FROM jsonb_populate_record(NULL::public.buyers,$1))
    WHERE b.id=$2 AND to_jsonb(b)=$3 AND coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id)
      FROM public.buyer_transactions t WHERE t.buyer_id=b.id),'[]'::jsonb)=$4$sql$,cols,cols)
  USING o.patch,p_buyer,c.snapshot->'buyer',c.snapshot->'transactions';
  GET DIAGNOSTICS changed=ROW_COUNT;
  IF changed=0 THEN v_state:=CASE WHEN EXISTS(SELECT 1 FROM public.buyers WHERE id=p_buyer) THEN 'stale' ELSE 'missing' END; END IF;
 END IF;
 INSERT INTO private.buyer_analysis_commits(request_id,buyer_id,state) VALUES(p_id,p_buyer,v_state);
 RETURN jsonb_build_object('state',v_state);
END $$;

DO $$ DECLARE f regprocedure; BEGIN
 FOR f IN SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
 AND p.proname=ANY(ARRAY['buyer_analysis_status','start_buyer_analysis','cancel_buyer_analysis','claim_buyer_analysis',
 'authorize_buyer_classification','store_buyer_analysis_result','apply_buyer_analysis']) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',f);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',f);
 END LOOP;
END $$;
