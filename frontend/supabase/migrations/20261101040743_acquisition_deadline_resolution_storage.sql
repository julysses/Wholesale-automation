-- Extend immutable review history with separately reviewed calendar interpretations.
-- No writer, policy provisioning or execution authorization is exposed here.
-- Compensation: leave the new review path disabled; preserve recorded decisions.
BEGIN;
CREATE FUNCTION private.valid_deadline_resolution(value jsonb,p_version integer) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE source jsonb; instant timestamptz; wall timestamp; day date; local_clock time;
BEGIN
 IF value IS NULL OR p_version IS NULL OR p_version<1 OR jsonb_typeof(value) IS DISTINCT FROM 'object'
  OR NOT(value ?& ARRAY['term','calendar_date','local_time','time_zone','resolved_instant','basis','source','rationale'])
  OR (SELECT count(*) FROM jsonb_object_keys(value))<>8 THEN RETURN false; END IF;
 IF value->>'term' IS NULL OR value->>'term' NOT IN ('effective','inspection_deadline','closing_deadline')
  OR value->>'basis' IS NULL OR value->>'basis' NOT IN ('explicit_document_time','reviewed_interpretation')
  OR jsonb_typeof(value->'calendar_date') IS DISTINCT FROM 'string' OR value->>'calendar_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  OR jsonb_typeof(value->'local_time') IS DISTINCT FROM 'string' OR value->>'local_time' !~ '^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$'
  OR jsonb_typeof(value->'time_zone') IS DISTINCT FROM 'string' OR length(value->>'time_zone') NOT BETWEEN 1 AND 100
  OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=value->>'time_zone')
  OR jsonb_typeof(value->'resolved_instant') IS DISTINCT FROM 'string'
  OR value->>'resolved_instant' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.0+)?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$'
  OR left(value->>'resolved_instant',19)<>(value->>'calendar_date')||'T'||(value->>'local_time')
  OR jsonb_typeof(value->'rationale') IS DISTINCT FROM 'string'
  OR length(value->>'rationale')>4000 OR length(trim(value->>'rationale'))<20 THEN RETURN false; END IF;
 day:=(value->>'calendar_date')::date; local_clock:=(value->>'local_time')::time;
 instant:=(value->>'resolved_instant')::timestamptz;
 wall:=instant AT TIME ZONE (value->>'time_zone');
 -- Round-trip the supplied instant instead of resolving a naive local timestamp:
 -- both explicit offsets in a repeated hour are valid, a missing hour is not.
 IF NOT isfinite(instant) OR wall::date<>day OR wall::time<>local_clock THEN RETURN false; END IF;
 source:=value->'source';
 IF jsonb_typeof(source) IS DISTINCT FROM 'object'
  OR NOT(source ?& ARRAY['term','artifact_id','artifact_version','sha256','locator'])
  OR (SELECT count(*) FROM jsonb_object_keys(source))<>5
  OR source->>'term' IS DISTINCT FROM value->>'term'
  OR jsonb_typeof(source->'artifact_id') IS DISTINCT FROM 'string'
  OR source->>'artifact_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  OR jsonb_typeof(source->'artifact_version') IS DISTINCT FROM 'number'
  OR source->>'artifact_version' !~ '^[1-9][0-9]*$'
  OR (source->>'artifact_version')::numeric>p_version
  OR jsonb_typeof(source->'sha256') IS DISTINCT FROM 'string' OR source->>'sha256' !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(source->'locator') IS DISTINCT FROM 'string'
  OR length(source->>'locator')>1000 OR length(trim(source->>'locator'))<1
  OR source->>'locator' ~ '[[:cntrl:]]' THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow OR numeric_value_out_of_range THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_deadline_resolution(jsonb,integer) FROM PUBLIC,anon,authenticated,service_role;

ALTER TABLE private.acquisition_contract_review_policies
 DROP CONSTRAINT acquisition_review_policy_kind,
 DROP CONSTRAINT acquisition_review_policy_purpose,
 ADD CONSTRAINT acquisition_review_policy_kind CHECK(kind IN ('contract_review','title_review','assignment_basis','executed_contract','deadline_resolution')),
 ADD CONSTRAINT acquisition_review_policy_purpose CHECK(
  (kind IN ('contract_review','assignment_basis','executed_contract','deadline_resolution') AND purpose='purchase_contract')
  OR (kind='title_review' AND purpose='title_report'));

ALTER TABLE public.acquisition_contract_reviews
 ADD COLUMN deadline_term text,
 ADD COLUMN deadline_resolution jsonb,
 ADD COLUMN deadline_original_review_id uuid,
 ADD COLUMN deadline_original_status text GENERATED ALWAYS AS
  (CASE WHEN kind='deadline_resolution' AND status='withdrawn' THEN 'approved'::text END) STORED,
 ADD CONSTRAINT acquisition_deadline_review_shape CHECK(
  (kind<>'deadline_resolution' AND deadline_term IS NULL AND deadline_resolution IS NULL AND deadline_original_review_id IS NULL)
  OR (kind='deadline_resolution' AND deadline_term IS NOT NULL
   AND deadline_term IN ('effective','inspection_deadline','closing_deadline') AND (
    (status='approved' AND deadline_original_review_id IS NULL AND deadline_resolution IS NOT NULL
     AND private.valid_deadline_resolution(deadline_resolution,contract_version)
     AND deadline_resolution->>'term'=deadline_term
     AND (deadline_resolution->'source'->>'artifact_id')::uuid=artifact_id
     AND (deadline_resolution->'source'->>'artifact_version')::integer=source_version
     AND deadline_resolution->'source'->>'sha256'=sha256)
    OR (status='withdrawn' AND deadline_resolution IS NULL AND deadline_original_review_id IS NOT NULL
     AND deadline_original_review_id<>id AND sequence>1)))),
 ADD CONSTRAINT acquisition_deadline_review_identity UNIQUE(workspace_id,contract_id,contract_version,kind,deadline_term,id,status),
 ADD CONSTRAINT acquisition_deadline_original_review FOREIGN KEY(workspace_id,contract_id,contract_version,kind,deadline_term,deadline_original_review_id,deadline_original_status)
  REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,deadline_term,id,status);
CREATE INDEX acquisition_deadline_review_latest ON public.acquisition_contract_reviews
 (workspace_id,contract_id,contract_version,deadline_term,sequence DESC) WHERE kind='deadline_resolution';
-- Existing sequence uniqueness, RLS, SELECT-only grants, source/policy foreign
-- keys and immutable history trigger remain intact. Existing RPCs reject this kind.
COMMIT;
