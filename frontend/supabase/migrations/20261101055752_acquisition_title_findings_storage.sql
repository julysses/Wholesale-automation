-- Extend the existing immutable review entity with post-execution title findings.
-- No writer, policy provisioning, title-clearance claim or disposition is enabled.
-- Compensation: keep the new path unavailable / pause acquisition; preserve history.
BEGIN;
CREATE FUNCTION private.valid_title_source(value jsonb,p_version integer) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
BEGIN
 RETURN value IS NOT NULL AND p_version IS NOT NULL AND p_version>0
  AND jsonb_typeof(value)='object' AND value ?& ARRAY['artifact_id','artifact_version','sha256','locator']
  AND (SELECT count(*) FROM jsonb_object_keys(value))=4
  AND jsonb_typeof(value->'artifact_id')='string' AND value->>'artifact_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  AND jsonb_typeof(value->'artifact_version')='number' AND value->>'artifact_version' ~ '^[1-9][0-9]*$'
  AND (value->>'artifact_version')::integer BETWEEN 1 AND p_version
  AND jsonb_typeof(value->'sha256')='string' AND value->>'sha256' ~ '^[0-9a-f]{64}$'
  AND jsonb_typeof(value->'locator')='string' AND length(value->>'locator')<=1000
  AND length(trim(value->>'locator'))>0 AND value->>'locator' !~ '[[:cntrl:]]';
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;
CREATE FUNCTION private.valid_title_report_date(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE stamp timestamptz;
BEGIN
 IF value IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'object'
  OR NOT(value ?& ARRAY['precision','calendar_date','instant']) OR (SELECT count(*) FROM jsonb_object_keys(value))<>3 THEN RETURN false; END IF;
 IF value->>'precision'='unknown' THEN RETURN value->'calendar_date'='null'::jsonb AND value->'instant'='null'::jsonb; END IF;
 IF value->>'precision'='date' THEN
  RETURN value->'instant'='null'::jsonb AND jsonb_typeof(value->'calendar_date')='string'
   AND value->>'calendar_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND (value->>'calendar_date')::date::text=value->>'calendar_date';
 END IF;
 IF value->>'precision' IS DISTINCT FROM 'instant' OR value->'calendar_date' IS DISTINCT FROM 'null'::jsonb
  OR jsonb_typeof(value->'instant') IS DISTINCT FROM 'string'
  OR value->>'instant' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$' THEN RETURN false; END IF;
 stamp:=(value->>'instant')::timestamptz; RETURN isfinite(stamp);
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN RETURN false;
END $$;
CREATE FUNCTION private.valid_title_findings(value jsonb,p_version integer,p_approved boolean) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; finding jsonb; source jsonb; sources jsonb:='[]'; seen jsonb:='{}'; original jsonb;
BEGIN
 IF value IS NULL OR p_version IS NULL OR p_version<1 OR p_approved IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'object'
  OR NOT(value ?& ARRAY['report_as_of','report_as_of_source','report_note','ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'])
  OR (SELECT count(*) FROM jsonb_object_keys(value))<>8
  OR private.valid_title_report_date(value->'report_as_of') IS DISTINCT FROM true
  OR jsonb_typeof(value->'report_note') IS DISTINCT FROM 'string'
  OR length(value->>'report_note')>4000 OR length(btrim(value->>'report_note',E' \t\n\r\f\v'))<20 THEN RETURN false; END IF;
 IF value->'report_as_of'->>'precision'='unknown' THEN
  IF p_approved OR value->'report_as_of_source' IS DISTINCT FROM 'null'::jsonb THEN RETURN false; END IF;
 ELSE
  IF private.valid_title_source(value->'report_as_of_source',p_version) IS DISTINCT FROM true THEN RETURN false; END IF;
  sources:=jsonb_build_array(value->'report_as_of_source');
 END IF;
 FOREACH name IN ARRAY ARRAY['ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'] LOOP
  finding:=value->name;
  IF jsonb_typeof(finding) IS DISTINCT FROM 'object' OR NOT(finding ?& ARRAY['finding','note','required_action','sources'])
   OR (SELECT count(*) FROM jsonb_object_keys(finding))<>4
   OR finding->>'finding' IS NULL OR finding->>'finding' NOT IN ('satisfactory','requires_resolution','unknown')
   OR jsonb_typeof(finding->'note') IS DISTINCT FROM 'string' OR length(finding->>'note')>4000
   OR length(btrim(finding->>'note',E' \t\n\r\f\v'))<20
   OR jsonb_typeof(finding->'sources') IS DISTINCT FROM 'array' OR jsonb_array_length(finding->'sources')>3 THEN RETURN false; END IF;
  IF finding->>'finding'='satisfactory' THEN
   IF jsonb_array_length(finding->'sources')<1 OR finding->'required_action' IS DISTINCT FROM 'null'::jsonb THEN RETURN false; END IF;
  ELSE
   IF p_approved OR jsonb_typeof(finding->'required_action') IS DISTINCT FROM 'string'
    OR length(finding->>'required_action')>4000 OR length(btrim(finding->>'required_action',E' \t\n\r\f\v'))<20 THEN RETURN false; END IF;
  END IF;
  IF (SELECT count(*) FROM jsonb_array_elements(finding->'sources'))<>(SELECT count(DISTINCT item) FROM jsonb_array_elements(finding->'sources') item) THEN RETURN false; END IF;
  sources:=sources||(finding->'sources');
 END LOOP;
 FOR source IN SELECT * FROM jsonb_array_elements(sources) LOOP
  IF private.valid_title_source(source,p_version) IS DISTINCT FROM true THEN RETURN false; END IF;
  original:=jsonb_build_array(source->'artifact_version',source->'sha256');
  IF seen ? (source->>'artifact_id') AND seen->(source->>'artifact_id')<>original THEN RETURN false; END IF;
  seen:=seen||jsonb_build_object(source->>'artifact_id',original);
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;
CREATE FUNCTION private.valid_title_source_journal(findings jsonb,journal jsonb,p_version integer,p_artifact uuid,p_source_version integer,p_verification uuid,p_hash text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE item jsonb; citation jsonb; name text; citations jsonb:='[]'; seen text[]:='{}'; root_found boolean:=false;
BEGIN
 IF journal IS NULL OR jsonb_typeof(journal) IS DISTINCT FROM 'array' OR jsonb_array_length(journal) NOT BETWEEN 1 AND 16
  OR p_artifact IS NULL OR p_source_version IS NULL OR p_verification IS NULL OR p_hash IS NULL THEN RETURN false; END IF;
 FOR item IN SELECT * FROM jsonb_array_elements(journal) LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR NOT(item ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (SELECT count(*) FROM jsonb_object_keys(item))<>6
   OR private.valid_title_source(jsonb_build_object('artifact_id',item->'artifact_id','artifact_version',item->'source_version','sha256',item->'sha256','locator','Original source'),p_version) IS DISTINCT FROM true
   OR jsonb_typeof(item->'verification_id') IS DISTINCT FROM 'string' OR item->>'verification_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   OR item->>'purpose' IS NULL OR item->>'purpose' NOT IN ('purchase_contract','title_report','seller_disclosure','assignment_agreement','assignee_disclosure','closing_statement','supporting_document')
   OR private.valid_title_report_date(jsonb_build_object('precision','instant','calendar_date',NULL,'instant',item->'expires_at')) IS DISTINCT FROM true
   OR item->>'artifact_id'=ANY(seen) THEN RETURN false; END IF;
  seen:=array_append(seen,item->>'artifact_id');
  IF item->>'artifact_id'=p_artifact::text AND (item->>'source_version')::integer=p_source_version
   AND item->>'verification_id'=p_verification::text AND item->>'sha256'=p_hash AND item->>'purpose'='title_report' THEN root_found:=true; END IF;
 END LOOP;
 IF NOT root_found THEN RETURN false; END IF;
 IF findings->'report_as_of_source' IS DISTINCT FROM 'null'::jsonb THEN
  citation:=findings->'report_as_of_source';
  IF citation->>'artifact_id' IS DISTINCT FROM p_artifact::text OR (citation->>'artifact_version')::integer IS DISTINCT FROM p_source_version
   OR citation->>'sha256' IS DISTINCT FROM p_hash THEN RETURN false; END IF;
  citations:=jsonb_build_array(citation);
 END IF;
 FOREACH name IN ARRAY ARRAY['ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'] LOOP citations:=citations||(findings->name->'sources'); END LOOP;
 FOR citation IN SELECT * FROM jsonb_array_elements(citations) LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(journal) entry WHERE entry->>'artifact_id'=citation->>'artifact_id'
   AND entry->'source_version'=citation->'artifact_version' AND entry->>'sha256'=citation->>'sha256') THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_title_source(jsonb,integer),private.valid_title_report_date(jsonb),private.valid_title_findings(jsonb,integer,boolean),private.valid_title_source_journal(jsonb,jsonb,integer,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;

ALTER TABLE private.acquisition_contract_review_policies
 DROP CONSTRAINT acquisition_review_policy_kind, DROP CONSTRAINT acquisition_review_policy_purpose,
 ADD CONSTRAINT acquisition_review_policy_kind CHECK(kind IN ('contract_review','title_review','assignment_basis','executed_contract','deadline_resolution','title_findings')),
 ADD CONSTRAINT acquisition_review_policy_purpose CHECK(
  (kind IN ('contract_review','assignment_basis','executed_contract','deadline_resolution') AND purpose='purchase_contract')
  OR (kind IN ('title_review','title_findings') AND purpose='title_report'));
ALTER TABLE public.acquisition_contract_transitions ADD CONSTRAINT acquisition_title_execution_identity
 UNIQUE(workspace_id,contract_id,contract_version,id,recorded_status);
ALTER TABLE public.acquisition_contract_reviews
 DROP CONSTRAINT acquisition_contract_reviews_status_check, DROP CONSTRAINT acquisition_contract_reviews_check,
 ADD CONSTRAINT acquisition_contract_reviews_status_check CHECK(status IN ('approved','withdrawn') OR (kind='title_findings' AND status='requires_resolution')),
 ADD CONSTRAINT acquisition_contract_reviews_check CHECK(
  (status='approved' AND personally_reviewed AND expires_at IS NOT NULL AND isfinite(expires_at) AND expires_at>created_at)
  OR (status='withdrawn' AND NOT personally_reviewed AND expires_at IS NULL)
  OR (kind='title_findings' AND status='requires_resolution' AND personally_reviewed AND expires_at IS NULL)),
 ADD COLUMN title_findings jsonb, ADD COLUMN title_sources jsonb,
 ADD COLUMN title_execution_transition_id uuid,
 ADD COLUMN title_execution_status text GENERATED ALWAYS AS (CASE WHEN kind='title_findings' THEN 'executed' END) STORED,
 ADD COLUMN title_original_review_id uuid, ADD COLUMN title_original_status text,
 ADD CONSTRAINT acquisition_title_execution FOREIGN KEY(workspace_id,contract_id,contract_version,title_execution_transition_id,title_execution_status)
 REFERENCES public.acquisition_contract_transitions(workspace_id,contract_id,contract_version,id,recorded_status),
 ADD CONSTRAINT acquisition_title_review_identity UNIQUE(workspace_id,contract_id,contract_version,kind,id,status,title_execution_transition_id),
 ADD CONSTRAINT acquisition_title_original_review FOREIGN KEY(workspace_id,contract_id,contract_version,kind,title_original_review_id,title_original_status,title_execution_transition_id)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,id,status,title_execution_transition_id),
 ADD CONSTRAINT acquisition_title_findings_shape CHECK(
  (kind<>'title_findings' AND title_findings IS NULL AND title_sources IS NULL AND title_execution_transition_id IS NULL AND title_original_review_id IS NULL AND title_original_status IS NULL)
  OR (kind='title_findings' AND purpose='title_report' AND title_execution_transition_id IS NOT NULL AND (
   (status IN ('approved','requires_resolution') AND title_original_review_id IS NULL AND title_original_status IS NULL
    AND title_findings IS NOT NULL AND private.valid_title_findings(title_findings,contract_version,status='approved') IS TRUE
    AND title_sources IS NOT NULL AND private.valid_title_source_journal(title_findings,title_sources,contract_version,artifact_id,source_version,verification_id,sha256) IS TRUE)
   OR (status='withdrawn' AND title_findings IS NULL AND title_sources IS NULL AND title_original_review_id IS NOT NULL
    AND title_original_review_id<>id AND title_original_status IS NOT NULL AND title_original_status IN ('approved','requires_resolution') AND sequence>1))));
-- Existing RLS, restricted grants, original-artifact/verification/policy FKs,
-- unique request identities and immutable-row/audit triggers remain intact.
-- Generic review RPCs still reject title_findings; a controlled writer is required.
COMMIT;
