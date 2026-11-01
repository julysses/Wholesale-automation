-- Extend the equivalent immutable review entity; no parallel contract/review parent.
-- This migration does not expose an execution-review RPC or seed authority policies.
-- Compensation: keep execution review unavailable / pause acquisition. Retain all
-- historical rows and findings; do not erase outcomes or downgrade contract state.
BEGIN;
CREATE FUNCTION private.valid_execution_findings(value jsonb,p_version integer) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE name text; finding jsonb; source jsonb;
BEGIN
 IF value IS NULL OR p_version IS NULL OR p_version<1 OR jsonb_typeof(value)<>'object'
  OR NOT(value ?& ARRAY['seller_signatures','buyer_signatures','signing_authority','complete_agreement','terms'])
  OR (SELECT count(*) FROM jsonb_object_keys(value))<>5 THEN RETURN false; END IF;
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
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.valid_execution_findings(jsonb,integer) FROM PUBLIC,anon,authenticated,service_role;

-- Replace only the two reviewed-kind constraints, preserving all policy scope,
-- reviewer, expiry, approval reference, foreign keys and unique identities.
DO $$
DECLARE names text[]; name text;
BEGIN
 SELECT array_agg(conname ORDER BY conname) INTO names FROM pg_catalog.pg_constraint
 WHERE conrelid='private.acquisition_contract_review_policies'::regclass AND contype='c'
  AND pg_get_constraintdef(oid) ~ '\mkind\M';
 IF coalesce(array_length(names,1),0)<>2 THEN RAISE EXCEPTION 'Expected two review policy kind constraints'; END IF;
 FOREACH name IN ARRAY names LOOP
  EXECUTE format('ALTER TABLE private.acquisition_contract_review_policies DROP CONSTRAINT %I',name);
 END LOOP;
END $$;
ALTER TABLE private.acquisition_contract_review_policies
 ADD CONSTRAINT acquisition_review_policy_kind CHECK(kind IN ('contract_review','title_review','assignment_basis','executed_contract')),
 ADD CONSTRAINT acquisition_review_policy_purpose CHECK(
  (kind IN ('contract_review','assignment_basis','executed_contract') AND purpose='purchase_contract')
  OR (kind='title_review' AND purpose='title_report'));
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN execution_findings jsonb,
 ADD CONSTRAINT acquisition_execution_findings_shape CHECK(
  (kind<>'executed_contract' AND execution_findings IS NULL)
  OR (kind='executed_contract' AND (
   (status='approved' AND execution_findings IS NOT NULL AND private.valid_execution_findings(execution_findings,contract_version))
   OR (status='withdrawn' AND execution_findings IS NULL))));
-- Existing RLS, restricted grants, evidence/policy FKs and immutable-row trigger
-- remain unchanged. Existing RPCs reject the new kind until controlled writes exist.
COMMIT;
