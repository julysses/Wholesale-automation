-- New personal findings bind the effective supporting decisions at save time.
-- Legacy rows remain untouched; only new originals depending on a renewed head
-- receive a server-derived snapshot. All existing RLS/immutability stays intact.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews ADD COLUMN original_review_dependencies jsonb,
 ADD CONSTRAINT acquisition_original_review_dependencies_shape CHECK(original_review_dependencies IS NULL OR
  (renewal_root_id IS NULL AND status='approved' AND kind IN ('executed_contract','title_findings','disposition_findings')
   AND jsonb_typeof(original_review_dependencies)='array' AND jsonb_array_length(original_review_dependencies) BETWEEN 1 AND 3));
CREATE FUNCTION private.acquisition_review_anchor_head(p_workspace uuid,p_contract uuid,p_version integer,p_anchor uuid,p_at timestamptz)
RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_lineage_head(p_workspace,p_contract,p_version,coalesce(r.renewal_root_id,r.id),p_at)
 FROM public.acquisition_contract_reviews r WHERE r.workspace_id=p_workspace AND r.contract_id=p_contract
  AND r.contract_version=p_version AND r.id=p_anchor AND r.status='approved' AND r.created_at<=p_at
$$;
REVOKE ALL ON FUNCTION private.acquisition_review_anchor_head(uuid,uuid,integer,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.acquisition_review_dependencies_for(p_review public.acquisition_contract_reviews,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE:=p_review; p_workspace uuid:=p_review.workspace_id; p_contract uuid:=p_review.contract_id; p_version integer:=p_review.contract_version; dependency public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; requests jsonb:='[]'; result jsonb:='[]'; item jsonb; effective uuid;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN NULL; END IF;
 IF original.id IS NULL OR original.status<>'approved' OR original.renewal_root_id IS NOT NULL OR original.created_at>p_at THEN RETURN NULL; END IF;
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
   AND deadline_term IS NOT DISTINCT FROM item->>'term' AND status='approved';
  IF NOT FOUND THEN RETURN NULL; END IF;
  effective:=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,dependency.id,p_at);
  IF effective IS NULL THEN RETURN NULL; END IF;
  result:=result||jsonb_build_array(jsonb_build_object('root_id',dependency.id,'review_id',effective,'kind',dependency.kind,'term',dependency.deadline_term));
 END LOOP;
 RETURN result;
EXCEPTION WHEN invalid_text_representation OR invalid_parameter_value THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_dependencies_for(public.acquisition_contract_reviews,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.acquisition_review_dependency_heads(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_dependencies_for(r,p_at) FROM public.acquisition_contract_reviews r
 WHERE r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version AND r.id=p_root
  AND r.status='approved' AND r.renewal_root_id IS NULL
$$;
CREATE FUNCTION private.bind_acquisition_original_review_dependencies() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE dependencies jsonb;
BEGIN
 IF NEW.original_review_dependencies IS NOT NULL THEN RAISE EXCEPTION 'Original review dependencies are server derived' USING ERRCODE='23514'; END IF;
 IF NEW.renewal_root_id IS NOT NULL OR NEW.status<>'approved' OR NEW.kind NOT IN ('executed_contract','title_findings','disposition_findings') THEN RETURN NEW; END IF;
 dependencies:=private.acquisition_review_dependencies_for(NEW,clock_timestamp());
 IF dependencies IS NULL THEN RAISE EXCEPTION 'Original supporting decisions required' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(dependencies) d WHERE d->>'root_id' IS DISTINCT FROM d->>'review_id') THEN
  NEW.original_review_dependencies:=dependencies;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.bind_acquisition_original_review_dependencies() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_review_original_support BEFORE INSERT ON public.acquisition_contract_reviews
 FOR EACH ROW EXECUTE FUNCTION private.bind_acquisition_original_review_dependencies();
CREATE OR REPLACE FUNCTION private.acquisition_review_dependencies_match(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; expected jsonb;
BEGIN
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND status='approved';
 IF NOT FOUND THEN RETURN false; END IF;
 expected:=private.acquisition_review_dependency_heads(review.workspace_id,review.contract_id,review.contract_version,
  coalesce(review.renewal_root_id,review.id),p_at);
 IF expected IS NULL THEN RETURN false; END IF;
 IF review.renewal_root_id IS NOT NULL THEN RETURN review.renewal_dependencies IS NOT NULL AND review.renewal_dependencies=expected; END IF;
 IF review.original_review_dependencies IS NOT NULL THEN RETURN review.original_review_dependencies=expected; END IF;
 -- Legacy decisions bound the original IDs. New heads cannot silently refresh them.
 RETURN NOT EXISTS(SELECT 1 FROM jsonb_array_elements(expected) d WHERE d->>'root_id' IS DISTINCT FROM d->>'review_id');
END $$;
CREATE OR REPLACE FUNCTION private.acquisition_renewal_review_set(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE pending uuid[]:=ARRAY[p_root]; visited uuid[]:=ARRAY[]::uuid[]; selected uuid;
 original public.acquisition_contract_reviews%ROWTYPE; head uuid; dependencies jsonb; item jsonb; result jsonb:='[]';
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR p_root IS NULL THEN RETURN NULL; END IF;
 WHILE cardinality(pending)>0 LOOP
  selected:=pending[1];pending:=pending[2:];
  -- A new original may cite a particular renewed decision. Canonicalize only
  -- the traversal identity; preserve that exact bound ID in its findings/snapshot.
  SELECT coalesce(r.renewal_root_id,r.id) INTO selected FROM public.acquisition_contract_reviews r
   WHERE r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version
    AND r.id=selected AND r.status='approved' AND r.created_at<=p_at;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF selected=ANY(visited) THEN CONTINUE; END IF;
  visited:=array_append(visited,selected);
  -- Three date terms, execution, title and disposition: at most six distinct roots.
  IF cardinality(visited)>6 THEN RETURN NULL; END IF;
  SELECT * INTO original FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND id=selected AND status='approved' AND renewal_root_id IS NULL;
  IF NOT FOUND THEN RETURN NULL; END IF;
  head:=private.acquisition_review_lineage_head(p_workspace,p_contract,p_version,selected,p_at);
  dependencies:=private.acquisition_review_dependency_heads(p_workspace,p_contract,p_version,selected,p_at);
  IF head IS NULL OR dependencies IS NULL THEN RETURN NULL; END IF;
  result:=result||jsonb_build_array(jsonb_build_object('root_id',selected,'review_id',head,'kind',original.kind,'term',original.deadline_term));
  FOR item IN SELECT value FROM jsonb_array_elements(dependencies) LOOP
   pending:=array_append(pending,(item->>'root_id')::uuid);
  END LOOP;
 END LOOP;
 SELECT jsonb_agg(value ORDER BY value->>'root_id') INTO result FROM jsonb_array_elements(result);
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION private.deadline_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; original_source public.acquisition_contract_term_sources%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT coalesce(renewal_root_id,id) INTO p_root FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='deadline_resolution' AND status='approved' AND created_at<=p_at;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='deadline_resolution' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='deadline_resolution'
   AND deadline_term=review.deadline_term ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  JOIN public.workspaces w ON w.id=d.workspace_id AND w.status='active'
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='deadline_resolution'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed','title_review','disposition_review')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_deadline_resolution(review.deadline_resolution,review.contract_version)
  OR prepared->review.deadline_term->>'precision' IS DISTINCT FROM 'date'
  OR prepared->review.deadline_term->>'calendar_date' IS DISTINCT FROM review.deadline_resolution->>'calendar_date'
  OR jsonb_typeof(review.deadline_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.deadline_sources) NOT BETWEEN 1 AND 2 THEN RETURN false; END IF;
 -- The retained interpretation agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 SELECT * INTO original_source FROM public.acquisition_contract_term_sources
  WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version AND term=review.deadline_term;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=original_source.artifact_id::text AND item->>'source_version'=original_source.artifact_version::text
  AND (review.renewal_root_id IS NOT NULL OR item->>'verification_id'=original_source.verification_id::text)
  AND item->>'sha256'=original_source.sha256) THEN RETURN false; END IF;
 -- Renewals may bind a fresh scan of the exact original bytes. Each referenced
 -- scan must still be current under the full scanner/retention/reference checks.
 FOR bound IN SELECT value FROM jsonb_array_elements(review.deadline_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
CREATE OR REPLACE FUNCTION private.execution_findings_effective_match(p_workspace uuid,p_contract uuid,p_version integer,
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
     AND kind='deadline_resolution' AND deadline_term=name AND id=private.acquisition_review_anchor_head(
      p_workspace,p_contract,p_version,(binding->>'review_id')::uuid,p_at);
   IF NOT FOUND OR NOT private.deadline_review_effective_current((binding->>'review_id')::uuid,p_at)
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
CREATE OR REPLACE FUNCTION private.execution_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; source jsonb; binding jsonb; interpretation public.acquisition_contract_reviews%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT coalesce(renewal_root_id,id) INTO p_root FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='executed_contract' AND status='approved' AND created_at<=p_at;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='executed_contract' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  JOIN public.workspaces w ON w.id=d.workspace_id AND w.status='active'
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='executed_contract'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed','title_review','disposition_review')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_execution_findings(review.execution_findings,review.contract_version)
  OR NOT private.execution_findings_effective_match(review.workspace_id,review.contract_id,review.contract_version,review.execution_findings,prepared,p_at)
  OR jsonb_typeof(review.execution_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.execution_sources) NOT BETWEEN 1 AND 13 THEN RETURN false; END IF;
 -- The retained main agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 FOR source IN SELECT value FROM jsonb_array_elements(review.execution_findings->'terms'->'sources') LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
   item->>'artifact_id'=source->>'artifact_id' AND item->>'source_version'=source->>'artifact_version'
   AND item->>'sha256'=source->>'sha256') THEN RETURN false; END IF;
 END LOOP;
 FOR binding IN SELECT value FROM jsonb_array_elements(coalesce(review.execution_findings->'deadline_reviews','[]'::jsonb)) LOOP
  SELECT * INTO interpretation FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(
    review.workspace_id,review.contract_id,review.contract_version,(binding->>'review_id')::uuid,p_at)
   AND workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version
   AND kind='deadline_resolution' AND deadline_term=binding->>'term';
  IF NOT FOUND OR review.expires_at>interpretation.expires_at THEN RETURN false; END IF;
  FOR source IN SELECT value FROM jsonb_array_elements(interpretation.deadline_sources) LOOP
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
    item->>'artifact_id'=source->>'artifact_id' AND item->>'source_version'=source->>'source_version'
    AND item->>'verification_id'=source->>'verification_id' AND item->>'sha256'=source->>'sha256'
    AND item->>'purpose'=source->>'purpose') THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.execution_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
CREATE OR REPLACE FUNCTION private.title_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; bound jsonb; fresh_until timestamptz;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT coalesce(renewal_root_id,id) INTO p_root FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='title_findings' AND status='approved' AND created_at<=p_at;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='title_findings' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.title_policy_snapshot IS NULL OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=review.workspace_id AND id=review.policy_id;
 IF NOT FOUND OR to_jsonb(policy) IS DISTINCT FROM review.title_policy_snapshot OR policy.revoked_at IS NOT NULL
  OR policy.kind<>'title_findings' OR policy.purpose<>'title_report' OR policy.reviewer_id<>review.actor_id
  OR policy.valid_from>review.created_at OR policy.valid_until<=p_at OR review.expires_at>policy.valid_until
  OR review.expires_at>review.created_at+make_interval(secs=>policy.max_review_seconds) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.deals d JOIN public.workspaces w ON w.id=d.workspace_id
  JOIN public.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.user_id=m.user_id AND s.id=review.session_id
  WHERE d.workspace_id=review.workspace_id AND d.id=review.contract_id AND d.acquisition_version=review.contract_version
   AND d.acquisition_status IN ('title_review','disposition_review') AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin')
   AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
   AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))) THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=review.title_execution_transition_id
  AND workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version
  AND sequence=2 AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=review.workspace_id
  AND contract_id=review.contract_id AND contract_version=review.contract_version AND sequence=3 AND recorded_status='title_review'
  AND execution_review_id=execution.execution_review_id)
  OR NOT private.execution_review_effective_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(review.workspace_id,review.contract_id,review.contract_version,execution.execution_review_id,p_at)) THEN RETURN false; END IF;
 IF private.valid_title_findings(review.title_findings,review.contract_version,true) IS DISTINCT FROM true
  OR private.valid_title_source_journal(review.title_findings,review.title_sources,review.contract_version,review.artifact_id,
   review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 fresh_until:=private.title_report_fresh_until(review.title_findings->'report_as_of',policy,p_at);
 IF fresh_until IS NULL OR review.expires_at>fresh_until THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.title_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(
    review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
CREATE OR REPLACE FUNCTION private.disposition_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 plan public.acquisition_disposition_plans%ROWTYPE; execution public.acquisition_contract_transitions%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 bound jsonb;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT coalesce(renewal_root_id,id) INTO p_root FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='disposition_findings' AND status='approved' AND created_at<=p_at;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='disposition_findings' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.disposition_policy_snapshot IS NULL OR review.id IS DISTINCT FROM (
   SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
    AND contract_version=review.contract_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1)
  OR NOT private.disposition_policy_current(review.workspace_id,review.policy_id,review.actor_id,
   review.disposition_exit_type,p_at,review.disposition_policy_snapshot) THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=review.policy_id;
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE policy_id=review.policy_id;
 IF policy.valid_from>review.created_at OR scope.valid_from>review.created_at
  OR review.expires_at>least(policy.valid_until,scope.valid_until,review.created_at+make_interval(secs=>policy.max_review_seconds))
  OR NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
   JOIN public.workspaces w ON w.id=m.workspace_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=review.session_id
   WHERE m.workspace_id=review.workspace_id AND m.user_id=review.actor_id AND w.status='active' AND m.status='active'
    AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
    AND (sess.not_after IS NULL OR (p_at<sess.not_after AND review.expires_at<=sess.not_after))) THEN RETURN false; END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR plan.id<>review.disposition_plan_id OR plan.status<>'proposed' OR plan.exit_type<>review.disposition_exit_type
  OR plan.execution_transition_id<>review.disposition_execution_id OR plan.title_entry_id<>review.disposition_title_entry_id THEN RETURN false; END IF;
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version AND kind='title_findings'
  AND id=private.acquisition_review_anchor_head(review.workspace_id,review.contract_id,review.contract_version,review.disposition_title_review_id,p_at);
 IF NOT FOUND OR title.title_execution_transition_id<>plan.execution_transition_id
  OR NOT private.title_review_effective_current(review.disposition_title_review_id,p_at) OR review.expires_at>title.expires_at THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=plan.execution_transition_id;
 IF NOT FOUND OR NOT private.execution_review_effective_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(review.workspace_id,review.contract_id,review.contract_version,execution.execution_review_id,p_at)) THEN RETURN false; END IF;
 IF private.valid_disposition_findings(review.disposition_findings,review.contract_version,true,plan.exit_type) IS DISTINCT FROM true
  OR private.valid_disposition_source_journal(review.disposition_findings,review.disposition_sources,review.contract_version,
   review.artifact_id,review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 IF plan.exit_type='wholesale_assignment' AND (NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_findings->'assignment'->'legal_basis'->'sources') c
    WHERE c->>'artifact_id'=scope.legal_source_id::text) OR NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_sources) c WHERE c->>'artifact_id'=scope.legal_source_id::text)) THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.disposition_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(
   SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
CREATE OR REPLACE FUNCTION private.title_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; status_name text; source_ref record;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; scan public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 deadline timestamptz; approval_deadline timestamptz; calendar_supported boolean:=false;
 candidate jsonb:=NULL; resolution jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 state:=private.title_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 IF prior.status IN ('approved','requires_resolution') AND prior.actor_id=auth.uid() AND prior.sequence<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'artifact_id',prior.artifact_id,'source_version',prior.source_version,
   'verification_id',prior.verification_id,'policy_id',prior.policy_id,'expected_sequence',prior.sequence,'original_status',prior.status);
 END IF;
 -- A null selection can still recover/withdraw the latest original decision.
 IF p_artifact IS NOT NULL THEN
  SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
  IF NOT FOUND THEN RAISE EXCEPTION 'Title report reference unavailable' USING ERRCODE='42501'; END IF;
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=source_ref.source_version AND id=p_artifact AND purpose='title_report' AND campaign_id IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Original title report unavailable' USING ERRCODE='42501'; END IF;
  SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND kind='title_findings'
  AND purpose='title_report' AND reviewer_id=auth.uid() AND revoked_at IS NULL AND valid_from<=checked AND checked<valid_until
  ORDER BY valid_from DESC,id DESC LIMIT 1;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND sequence=2 AND recorded_status='executed';
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='title_review')
  OR execution.id IS NULL OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND sequence=3 AND recorded_status='title_review' AND execution_review_id=execution.execution_review_id) THEN status_name:='contract_unavailable';
 ELSIF coalesce(prior.sequence,0)>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF p_artifact IS NULL THEN status_name:='document_required';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSIF source_ref.link_revoked OR scan.id IS NULL OR NOT private.contract_review_evidence_current(p_workspace,p_contract,source_ref.source_version,p_artifact,scan.id,artifact.expected_sha256,'title_report',checked) THEN status_name:='evidence_review_required';
 ELSE
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,scanner_session.not_after,
   reviewer_session.not_after,policy.valid_until,checked+make_interval(secs=>policy.max_review_seconds)) INTO deadline
  FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose='title_report'
  JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
  JOIN auth.sessions scanner_session ON scanner_session.id=scan.session_id AND scanner_session.user_id=scan.actor_id
  JOIN auth.sessions reviewer_session ON reviewer_session.id=(auth.jwt()->>'session_id')::uuid AND reviewer_session.user_id=auth.uid()
  WHERE k.workspace_id=p_workspace AND k.id=scan.key_id;
  IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
  ELSE
   resolution:=jsonb_build_object('artifact_id',p_artifact,'source_version',source_ref.source_version,'verification_id',scan.id,
    'sha256',artifact.expected_sha256,'policy_id',policy.id,'available_until',deadline,'expected_sequence',(state->>'sequence')::integer);
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,execution.execution_review_id,checked);
   calendar_supported:=policy.title_report_max_age_days IS NOT NULL AND EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=policy.title_report_timezone);
   IF NOT private.execution_review_current(executed.id,checked) THEN status_name:='execution_review_required';
   ELSIF policy.title_report_max_age_seconds IS NULL AND NOT calendar_supported THEN status_name:='report_freshness_policy_required';
   ELSE
    approval_deadline:=least(deadline,executed.expires_at);
    IF approval_deadline<=checked THEN status_name:='execution_review_required';
    ELSE
     status_name:='ready_for_human_review';
     candidate:=resolution||jsonb_build_object('max_expires_at',approval_deadline,'report_policy',jsonb_build_object(
      'max_age_seconds',policy.title_report_max_age_seconds,
      'max_age_days',CASE WHEN calendar_supported THEN policy.title_report_max_age_days END,
      'timezone',CASE WHEN calendar_supported THEN policy.title_report_timezone END));
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'artifact_id',p_artifact,
  'status',status_name,'candidate',candidate,'resolution',resolution,'withdrawal',withdrawal,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.disposition_review_candidate(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; status_name text;
 prior public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 executed public.acquisition_contract_reviews%ROWTYPE; execution public.acquisition_contract_transitions%ROWTYPE;
 plan public.acquisition_disposition_plans%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 scope private.acquisition_disposition_policy_scopes%ROWTYPE; root jsonb; legal jsonb;
 deadline timestamptz; approval_deadline timestamptz; reviewer_expires timestamptz;
 candidate jsonb:=NULL; resolution jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 state:=private.disposition_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
 IF prior.status IN ('approved','requires_resolution') AND prior.actor_id=auth.uid() AND prior.sequence<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'plan_id',prior.disposition_plan_id,'exit_type',prior.disposition_exit_type,
   'policy_id',prior.policy_id,'expected_sequence',prior.sequence,'original_status',prior.status);
 END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=plan.execution_transition_id AND recorded_status='executed';
 SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,execution.execution_review_id,checked);
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 SELECT p.* INTO policy FROM private.acquisition_contract_review_policies p
 JOIN private.acquisition_disposition_policy_scopes s ON s.policy_id=p.id AND s.workspace_id=p.workspace_id AND s.reviewer_id=p.reviewer_id
 WHERE p.workspace_id=p_workspace AND p.reviewer_id=auth.uid() AND s.exit_type=plan.exit_type
  AND private.disposition_policy_current(p_workspace,p.id,auth.uid(),plan.exit_type,checked,jsonb_build_object('reviewer',to_jsonb(p),'scope',to_jsonb(s)))
 ORDER BY p.valid_from DESC,p.id DESC LIMIT 1;
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE policy_id=policy.id;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='title_review') THEN status_name:='contract_unavailable';
 ELSIF coalesce(prior.sequence,0)>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF plan.id IS NULL OR plan.status<>'proposed' THEN status_name:='proposal_required';
 ELSIF execution.id IS NULL OR executed.id IS NULL OR executed.kind<>'executed_contract' OR executed.status<>'approved'
  OR executed.purpose<>'purchase_contract' OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace
   AND contract_id=p_contract AND contract_version=p_version AND id=plan.title_entry_id AND recorded_status='title_review'
   AND execution_review_id=execution.execution_review_id) THEN status_name:='contract_unavailable';
 ELSIF title.id IS NULL OR title.status NOT IN ('approved','requires_resolution') OR title.title_execution_transition_id<>execution.id THEN status_name:='title_findings_required';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSE
  root:=private.disposition_source_choice(p_workspace,p_contract,p_version,executed.artifact_id,executed.verification_id,checked);
  IF root IS NULL OR root->>'sha256'<>executed.sha256 OR (root->>'source_version')::integer<>executed.source_version THEN status_name:='evidence_review_required';
  ELSE
   IF scope.legal_source_id IS NOT NULL THEN
    legal:=private.disposition_source_choice(p_workspace,p_contract,p_version,scope.legal_source_id,
     CASE WHEN scope.legal_source_id=executed.artifact_id THEN executed.verification_id END,checked);
   END IF;
   SELECT not_after INTO reviewer_expires FROM auth.sessions WHERE id=(auth.jwt()->>'session_id')::uuid AND user_id=auth.uid();
   deadline:=least((root->>'expires_at')::timestamptz,policy.valid_until,scope.valid_until,reviewer_expires,checked+make_interval(secs=>policy.max_review_seconds));
   IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
   ELSE
    resolution:=jsonb_build_object('plan_id',plan.id,'exit_type',plan.exit_type,'policy_id',policy.id,
     'execution_transition_id',execution.id,'title_entry_id',plan.title_entry_id,'title_review_id',title.id,'title_status',title.status,
     'expected_sequence',(state->>'sequence')::integer,'available_until',deadline,'executed_source',root,'legal_source',legal);
    IF NOT private.execution_review_current(executed.id,checked) THEN status_name:='execution_review_required';
    ELSIF NOT private.title_review_current(title.id,checked) THEN status_name:='title_review_required';
    ELSIF plan.exit_type='wholesale_assignment' AND legal IS NULL THEN status_name:='legal_evidence_required';
    ELSE
     approval_deadline:=least(deadline,executed.expires_at,title.expires_at,(legal->>'expires_at')::timestamptz);
     IF approval_deadline<=checked THEN status_name:='title_review_required';
     ELSE
      status_name:='ready_for_human_review';candidate:=resolution||jsonb_build_object('max_expires_at',approval_deadline);
     END IF;
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'status',status_name,'candidate',candidate,'resolution',resolution,'withdrawal',withdrawal,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.resolve_disposition_review_sources(p_workspace uuid,p_contract uuid,p_version integer,p_plan uuid,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE authority record; ref record; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 verification public.acquisition_evidence_verifications%ROWTYPE; citation jsonb; bound jsonb;
 citations jsonb:='[]'; sources jsonb:='[]'; name text; source_id uuid; source_deadline timestamptz;
 checked timestamptz; deadline timestamptz; active boolean;
 plan public.acquisition_disposition_plans%ROWTYPE; executed public.acquisition_contract_transitions%ROWTYPE;
 original public.acquisition_contract_reviews%ROWTYPE; p_artifact uuid; p_verification uuid;
BEGIN
 IF p_workspace IS NULL OR p_contract IS NULL OR p_plan IS NULL
  OR private.valid_disposition_findings(p_findings,p_version,false,p_findings->>'exit_type') IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Exact disposition findings and original proposal required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true OR NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract
  AND acquisition_version=p_version AND acquisition_status='title_review') THEN
  RAISE EXCEPTION 'Current active disposition preparation context required' USING ERRCODE='55000'; END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=p_plan AND status='proposed';
 IF NOT FOUND OR plan.exit_type IS DISTINCT FROM p_findings->>'exit_type'
  OR plan.id IS DISTINCT FROM (SELECT id FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version ORDER BY sequence DESC LIMIT 1) THEN
  RAISE EXCEPTION 'Current exact purchase-path proposal required' USING ERRCODE='55000'; END IF;
 SELECT * INTO executed FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=plan.execution_transition_id AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=plan.title_entry_id AND recorded_status='title_review' AND execution_review_id=executed.execution_review_id) THEN
  RAISE EXCEPTION 'Original recorded execution and title entry required' USING ERRCODE='55000'; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,executed.execution_review_id,clock_timestamp()) AND kind='executed_contract' AND status='approved' AND purpose='purchase_contract';
 IF NOT FOUND THEN RAISE EXCEPTION 'Original execution review required' USING ERRCODE='55000'; END IF;
 p_artifact:=original.artifact_id; p_verification:=original.verification_id;
 citations:=private.disposition_citations(p_findings);
 IF (p_findings->'contractual_interest'->>'finding'='satisfactory' AND NOT EXISTS(
    SELECT 1 FROM jsonb_array_elements(p_findings->'contractual_interest'->'sources') item WHERE item->>'artifact_id'=p_artifact::text))
  OR (plan.exit_type='wholesale_assignment' AND p_findings->'assignment'->'assignment_provisions'->>'finding'='satisfactory' AND NOT EXISTS(
    SELECT 1 FROM jsonb_array_elements(p_findings->'assignment'->'assignment_provisions'->'sources') item WHERE item->>'artifact_id'=p_artifact::text)) THEN
  RAISE EXCEPTION 'Satisfactory contract findings must cite the recorded executed original' USING ERRCODE='55000'; END IF;
 FOR source_id IN SELECT id FROM (SELECT p_artifact AS id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(citations)) originals ORDER BY id LOOP
  SELECT * INTO ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,source_id);
  IF NOT FOUND OR ref.link_revoked THEN RAISE EXCEPTION 'Current original disposition source reference required' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||source_id::text,0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=ref.source_version AND id=source_id AND campaign_id IS NULL;
  IF NOT FOUND OR (source_id=p_artifact AND (artifact.purpose<>'purchase_contract' OR artifact.contract_version<>original.source_version OR artifact.expected_sha256<>original.sha256)) THEN
   RAISE EXCEPTION 'Original disposition source unavailable' USING ERRCODE='55000'; END IF;
  FOR citation IN SELECT value FROM jsonb_array_elements(citations) WHERE value->>'artifact_id'=source_id::text LOOP
   IF (citation->>'artifact_version')::integer<>artifact.contract_version OR citation->>'sha256'<>artifact.expected_sha256 THEN
    RAISE EXCEPTION 'Original disposition citation changed' USING ERRCODE='55000'; END IF;
  END LOOP;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
  SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=source_id
   ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND OR (source_id=p_artifact AND verification.id<>p_verification) THEN
   RAISE EXCEPTION 'Exact current disposition scan required' USING ERRCODE='55000'; END IF;
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after) INTO source_deadline
   FROM private.acquisition_evidence_verification_keys k
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
   JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=verification.session_id AND s.user_id=m.user_id
   WHERE k.id=verification.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,ks,rp,m,profile,s;
  IF source_deadline IS NULL THEN RAISE EXCEPTION 'Disposition source authority missing' USING ERRCODE='55000'; END IF;
  sources:=sources||jsonb_build_array(jsonb_build_object('artifact_id',source_id,'source_version',artifact.contract_version,
   'verification_id',verification.id,'sha256',artifact.expected_sha256,'purpose',artifact.purpose,'expires_at',source_deadline));
  deadline:=least(deadline,source_deadline);
 END LOOP;
 checked:=clock_timestamp();
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=checked THEN RAISE EXCEPTION 'Disposition session expired' USING ERRCODE='42501'; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
  IF (bound->>'expires_at')::timestamptz<=checked OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
   (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,
   bound->>'sha256',bound->>'purpose',checked) THEN
   RAISE EXCEPTION 'Disposition source authority changed while waiting' USING ERRCODE='55000'; END IF;
 END LOOP;
 -- The caller must recheck these exact sources after any subsequent waits and
 -- independently bind current execution/deadline/title/reviewer/legal policy authority.
 RETURN jsonb_build_object('plan_id',plan.id,'exit_type',plan.exit_type,'execution_transition_id',executed.id,
  'execution_review_id',original.id,'title_entry_id',plan.title_entry_id,'artifact_id',p_artifact,'source_version',original.source_version,
  'verification_id',p_verification,'sha256',original.sha256,'sources',sources,'checked_at',checked,'expires_at',least(deadline,authority.session_expires),
  'legal_review_approved',false,'disposition_approved',false,'marketing_authorized',false,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.record_title_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_artifact uuid,p_verification uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 sources jsonb; resolved jsonb; bound jsonb; originals jsonb:='[]'; name text; fingerprint text;
 seq integer; stamped timestamptz; fresh_until timestamptz;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('approved','requires_resolution','withdrawn')
  OR p_artifact IS NULL OR p_verification IS NULL OR p_policy IS NULL OR p_personally_reviewed IS NULL
  OR p_note IS NULL OR length(btrim(p_note,E' \t\n\r\f\v'))<20 OR length(p_note)>4000
  OR (p_status<>'withdrawn' AND (NOT p_personally_reviewed OR private.valid_title_findings(p_findings,p_version,p_status='approved') IS DISTINCT FROM true))
  OR (p_status='approved' AND (p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='requires_resolution' AND p_expires IS NOT NULL)
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL OR p_findings IS NOT NULL)) THEN
  RAISE EXCEPTION 'Exact human title review required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,'title_findings',p_expected_sequence,
  p_status,p_artifact,p_verification,p_policy,p_expires,p_personally_reviewed,p_note,p_findings,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Title request conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Title review sequence changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS NULL OR prior.status NOT IN ('approved','requires_resolution') OR prior.actor_id<>auth.uid()
    OR prior.policy_id<>p_policy OR prior.artifact_id<>p_artifact OR prior.verification_id<>p_verification THEN
    RAISE EXCEPTION 'Original title decision required for withdrawal' USING ERRCODE='55000'; END IF;
   artifact.purpose:=prior.purpose;artifact.expected_sha256:=prior.sha256;artifact.contract_version:=prior.source_version;
   execution.id:=prior.title_execution_transition_id;
  ELSE
   SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=2 AND recorded_status='executed';
   IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=3 AND recorded_status='title_review' AND execution_review_id=execution.execution_review_id) THEN
    RAISE EXCEPTION 'Exact recorded execution and title entry required' USING ERRCODE='55000'; END IF;
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,execution.execution_review_id,clock_timestamp());
   -- Lock the combined original set before acquiring scanner/policy locks. The
   -- contract context serializes reference edits, review withdrawals and stages.
   IF p_findings->'report_as_of_source'<>'null'::jsonb THEN originals:=jsonb_build_array(p_findings->'report_as_of_source'); END IF;
   FOREACH name IN ARRAY ARRAY['ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession'] LOOP originals:=originals||(p_findings->name->'sources'); END LOOP;
   FOR bound IN SELECT jsonb_build_object('artifact_id',id,'sha256',expected_sha256) FROM public.acquisition_evidence_artifacts
    WHERE workspace_id=p_workspace AND contract_id=p_contract AND id IN (
     SELECT p_artifact UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)
     UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(executed.execution_sources)) ORDER BY id LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
   END LOOP;
   resolved:=private.resolve_title_review_sources(p_workspace,p_contract,p_version,p_artifact,p_verification,p_findings);
   sources:=resolved->'sources';
   IF p_status='approved' THEN
    PERFORM private.lock_acquisition_renewal_authority(p_workspace,p_contract,p_version,
     coalesce(executed.renewal_root_id,executed.id),p_policy);
   END IF;
   SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy
    AND kind='title_findings' AND purpose='title_report' AND reviewer_id=auth.uid() FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed title authority required' USING ERRCODE='42501'; END IF;
   stamped:=clock_timestamp();
   IF policy.revoked_at IS NOT NULL OR policy.valid_from>stamped OR policy.valid_until<=stamped THEN RAISE EXCEPTION 'Title policy unavailable' USING ERRCODE='55000'; END IF;
   IF p_status='approved' THEN
    fresh_until:=private.title_report_fresh_until(p_findings->'report_as_of',policy,stamped);
    IF fresh_until IS NULL OR p_expires<=stamped OR p_expires>least(fresh_until,policy.valid_until,
      stamped+make_interval(secs=>policy.max_review_seconds),(resolved->>'expires_at')::timestamptz,executed.expires_at)
     OR NOT private.execution_review_current(executed.id,stamped) THEN
     RAISE EXCEPTION 'Current bounded title and execution review required' USING ERRCODE='55000'; END IF;
   END IF;
   FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
    IF (bound->>'expires_at')::timestamptz<=stamped OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
     (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',stamped) THEN
     RAISE EXCEPTION 'Title source changed while waiting' USING ERRCODE='55000'; END IF;
   END LOOP;
   SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND id=p_artifact;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN
   RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,
   purpose,sha256,policy_id,actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,
   title_findings,title_sources,title_execution_transition_id,title_original_review_id,title_original_status,title_policy_snapshot)
  VALUES(p_id,p_workspace,p_contract,p_version,'title_findings',seq+1,p_status,p_artifact,p_verification,artifact.purpose,artifact.expected_sha256,p_policy,
   auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,p_expires,fingerprint,stamped,artifact.contract_version,
   p_findings,sources,execution.id,CASE WHEN p_status='withdrawn' THEN prior.id END,CASE WHEN p_status='withdrawn' THEN prior.status END,
   CASE WHEN p_status<>'withdrawn' THEN to_jsonb(policy) END) RETURNING * INTO saved;
  -- A separate statement checks the exact persisted snapshot at final write time.
  IF p_status='approved' AND NOT private.title_review_current(saved.id,clock_timestamp()) THEN
   RAISE EXCEPTION 'Title approval authority changed before save' USING ERRCODE='55000'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,
   'contract_version',p_version,'kind','title_findings','sequence',saved.sequence,'execution_transition_id',execution.id,
   'original_review_id',saved.title_original_review_id,'sources',sources,'policy_id',p_policy,'expires_at',p_expires,'execution_authorized',false));
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.record_disposition_review(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_plan uuid,p_original_review uuid,p_policy uuid,p_expires timestamptz,p_personally_reviewed boolean,p_note text,p_findings jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 title public.acquisition_contract_reviews%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; plan public.acquisition_disposition_plans%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 resolved jsonb; sources jsonb; bound jsonb; originals jsonb; snapshot jsonb; fingerprint text; seq integer; stamped timestamptz;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('approved','requires_resolution','withdrawn') OR p_plan IS NULL OR p_policy IS NULL
  OR p_personally_reviewed IS NULL OR p_note IS NULL OR length(btrim(p_note,E' \t\n\r\f\v'))<20 OR length(p_note)>4000
  OR (p_status<>'withdrawn' AND (NOT p_personally_reviewed OR p_original_review IS NOT NULL
   OR private.valid_disposition_findings(p_findings,p_version,p_status='approved',p_findings->>'exit_type') IS DISTINCT FROM true))
  OR (p_status='approved' AND (p_expires IS NULL OR NOT isfinite(p_expires)))
  OR (p_status='requires_resolution' AND p_expires IS NOT NULL)
  OR (p_status='withdrawn' AND (p_personally_reviewed OR p_expires IS NOT NULL OR p_findings IS NOT NULL
   OR p_original_review IS NULL OR p_original_review=p_id OR p_expected_sequence<1)) THEN
  RAISE EXCEPTION 'Exact human disposition review required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('contract-review:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,'disposition_findings',p_expected_sequence,
  p_status,p_plan,p_original_review,p_policy,p_expires,p_personally_reviewed,p_note,p_findings,auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_contract_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Disposition request conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Disposition sequence changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS DISTINCT FROM p_original_review OR prior.status NOT IN ('approved','requires_resolution')
    OR prior.actor_id<>auth.uid() OR prior.policy_id<>p_policy OR prior.disposition_plan_id<>p_plan THEN
    RAISE EXCEPTION 'Original personal disposition decision required' USING ERRCODE='55000'; END IF;
   plan.id:=prior.disposition_plan_id;plan.exit_type:=prior.disposition_exit_type;
   plan.execution_transition_id:=prior.disposition_execution_id;plan.title_entry_id:=prior.disposition_title_entry_id;
   title.id:=prior.disposition_title_review_id;title.status:=prior.disposition_title_status;
   resolved:=jsonb_build_object('artifact_id',prior.artifact_id,'verification_id',prior.verification_id,'source_version',prior.source_version,'sha256',prior.sha256);
  ELSE
   SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND id=p_plan AND status='proposed';
   IF NOT FOUND THEN RAISE EXCEPTION 'Original disposition proposal required' USING ERRCODE='55000'; END IF;
   SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=plan.execution_transition_id;
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_anchor_head(p_workspace,p_contract,p_version,execution.execution_review_id,clock_timestamp());
   SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
   IF NOT FOUND OR title.status NOT IN ('approved','requires_resolution') OR title.title_execution_transition_id<>plan.execution_transition_id THEN
    RAISE EXCEPTION 'Record original title findings before disposition review' USING ERRCODE='55000'; END IF;
   originals:=private.disposition_citations(p_findings)||coalesce(executed.execution_sources,'[]')||coalesce(title.title_sources,'[]');
   FOR bound IN SELECT jsonb_build_object('artifact_id',id,'sha256',expected_sha256) FROM public.acquisition_evidence_artifacts
    WHERE workspace_id=p_workspace AND contract_id=p_contract AND id IN (
     SELECT executed.artifact_id UNION SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)) ORDER BY id LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'artifact_id'),0));
    PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||(bound->>'sha256'),0));
   END LOOP;
   resolved:=private.resolve_disposition_review_sources(p_workspace,p_contract,p_version,p_plan,p_findings);sources:=resolved->'sources';
   IF p_status='approved' THEN
    PERFORM private.lock_acquisition_renewal_authority(p_workspace,p_contract,p_version,
     coalesce(title.renewal_root_id,title.id),p_policy);
   END IF;
   SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=p_policy
    AND kind='disposition_findings' AND purpose='purchase_contract' AND reviewer_id=auth.uid() FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed disposition policy required' USING ERRCODE='42501'; END IF;
   SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=p_policy
    AND reviewer_id=auth.uid() AND exit_type=plan.exit_type FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed exit-specific policy required' USING ERRCODE='42501'; END IF;
   snapshot:=jsonb_build_object('reviewer',to_jsonb(policy),'scope',to_jsonb(scope));stamped:=clock_timestamp();
   IF NOT private.disposition_policy_current(p_workspace,p_policy,auth.uid(),plan.exit_type,stamped,snapshot) THEN
    RAISE EXCEPTION 'Disposition policy unavailable' USING ERRCODE='55000'; END IF;
   IF plan.exit_type='wholesale_assignment' AND (p_status='approved' OR p_findings->'assignment'->'legal_basis'->>'finding'='satisfactory') AND (NOT EXISTS(
    SELECT 1 FROM jsonb_array_elements(p_findings->'assignment'->'legal_basis'->'sources') c WHERE c->>'artifact_id'=scope.legal_source_id::text)
    OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(sources) c WHERE c->>'artifact_id'=scope.legal_source_id::text)) THEN
    RAISE EXCEPTION 'Policy-bound original legal evidence required' USING ERRCODE='55000'; END IF;
   IF p_status='approved' AND (p_expires<=stamped OR p_expires>least(policy.valid_until,scope.valid_until,
    stamped+make_interval(secs=>policy.max_review_seconds),(resolved->>'expires_at')::timestamptz,executed.expires_at,title.expires_at)
    OR NOT private.title_review_current(title.id,stamped) OR NOT private.execution_review_current(executed.id,stamped)) THEN
    RAISE EXCEPTION 'Current bounded title, execution and disposition authority required' USING ERRCODE='55000'; END IF;
   FOR bound IN SELECT value FROM jsonb_array_elements(sources) LOOP
    IF (bound->>'expires_at')::timestamptz<=stamped OR NOT private.contract_review_evidence_current(p_workspace,p_contract,
     (bound->>'source_version')::integer,(bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',stamped) THEN
     RAISE EXCEPTION 'Disposition source changed while waiting' USING ERRCODE='55000'; END IF;
   END LOOP;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND (authority.session_expires<=stamped OR (p_status='approved' AND p_expires>authority.session_expires)) THEN
   RAISE EXCEPTION 'Review session expired' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_contract_reviews(id,workspace_id,contract_id,contract_version,kind,sequence,status,artifact_id,verification_id,
   purpose,sha256,policy_id,actor_id,session_id,actor_membership_updated_at,personally_reviewed,note,expires_at,request_hash,created_at,evidence_version,
   disposition_findings,disposition_sources,disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,
   disposition_title_review_id,disposition_title_status,disposition_original_review_id,disposition_original_status,disposition_policy_snapshot)
  VALUES(p_id,p_workspace,p_contract,p_version,'disposition_findings',seq+1,p_status,(resolved->>'artifact_id')::uuid,(resolved->>'verification_id')::uuid,
   'purchase_contract',resolved->>'sha256',p_policy,auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,p_personally_reviewed,p_note,
   p_expires,fingerprint,stamped,(resolved->>'source_version')::integer,p_findings,sources,plan.id,plan.exit_type,plan.execution_transition_id,plan.title_entry_id,
   title.id,title.status,CASE WHEN p_status='withdrawn' THEN prior.id END,CASE WHEN p_status='withdrawn' THEN prior.status END,snapshot) RETURNING * INTO saved;
  IF p_status='approved' AND NOT private.disposition_review_current(saved.id,clock_timestamp()) THEN
   RAISE EXCEPTION 'Disposition authority changed before save' USING ERRCODE='55000'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_contract_review',p_id::text,p_status,auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,
   'contract_version',p_version,'kind','disposition_findings','sequence',saved.sequence,'plan_id',plan.id,'exit_type',plan.exit_type,
   'title_review_id',title.id,'original_review_id',saved.disposition_original_review_id,'sources',sources,'policy_id',p_policy,
   'expires_at',p_expires,'execution_authorized',false));
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
   'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',false,'review_recorded',true,'approval_current',false,'execution_authorized',false);
 END IF;
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'kind',saved.kind,'sequence',saved.sequence,'status',saved.status,'duplicate',true,'review_recorded',true,'approval_current',false,'execution_authorized',false);
END $$;
-- Compensation: pause acquisition and forward-correct the functions. Keep the
-- additive snapshot column and immutable evidence; never rewrite historical approvals.
COMMIT;
