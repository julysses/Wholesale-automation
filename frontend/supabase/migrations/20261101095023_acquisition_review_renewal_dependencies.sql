-- Bind each new renewal to server-derived supporting review identities.
-- Identity matching is necessary, not sufficient, for current approval.
-- Compensation: leave renewal unavailable; retain snapshots and forward-fix.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN renewal_dependencies jsonb,
 ADD CONSTRAINT acquisition_renewal_dependencies_shape CHECK(renewal_dependencies IS NULL OR
  (renewal_root_id IS NOT NULL AND jsonb_typeof(renewal_dependencies)='array' AND jsonb_array_length(renewal_dependencies)<=3));

CREATE FUNCTION private.acquisition_review_dependency_heads(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; dependency public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; requests jsonb:='[]'; result jsonb:='[]'; item jsonb; effective uuid;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN NULL; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=p_root AND status='approved' AND renewal_root_id IS NULL;
 IF NOT FOUND OR original.created_at>p_at THEN RETURN NULL; END IF;
 CASE original.kind
 WHEN 'deadline_resolution' THEN RETURN '[]'::jsonb;
 WHEN 'executed_contract' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('root_id',b->>'review_id','kind','deadline_resolution','term',b->>'term')),'[]')
   INTO requests FROM jsonb_array_elements(coalesce(original.execution_findings->'deadline_reviews','[]')) b;
 WHEN 'title_findings','disposition_findings' THEN
  SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND id=CASE original.kind WHEN 'title_findings' THEN original.title_execution_transition_id ELSE original.disposition_execution_id END
   AND recorded_status='executed' AND sequence=2;
  IF NOT FOUND THEN RETURN NULL; END IF;
  requests:=jsonb_build_array(jsonb_build_object('root_id',execution.execution_review_id,'kind','executed_contract','term',NULL));
  IF original.kind='disposition_findings' THEN
   requests:=requests||jsonb_build_array(jsonb_build_object('root_id',original.disposition_title_review_id,'kind','title_findings','term',NULL));
  END IF;
 ELSE RETURN NULL;
 END CASE;
 FOR item IN SELECT value FROM jsonb_array_elements(requests) ORDER BY value->>'kind',value->>'term',value->>'root_id' LOOP
  SELECT * INTO dependency FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND id=(item->>'root_id')::uuid AND kind=item->>'kind'
   AND deadline_term IS NOT DISTINCT FROM item->>'term' AND status='approved' AND renewal_root_id IS NULL;
  IF NOT FOUND THEN RETURN NULL; END IF;
  effective:=private.acquisition_review_lineage_head(p_workspace,p_contract,p_version,dependency.id,p_at);
  IF effective IS NULL THEN RETURN NULL; END IF;
  result:=result||jsonb_build_array(jsonb_build_object('root_id',dependency.id,'review_id',effective,'kind',dependency.kind,'term',dependency.deadline_term));
 END LOOP;
 RETURN result;
EXCEPTION WHEN invalid_text_representation OR invalid_parameter_value THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_dependency_heads(uuid,uuid,integer,uuid,timestamptz)
 FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.bind_acquisition_renewal_dependencies() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.renewal_dependencies IS NOT NULL THEN
  RAISE EXCEPTION 'Renewal dependencies are server derived' USING ERRCODE='23514'; END IF;
 IF NEW.renewal_root_id IS NULL THEN RETURN NEW; END IF;
 -- Alphabetical trigger order runs lineage validation and deal locking first.
 NEW.renewal_dependencies:=private.acquisition_review_dependency_heads(NEW.workspace_id,NEW.contract_id,NEW.contract_version,NEW.renewal_root_id,clock_timestamp());
 IF NEW.renewal_dependencies IS NULL THEN
  RAISE EXCEPTION 'Unwithdrawn original supporting reviews required' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.bind_acquisition_renewal_dependencies() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_review_renewal_support BEFORE INSERT ON public.acquisition_contract_reviews
 FOR EACH ROW EXECUTE FUNCTION private.bind_acquisition_renewal_dependencies();

CREATE FUNCTION private.acquisition_review_dependencies_match(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; expected jsonb;
BEGIN
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND status='approved';
 IF NOT FOUND THEN RETURN false; END IF;
 expected:=private.acquisition_review_dependency_heads(review.workspace_id,review.contract_id,review.contract_version,
  coalesce(review.renewal_root_id,review.id),p_at);
 IF expected IS NULL THEN RETURN false; END IF;
 IF review.renewal_root_id IS NOT NULL THEN RETURN review.renewal_dependencies IS NOT NULL AND review.renewal_dependencies=expected; END IF;
 -- Legacy decisions bound the original IDs. New heads cannot silently refresh them.
 RETURN NOT EXISTS(SELECT 1 FROM jsonb_array_elements(expected) d WHERE d->>'root_id' IS DISTINCT FROM d->>'review_id');
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_dependencies_match(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
