-- OCR receipts are private evidence, never property verification or contact permission.
-- Text is hash-checked at ingestion; full text remains in the private evidence files.
BEGIN;
CREATE TABLE wholesale_ingest.foreclosure_extractions (
 source_id uuid NOT NULL,
 source_record_id text NOT NULL,
 html_sha256 text NOT NULL,
 page integer NOT NULL CHECK(page BETWEEN 1 AND 100),
 engine text NOT NULL CHECK(length(engine) BETWEEN 1 AND 128),
 image_sha256 text NOT NULL CHECK(image_sha256 ~ '^[a-f0-9]{64}$'),
 text_length integer NOT NULL CHECK(text_length BETWEEN 0 AND 100000),
 text_sha256 text NOT NULL CHECK(text_sha256 ~ '^[a-f0-9]{64}$'),
 confidence numeric NOT NULL CHECK(confidence BETWEEN 0 AND 100),
 quality_review boolean NOT NULL,
 extracted_at timestamptz NOT NULL CHECK(isfinite(extracted_at)),
 operator_id uuid NOT NULL REFERENCES public.profiles(id),
 received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(source_id,source_record_id,html_sha256,page,engine),
 FOREIGN KEY(source_id,source_record_id,html_sha256) REFERENCES wholesale_ingest.foreclosure_captures
);
ALTER TABLE wholesale_ingest.foreclosure_extractions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.foreclosure_extractions FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.foreclosure_extractions TO service_role;

CREATE FUNCTION public.save_foreclosure_extractions(p_operator uuid,p_source text,p_items jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,wholesale_ingest,pg_temp AS $$
DECLARE src wholesale_ingest.sources; item jsonb; capture wholesale_ingest.foreclosure_captures;
 old wholesale_ingest.foreclosure_extractions; n integer; stamp timestamptz; score numeric;
 doc text; summary_hash text; image_hash text; text_hash text; contents text; engine_id text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO STRICT src FROM wholesale_ingest.sources WHERE source_key=p_source AND list_type='pre_foreclosure';
 IF jsonb_typeof(p_items) IS DISTINCT FROM 'array' OR jsonb_array_length(p_items) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid extraction batch'; END IF;
 IF (SELECT count(DISTINCT (value->>'document_id',value->>'page',value->>'engine')) FROM jsonb_array_elements(p_items))<>jsonb_array_length(p_items) THEN RAISE EXCEPTION 'Duplicate extraction pages'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_items) ORDER BY value->>'document_id',value->>'page',value->>'engine' LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(item))<>10 OR NOT(item ?& ARRAY['document_id','source_url','html_sha256','page','image_sha256','engine','text','text_sha256','confidence','extracted_at']) THEN RAISE EXCEPTION 'Unexpected extraction fields'; END IF;
  doc:=item->>'document_id';summary_hash:=item->>'html_sha256';image_hash:=item->>'image_sha256';
  text_hash:=item->>'text_sha256';contents:=item->>'text';engine_id:=item->>'engine';
  IF jsonb_typeof(item->'page') IS DISTINCT FROM 'number' OR coalesce(item->>'page','') !~ '^[0-9]+$' OR jsonb_typeof(item->'confidence') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'Invalid extraction numeric fields'; END IF;
  n:=(item->>'page')::integer;score:=(item->>'confidence')::numeric;stamp:=(item->>'extracted_at')::timestamptz;
  IF coalesce(doc,'') !~ '^[0-9]{1,30}$' OR coalesce(summary_hash,'') !~ '^[a-f0-9]{64}$' OR coalesce(image_hash,'') !~ '^[a-f0-9]{64}$'
   OR coalesce(text_hash,'') !~ '^[a-f0-9]{64}$' OR coalesce(engine_id,'') !~ '^[a-zA-Z0-9/._-]{1,128}$'
   OR jsonb_typeof(item->'text') IS DISTINCT FROM 'string' OR octet_length(contents)>100000
   OR text_hash IS DISTINCT FROM encode(sha256(convert_to(contents,'UTF8')),'hex')
   OR n NOT BETWEEN 1 AND 100 OR score NOT BETWEEN 0 AND 100 OR stamp IS NULL OR NOT isfinite(stamp)
   OR stamp<'2000-01-01' OR stamp>now()+interval '5 minutes' THEN RAISE EXCEPTION 'Invalid extraction receipt'; END IF;
  SELECT * INTO capture FROM wholesale_ingest.foreclosure_captures WHERE source_id=src.id AND source_record_id=doc AND html_sha256=summary_hash;
  IF NOT FOUND OR capture.source_url IS DISTINCT FROM item->>'source_url' OR jsonb_array_length(capture.pages)<>capture.expected_pages
   OR capture.pages->(n-1)->>'sha256' IS DISTINCT FROM image_hash OR stamp<capture.captured_at THEN RAISE EXCEPTION 'Extraction must match complete captured evidence'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(src.id::text||':'||doc||':'||summary_hash||':'||n::text||':'||engine_id,0));
  SELECT * INTO old FROM wholesale_ingest.foreclosure_extractions WHERE source_id=src.id AND source_record_id=doc AND html_sha256=summary_hash AND page=n AND engine=engine_id;
  IF FOUND THEN
   IF old.image_sha256<>image_hash OR old.text_sha256<>text_hash OR old.text_length<>length(contents) OR old.confidence<>score OR old.extracted_at<>stamp THEN RAISE EXCEPTION 'Extraction evidence conflict'; END IF;
  ELSE
   INSERT INTO wholesale_ingest.foreclosure_extractions VALUES(src.id,doc,summary_hash,n,engine_id,image_hash,length(contents),text_hash,score,contents !~ '\S' OR score<85,stamp,p_operator,now());
  END IF;
 END LOOP;
 RETURN jsonb_build_object('accepted',jsonb_array_length(p_items),'source_key',p_source,'verification_granted',false,'outreach_authorized',false);
END; $$;
REVOKE ALL ON FUNCTION public.save_foreclosure_extractions(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_foreclosure_extractions(uuid,text,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.foreclosure_capture_status(p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,wholesale_ingest,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 WITH latest AS (
  SELECT DISTINCT ON(source_id,source_record_id) * FROM wholesale_ingest.foreclosure_captures ORDER BY source_id,source_record_id,captured_at DESC,received_at DESC
 ), extraction_pages AS (
  SELECT DISTINCT ON(e.source_id,e.source_record_id,e.html_sha256,e.page) e.*
  FROM wholesale_ingest.foreclosure_extractions e JOIN latest c USING(source_id,source_record_id,html_sha256)
  ORDER BY e.source_id,e.source_record_id,e.html_sha256,e.page,e.extracted_at DESC,e.received_at DESC,e.engine
 ), extraction_counts AS (
  SELECT source_id,source_record_id,html_sha256,count(*)::int extracted_pages,
   count(*) FILTER(WHERE quality_review)::int quality_review_pages
  FROM extraction_pages GROUP BY source_id,source_record_id,html_sha256
 ), counts AS (
  SELECT s.county,count(c.source_record_id)::int documents,
   count(*) FILTER(WHERE jsonb_array_length(c.pages)=c.expected_pages)::int complete_documents,
   coalesce(sum(jsonb_array_length(c.pages)),0)::int captured_pages,coalesce(sum(c.expected_pages),0)::int expected_pages,
   coalesce(sum(e.extracted_pages),0)::int extracted_pages,
   count(*) FILTER(WHERE e.extracted_pages=c.expected_pages)::int extracted_documents,
   coalesce(sum(e.quality_review_pages),0)::int quality_review_pages,max(c.received_at) updated_at
  FROM wholesale_ingest.sources s LEFT JOIN latest c ON c.source_id=s.id
  LEFT JOIN extraction_counts e USING(source_id,source_record_id,html_sha256)
  WHERE s.list_type='pre_foreclosure' GROUP BY s.county)
 SELECT jsonb_build_object('counties',jsonb_agg(to_jsonb(counts) ORDER BY county),'verification_granted',false) INTO result FROM counts;
 RETURN result;
END; $$;
COMMIT;
