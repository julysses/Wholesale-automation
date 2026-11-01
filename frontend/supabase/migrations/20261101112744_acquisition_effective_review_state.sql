-- Connect existing current-state projections to exact effective renewal heads.
-- Preserve the meaning of an exact review ID: an older root is NOT current merely
-- because a descendant was renewed. Transition roots remain historical and their
-- separate effective-authority integration must explicitly resolve the head.
-- No tables, RLS, client grants, activation or lifecycle writers are changed.
BEGIN;
CREATE FUNCTION private.acquisition_review_effective_exact_current(p_review uuid,p_kind text,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT coalesce((SELECT r.status='approved'
  AND r.id=private.acquisition_review_lineage_head(r.workspace_id,r.contract_id,r.contract_version,coalesce(r.renewal_root_id,r.id),p_at)
  AND private.acquisition_effective_review_current(coalesce(r.renewal_root_id,r.id),p_kind,p_at)
 FROM public.acquisition_contract_reviews r WHERE r.id=p_review AND r.kind=p_kind
  AND p_kind IN ('deadline_resolution','executed_contract','title_findings','disposition_findings')),false)
$$;
REVOKE ALL ON FUNCTION private.acquisition_review_effective_exact_current(uuid,text,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.deadline_review_current(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_effective_exact_current(p_review,'deadline_resolution',p_at)
$$;
REVOKE ALL ON FUNCTION private.deadline_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.execution_review_current(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_effective_exact_current(p_review,'executed_contract',p_at)
$$;
REVOKE ALL ON FUNCTION private.execution_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.title_review_current(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_effective_exact_current(p_review,'title_findings',p_at)
$$;
REVOKE ALL ON FUNCTION private.title_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.disposition_review_current(p_review uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_effective_exact_current(p_review,'disposition_findings',p_at)
$$;
REVOKE ALL ON FUNCTION private.disposition_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
-- Compensation: pause acquisition and restore the prior exact predicates through
-- a forward migration if needed. Never delete renewals or rewrite original history.
COMMIT;
