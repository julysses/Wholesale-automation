-- Capture receipts are evidence inventory, never identity, sale, tracing or outreach approval.
BEGIN;
CREATE TABLE wholesale_ingest.foreclosure_captures (
 source_id uuid NOT NULL REFERENCES wholesale_ingest.sources,
 source_record_id text NOT NULL,
 html_sha256 text NOT NULL CHECK(html_sha256 ~ '^[a-f0-9]{64}$'),
 source_url text NOT NULL,
 captured_at timestamptz NOT NULL,
 expected_pages integer NOT NULL CHECK(expected_pages BETWEEN 1 AND 100),
 pages jsonb NOT NULL CHECK(jsonb_typeof(pages)='array'),
 operator_id uuid NOT NULL REFERENCES public.profiles(id),
 received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(source_id,source_record_id,html_sha256)
);
ALTER TABLE wholesale_ingest.foreclosure_captures ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.foreclosure_captures FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.foreclosure_captures TO service_role;

CREATE FUNCTION public.save_foreclosure_captures(p_operator uuid,p_source text,p_items jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,wholesale_ingest,pg_temp AS $$
DECLARE src wholesale_ingest.sources; item jsonb; old wholesale_ingest.foreclosure_captures;
 cnt integer; expected integer; stamp timestamptz; doc text; url text; digest text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO STRICT src FROM wholesale_ingest.sources WHERE source_key=p_source AND list_type='pre_foreclosure';
 IF jsonb_typeof(p_items) IS DISTINCT FROM 'array' OR jsonb_array_length(p_items) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid capture batch'; END IF;
 IF (SELECT count(DISTINCT value->>'document_id') FROM jsonb_array_elements(p_items))<>jsonb_array_length(p_items) THEN RAISE EXCEPTION 'Duplicate or missing document IDs'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_items) ORDER BY value->>'document_id' LOOP
  doc:=item->>'document_id';url:=item->>'source_url';digest:=item->>'html_sha256';
  IF doc IS NULL OR doc !~ '^[0-9]{1,30}$' OR digest IS NULL OR digest !~ '^[a-f0-9]{64}$' OR url IS DISTINCT FROM
   (CASE src.county WHEN 'Collin' THEN 'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/'||doc ELSE 'https://dallas.tx.publicsearch.us/doc/'||doc END) THEN RAISE EXCEPTION 'Invalid official capture identity'; END IF;
  IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.records r JOIN wholesale_ingest.ingest_runs run ON run.id=r.run_id WHERE run.source_id=src.id AND r.source_record_id=doc) THEN RAISE EXCEPTION 'Capture must match an ingested notice'; END IF;
  IF (SELECT count(*) FROM jsonb_object_keys(item))<>6 OR NOT (item ?& ARRAY['document_id','source_url','html_sha256','captured_at','expected_pages','pages']) THEN RAISE EXCEPTION 'Unexpected capture fields'; END IF;
  expected:=(item->>'expected_pages')::integer;stamp:=(item->>'captured_at')::timestamptz;
  IF expected IS NULL OR expected NOT BETWEEN 1 AND 100 OR stamp IS NULL OR NOT isfinite(stamp) OR stamp<'2000-01-01' OR stamp>now()+interval '5 minutes' THEN RAISE EXCEPTION 'Invalid capture date or page count'; END IF;
  IF jsonb_typeof(item->'pages') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid page receipts'; END IF;
  cnt:=jsonb_array_length(item->'pages');
  IF cnt NOT BETWEEN 1 AND expected OR EXISTS(SELECT 1 FROM jsonb_array_elements(item->'pages') WITH ORDINALITY p(value,n) WHERE
   jsonb_typeof(value) IS DISTINCT FROM 'object' OR value->>'page' IS DISTINCT FROM n::text OR coalesce(value->>'sha256','') !~ '^[a-f0-9]{64}$')
   OR (SELECT count(DISTINCT value->>'sha256') FROM jsonb_array_elements(item->'pages'))<>cnt THEN RAISE EXCEPTION 'Invalid ordered page receipts'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(src.id::text||':'||doc||':'||digest,0));
  SELECT * INTO old FROM wholesale_ingest.foreclosure_captures WHERE source_id=src.id AND source_record_id=doc AND html_sha256=digest;
  IF FOUND THEN
   IF old.expected_pages<>expected OR old.captured_at<>stamp OR old.source_url<>url THEN RAISE EXCEPTION 'Capture identity conflict'; END IF;
   IF NOT(old.pages <@ (item->'pages')) AND NOT((item->'pages') <@ old.pages) THEN RAISE EXCEPTION 'Page evidence conflict'; END IF;
   IF jsonb_array_length(old.pages)<cnt THEN UPDATE wholesale_ingest.foreclosure_captures SET pages=item->'pages',operator_id=p_operator,received_at=now() WHERE source_id=src.id AND source_record_id=doc AND html_sha256=digest; END IF;
  ELSE
   INSERT INTO wholesale_ingest.foreclosure_captures VALUES(src.id,doc,digest,url,stamp,expected,item->'pages',p_operator,now());
  END IF;
 END LOOP;
 RETURN jsonb_build_object('accepted',jsonb_array_length(p_items),'source_key',p_source,'operator_id',p_operator,'verification_granted',false,'outreach_authorized',false);
END; $$;
CREATE FUNCTION public.foreclosure_capture_status(p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,wholesale_ingest,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 WITH latest AS (SELECT DISTINCT ON(source_id,source_record_id) * FROM wholesale_ingest.foreclosure_captures ORDER BY source_id,source_record_id,captured_at DESC,received_at DESC), counts AS (
 SELECT s.county,count(c.source_record_id)::int documents,count(*) FILTER(WHERE jsonb_array_length(c.pages)=c.expected_pages)::int complete_documents,
 coalesce(sum(jsonb_array_length(c.pages)),0)::int captured_pages,coalesce(sum(c.expected_pages),0)::int expected_pages,max(c.received_at) updated_at
 FROM wholesale_ingest.sources s LEFT JOIN latest c ON c.source_id=s.id WHERE s.list_type='pre_foreclosure' GROUP BY s.county)
 SELECT jsonb_build_object('counties',jsonb_agg(to_jsonb(counts) ORDER BY county),'verification_granted',false) INTO result FROM counts;
 RETURN result;
END; $$;
REVOKE ALL ON FUNCTION public.save_foreclosure_captures(uuid,text,jsonb),public.foreclosure_capture_status(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_foreclosure_captures(uuid,text,jsonb),public.foreclosure_capture_status(uuid) TO service_role;
COMMIT;
