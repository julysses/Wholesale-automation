-- Post-execution findings extend the existing immutable review history.
-- No writer, policy provisioning, distribution or lifecycle transition is enabled.
-- Compensation: keep the path unavailable or pause acquisition; retain history.
BEGIN;
CREATE FUNCTION private.disposition_citations(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; sources jsonb:='[]';
BEGIN
 FOREACH name IN ARRAY ARRAY['contractual_interest','closing_structure','remaining_obligations'] LOOP
  sources:=sources||(value->name->'sources'); END LOOP;
 IF value->>'exit_type'='wholesale_assignment' THEN
  FOREACH name IN ARRAY ARRAY['assignment_provisions','legal_basis','seller_disclosure_requirements','assignee_disclosure_requirements'] LOOP
   sources:=sources||(value->'assignment'->name->'sources'); END LOOP;
 END IF;
 RETURN sources;
END $$;
CREATE FUNCTION private.valid_disposition_findings(value jsonb,p_version integer,p_approved boolean,p_exit text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE finding jsonb; source jsonb; seen jsonb:='{}'; original jsonb; entries jsonb;
BEGIN
 IF value IS NULL OR p_version IS NULL OR p_version<1 OR p_approved IS NULL
  OR p_exit IS NULL OR p_exit NOT IN ('principal_acquisition','wholesale_assignment')
  OR jsonb_typeof(value) IS DISTINCT FROM 'object'
  OR NOT(value ?& ARRAY['exit_type','contractual_interest','closing_structure','remaining_obligations','assignment'])
  OR (SELECT count(*) FROM jsonb_object_keys(value))<>5 OR value->>'exit_type' IS DISTINCT FROM p_exit THEN RETURN false; END IF;
 entries:=jsonb_build_array(value->'contractual_interest',value->'closing_structure',value->'remaining_obligations');
 IF p_exit='wholesale_assignment' THEN
  IF jsonb_typeof(value->'assignment') IS DISTINCT FROM 'object'
   OR NOT(value->'assignment' ?& ARRAY['assignment_provisions','legal_basis','seller_disclosure_requirements','assignee_disclosure_requirements'])
   OR (SELECT count(*) FROM jsonb_object_keys(value->'assignment'))<>4 THEN RETURN false; END IF;
  entries:=entries||jsonb_build_array(value->'assignment'->'assignment_provisions',value->'assignment'->'legal_basis',
   value->'assignment'->'seller_disclosure_requirements',value->'assignment'->'assignee_disclosure_requirements');
 ELSIF value->'assignment' IS DISTINCT FROM 'null'::jsonb THEN RETURN false; END IF;
 FOR finding IN SELECT * FROM jsonb_array_elements(entries) LOOP
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
  FOR source IN SELECT * FROM jsonb_array_elements(finding->'sources') LOOP
   IF private.valid_title_source(source,p_version) IS DISTINCT FROM true THEN RETURN false; END IF;
   original:=jsonb_build_array(source->'artifact_version',source->'sha256');
   IF seen ? (source->>'artifact_id') AND seen->(source->>'artifact_id')<>original THEN RETURN false; END IF;
   seen:=seen||jsonb_build_object(source->>'artifact_id',original);
  END LOOP;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;
CREATE FUNCTION private.valid_disposition_source_journal(findings jsonb,journal jsonb,p_version integer,p_artifact uuid,p_source_version integer,p_verification uuid,p_hash text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE item jsonb; citation jsonb; name text; citations jsonb:='[]'; seen text[]:='{}'; root_found boolean:=false;
BEGIN
 IF journal IS NULL OR jsonb_typeof(journal) IS DISTINCT FROM 'array' OR jsonb_array_length(journal) NOT BETWEEN 1 AND 22
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
   AND item->>'verification_id'=p_verification::text AND item->>'sha256'=p_hash AND item->>'purpose'='purchase_contract' THEN root_found:=true; END IF;
 END LOOP;
 IF NOT root_found THEN RETURN false; END IF;
 citations:=private.disposition_citations(findings);
 FOR citation IN SELECT * FROM jsonb_array_elements(citations) LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(journal) entry WHERE entry->>'artifact_id'=citation->>'artifact_id'
   AND entry->'source_version'=citation->'artifact_version' AND entry->>'sha256'=citation->>'sha256') THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_parameter_value THEN RETURN false;
END $$;

REVOKE ALL ON FUNCTION private.disposition_citations(jsonb),private.valid_disposition_findings(jsonb,integer,boolean,text),private.valid_disposition_source_journal(jsonb,jsonb,integer,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
ALTER TABLE private.acquisition_contract_review_policies
 DROP CONSTRAINT acquisition_review_policy_kind, DROP CONSTRAINT acquisition_review_policy_purpose,
 ADD CONSTRAINT acquisition_review_policy_kind CHECK(kind IN ('contract_review','title_review','assignment_basis','executed_contract','deadline_resolution','title_findings','disposition_findings')),
 ADD CONSTRAINT acquisition_review_policy_purpose CHECK(
  (kind IN ('contract_review','assignment_basis','executed_contract','deadline_resolution','disposition_findings') AND purpose='purchase_contract')
  OR (kind IN ('title_review','title_findings') AND purpose='title_report'));
ALTER TABLE public.acquisition_contract_reviews
 DROP CONSTRAINT acquisition_contract_reviews_status_check, DROP CONSTRAINT acquisition_contract_reviews_check,
 ADD CONSTRAINT acquisition_contract_reviews_status_check CHECK(status IN ('approved','withdrawn') OR (kind IN ('title_findings','disposition_findings') AND status='requires_resolution')),
 ADD CONSTRAINT acquisition_contract_reviews_check CHECK(
  (status='approved' AND personally_reviewed AND expires_at IS NOT NULL AND isfinite(expires_at) AND expires_at>created_at)
  OR (status='withdrawn' AND NOT personally_reviewed AND expires_at IS NULL)
  OR (kind IN ('title_findings','disposition_findings') AND status='requires_resolution' AND personally_reviewed AND expires_at IS NULL)),
 ADD COLUMN disposition_findings jsonb, ADD COLUMN disposition_sources jsonb,
 ADD COLUMN disposition_plan_id uuid, ADD COLUMN disposition_exit_type text,
 ADD COLUMN disposition_execution_id uuid, ADD COLUMN disposition_title_entry_id uuid,
 ADD COLUMN disposition_title_review_id uuid, ADD COLUMN disposition_title_status text,
 ADD COLUMN disposition_original_review_id uuid, ADD COLUMN disposition_original_status text,
 ADD COLUMN disposition_plan_status text GENERATED ALWAYS AS (CASE WHEN kind='disposition_findings' THEN 'proposed' END) STORED,
 ADD COLUMN disposition_title_kind text GENERATED ALWAYS AS (CASE WHEN kind='disposition_findings' THEN 'title_findings' END) STORED,
 ADD CONSTRAINT acquisition_disposition_original_plan FOREIGN KEY(workspace_id,contract_id,contract_version,disposition_plan_id,disposition_plan_status,disposition_exit_type,disposition_execution_id,disposition_title_entry_id)
 REFERENCES public.acquisition_disposition_plans(workspace_id,contract_id,contract_version,id,status,exit_type,execution_transition_id,title_entry_id),
 ADD CONSTRAINT acquisition_disposition_original_title FOREIGN KEY(workspace_id,contract_id,contract_version,disposition_title_kind,disposition_title_review_id,disposition_title_status,disposition_execution_id)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,id,status,title_execution_transition_id),
 ADD CONSTRAINT acquisition_disposition_review_identity UNIQUE(workspace_id,contract_id,contract_version,kind,id,status,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id,disposition_title_status),
 ADD CONSTRAINT acquisition_disposition_original_review FOREIGN KEY(workspace_id,contract_id,contract_version,kind,disposition_original_review_id,disposition_original_status,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id,disposition_title_status)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,id,status,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id,disposition_title_status),
 ADD CONSTRAINT acquisition_disposition_findings_shape CHECK(
  (kind<>'disposition_findings' AND disposition_findings IS NULL AND disposition_sources IS NULL AND disposition_plan_id IS NULL
   AND disposition_exit_type IS NULL AND disposition_execution_id IS NULL AND disposition_title_entry_id IS NULL AND disposition_title_review_id IS NULL
   AND disposition_title_status IS NULL AND disposition_original_review_id IS NULL AND disposition_original_status IS NULL)
  OR (kind='disposition_findings' AND purpose='purchase_contract' AND disposition_plan_id IS NOT NULL
   AND disposition_exit_type IS NOT NULL AND disposition_exit_type IN ('principal_acquisition','wholesale_assignment')
   AND disposition_execution_id IS NOT NULL AND disposition_title_entry_id IS NOT NULL AND disposition_title_review_id IS NOT NULL
   AND disposition_title_status IS NOT NULL AND disposition_title_status IN ('approved','requires_resolution')
   AND (status<>'approved' OR disposition_title_status='approved') AND (
    (status IN ('approved','requires_resolution') AND disposition_original_review_id IS NULL AND disposition_original_status IS NULL
     AND disposition_findings IS NOT NULL AND private.valid_disposition_findings(disposition_findings,contract_version,status='approved',disposition_exit_type) IS TRUE
     AND disposition_sources IS NOT NULL AND private.valid_disposition_source_journal(disposition_findings,disposition_sources,contract_version,artifact_id,source_version,verification_id,sha256) IS TRUE)
    OR (status='withdrawn' AND disposition_findings IS NULL AND disposition_sources IS NULL AND disposition_original_review_id IS NOT NULL
     AND disposition_original_review_id<>id AND disposition_original_status IS NOT NULL AND disposition_original_status IN ('approved','requires_resolution') AND sequence>1))));
-- Existing grants/RLS, immutable triggers and source/policy FKs remain intact.
-- Generic preparation review writers continue to reject this distinct kind.
COMMIT;
