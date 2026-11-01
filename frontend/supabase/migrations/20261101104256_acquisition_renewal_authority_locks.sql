-- Private complete renewal support set and lock orchestration.
-- No exposed save/read API or permission grant. Locks are not approval.
-- Compensation: retain history and leave renewal unavailable pending forward fix.
BEGIN;
CREATE FUNCTION private.acquisition_renewal_review_set(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE pending uuid[]:=ARRAY[p_root]; visited uuid[]:=ARRAY[]::uuid[]; selected uuid;
 original public.acquisition_contract_reviews%ROWTYPE; head uuid; dependencies jsonb; item jsonb; result jsonb:='[]';
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR p_root IS NULL THEN RETURN NULL; END IF;
 WHILE cardinality(pending)>0 LOOP
  selected:=pending[1];pending:=pending[2:];
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
REVOKE ALL ON FUNCTION private.acquisition_renewal_review_set(uuid,uuid,integer,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

-- The controlled caller must authenticate, lock_contract_document_context, and
-- validate the resulting authority at a fresh post-wait time before inserting.
-- Root/head identities may be expired; expiration is precisely a reason to renew.
CREATE FUNCTION private.lock_acquisition_renewal_authority(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid,p_policy uuid)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path='' AS $$
DECLARE reviews jsonb; originals jsonb; bound jsonb; ids uuid[]; policies uuid[]; sessions uuid[];
 artifact public.acquisition_evidence_artifacts%ROWTYPE; verification public.acquisition_evidence_verifications%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:'||p_contract::text,0));
 PERFORM 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Current renewal contract version required' USING ERRCODE='55000'; END IF;
 reviews:=private.acquisition_renewal_review_set(p_workspace,p_contract,p_version,p_root,clock_timestamp());
 IF reviews IS NULL THEN RAISE EXCEPTION 'Complete unsuperseded renewal support required' USING ERRCODE='55000'; END IF;
 SELECT array_agg(DISTINCT (value->>'review_id')::uuid) INTO ids FROM jsonb_array_elements(reviews);
 SELECT coalesce(jsonb_agg(source),'[]') INTO originals FROM public.acquisition_contract_reviews r
  CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.deadline_sources,'[]')||coalesce(r.execution_sources,'[]')||
   coalesce(r.title_sources,'[]')||coalesce(r.disposition_sources,'[]')) source
  WHERE r.workspace_id=p_workspace AND r.contract_id=p_contract AND r.contract_version=p_version AND r.id=ANY(ids);
 IF jsonb_array_length(originals)=0 THEN RAISE EXCEPTION 'Original renewal evidence required' USING ERRCODE='55000'; END IF;
 -- Match existing writers: canonical contract, sorted artifact/byte pairs, then
 -- evidence authority and review authority. Never lock a dependency piecemeal
 -- after a downstream policy has already been locked.
 FOR bound IN SELECT jsonb_build_object('id',id) FROM (SELECT DISTINCT value->>'artifact_id' AS id FROM jsonb_array_elements(originals)) source_ids ORDER BY id LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||(bound->>'id'),0));
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND id=(bound->>'id')::uuid;
  IF NOT FOUND THEN RAISE EXCEPTION 'Original renewal evidence unavailable' USING ERRCODE='55000'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
 END LOOP;
 FOR artifact IN SELECT a.* FROM public.acquisition_evidence_artifacts a WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract
  AND a.id IN (SELECT (value->>'artifact_id')::uuid FROM jsonb_array_elements(originals)) ORDER BY a.id LOOP
  SELECT * INTO verification FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=artifact.id ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'Current renewal observation required' USING ERRCODE='55000'; END IF;
  PERFORM 1 FROM private.acquisition_evidence_policies rp
   JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=rp.workspace_id AND k.id=verification.key_id
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=verification.actor_id
   JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=verification.session_id
   WHERE rp.workspace_id=p_workspace AND rp.id=artifact.retention_policy_id FOR SHARE OF rp,k,ks,m,profile,sess;
  IF NOT FOUND THEN RAISE EXCEPTION 'Complete renewal evidence authority required' USING ERRCODE='55000'; END IF;
 END LOOP;
 SELECT array_append(array_agg(DISTINCT policy_id),p_policy),array_agg(DISTINCT session_id) INTO policies,sessions
  FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND id=ANY(ids);
 PERFORM 1 FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND id=ANY(policies) ORDER BY id FOR SHARE;
 PERFORM 1 FROM private.acquisition_disposition_policy_scopes WHERE workspace_id=p_workspace AND policy_id=ANY(policies) ORDER BY policy_id FOR SHARE;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
  JOIN auth.sessions sess ON sess.user_id=m.user_id WHERE m.workspace_id=p_workspace AND sess.id=ANY(sessions)
  ORDER BY m.user_id,sess.id FOR SHARE OF m,profile,sess;
 IF reviews IS DISTINCT FROM private.acquisition_renewal_review_set(p_workspace,p_contract,p_version,p_root,clock_timestamp()) THEN
  RAISE EXCEPTION 'Renewal support changed while waiting' USING ERRCODE='55000'; END IF;
 -- Returning this set does not assert source/policy freshness, active acquisition,
 -- effective supporting reviews, proposed expiry, actor permission or approval.
 RETURN reviews;
END $$;
REVOKE ALL ON FUNCTION private.lock_acquisition_renewal_authority(uuid,uuid,integer,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
