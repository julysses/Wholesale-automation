-- Preserve legacy five-field findings and exact request fingerprints. Optional
-- binding identities reference reviewed calendar interpretations, not replacement
-- contract terms. Existing execution writers/transition checks remain unchanged
-- and still hold calendar-only findings until the complete locking integration.
-- Compensation: leave calendar execution held; retain findings/review history.
BEGIN;
CREATE OR REPLACE FUNCTION private.valid_execution_findings(value jsonb,p_version integer) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; finding jsonb; source jsonb; binding jsonb; names text[]:=ARRAY[]::text[]; ids uuid[]:=ARRAY[]::uuid[];
BEGIN
 IF value IS NULL OR p_version IS NULL OR p_version<1 OR jsonb_typeof(value)<>'object'
  OR NOT(value ?& ARRAY['seller_signatures','buyer_signatures','signing_authority','complete_agreement','terms'])
  OR EXISTS(SELECT 1 FROM jsonb_object_keys(value) k WHERE k NOT IN ('seller_signatures','buyer_signatures','signing_authority','complete_agreement','terms','deadline_reviews')) THEN RETURN false; END IF;
 FOREACH name IN ARRAY ARRAY['seller_signatures','buyer_signatures','signing_authority','complete_agreement'] LOOP
  finding:=value->name;
  IF jsonb_typeof(finding) IS DISTINCT FROM 'object'
   OR NOT(finding ?& ARRAY['finding','locator','note'])
   OR (SELECT count(*) FROM jsonb_object_keys(finding))<>3
   OR finding->>'finding' IS DISTINCT FROM 'confirmed'
   OR jsonb_typeof(finding->'locator') IS DISTINCT FROM 'string'
   OR length(trim(finding->>'locator')) NOT BETWEEN 1 AND 1000
   OR finding->>'locator' ~ '[[:cntrl:]]'
   OR jsonb_typeof(finding->'note') IS DISTINCT FROM 'string'
   OR length(trim(finding->>'note')) NOT BETWEEN 20 AND 4000 THEN RETURN false; END IF;
 END LOOP;
 IF NOT private.valid_contract_terms(value->'terms') THEN RETURN false; END IF;
 FOR source IN SELECT * FROM jsonb_array_elements(value->'terms'->'sources') LOOP
  IF (source->>'artifact_version')::integer>p_version THEN RETURN false; END IF;
 END LOOP;
 IF value ? 'deadline_reviews' THEN
  IF jsonb_typeof(value->'deadline_reviews') IS DISTINCT FROM 'array'
   OR jsonb_array_length(value->'deadline_reviews') NOT BETWEEN 1 AND 3 THEN RETURN false; END IF;
  FOR binding IN SELECT * FROM jsonb_array_elements(value->'deadline_reviews') LOOP
   IF jsonb_typeof(binding) IS DISTINCT FROM 'object' OR NOT(binding ?& ARRAY['term','review_id'])
    OR (SELECT count(*) FROM jsonb_object_keys(binding))<>2
    OR binding->>'term' IS NULL OR binding->>'term' NOT IN ('effective','inspection_deadline','closing_deadline')
    OR jsonb_typeof(binding->'review_id') IS DISTINCT FROM 'string'
    OR binding->>'review_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    OR binding->>'term'=ANY(names) OR (binding->>'review_id')::uuid=ANY(ids)
    OR value->'terms'->(binding->>'term')->>'precision' IS DISTINCT FROM 'date' THEN RETURN false; END IF;
   names:=array_append(names,binding->>'term'); ids:=array_append(ids,(binding->>'review_id')::uuid);
  END LOOP;
  FOREACH name IN ARRAY ARRAY['effective','inspection_deadline','closing_deadline'] LOOP
   IF value->'terms'->name->>'precision'='date' AND NOT(name=ANY(names)) THEN RETURN false; END IF;
  END LOOP;
 END IF;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_execution_findings(jsonb,integer) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.execution_findings_match(p_workspace uuid,p_contract uuid,p_version integer,
 p_findings jsonb,p_prepared jsonb,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; binding jsonb; review public.acquisition_contract_reviews%ROWTYPE;
 resolved jsonb; compared jsonb; instant jsonb;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR NOT private.valid_execution_findings(p_findings,p_version)
  OR NOT private.valid_contract_terms(p_prepared) THEN RETURN false; END IF;
 resolved:=p_findings->'terms'; compared:=p_prepared;
 FOREACH name IN ARRAY ARRAY['effective','inspection_deadline','closing_deadline'] LOOP
  IF resolved->name->>'precision'='date' THEN
   IF compared->name->>'precision' IS DISTINCT FROM 'date'
    OR compared->name->>'calendar_date' IS DISTINCT FROM resolved->name->>'calendar_date' THEN RETURN false; END IF;
   SELECT value INTO binding FROM jsonb_array_elements(coalesce(p_findings->'deadline_reviews','[]'::jsonb)) WHERE value->>'term'=name;
   IF NOT FOUND THEN RETURN false; END IF;
   SELECT * INTO review FROM public.acquisition_contract_reviews
    WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version
     AND kind='deadline_resolution' AND deadline_term=name AND id=(binding->>'review_id')::uuid;
   IF NOT FOUND OR NOT private.deadline_review_current(review.id,p_at)
    OR review.deadline_resolution->>'calendar_date' IS DISTINCT FROM resolved->name->>'calendar_date' THEN RETURN false; END IF;
   -- Derived copies are used only for ordering/time comparison; callers persist
   -- original findings with date precision and exact interpretation review IDs.
   instant:=jsonb_build_object('precision','instant','instant',review.deadline_resolution->>'resolved_instant');
   resolved:=jsonb_set(resolved,ARRAY[name],instant); compared:=jsonb_set(compared,ARRAY[name],instant);
  END IF;
 END LOOP;
 RETURN private.execution_terms_match(resolved,compared,p_at);
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.execution_findings_match(uuid,uuid,integer,jsonb,jsonb,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
