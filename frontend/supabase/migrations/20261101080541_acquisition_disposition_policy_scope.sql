-- Preserve existing policy row shapes and retained title-policy snapshots.
-- No policy is provisioned. This private predicate is not disposition authority.
-- Compensation: revoke a scope; retain review history and policy snapshots.
BEGIN;
CREATE TABLE private.acquisition_disposition_policy_scopes (
 policy_id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 reviewer_id uuid NOT NULL,
 kind text GENERATED ALWAYS AS ('disposition_findings'::text) STORED,
 purpose text GENERATED ALWAYS AS ('purchase_contract'::text) STORED,
 exit_type text NOT NULL CHECK(exit_type IN ('principal_acquisition','wholesale_assignment')),
 legal_source_id uuid,
 reviewed_by uuid NOT NULL REFERENCES public.profiles(id),
 approval_ref uuid NOT NULL,
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)),
 valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 revoked_at timestamptz CHECK(isfinite(revoked_at)),
 CHECK(valid_from<valid_until),
 CHECK((exit_type='principal_acquisition' AND legal_source_id IS NULL)
  OR (exit_type='wholesale_assignment' AND legal_source_id IS NOT NULL)),
 FOREIGN KEY(workspace_id,policy_id,kind,purpose,reviewer_id)
  REFERENCES private.acquisition_contract_review_policies(workspace_id,id,kind,purpose,reviewer_id),
 FOREIGN KEY(workspace_id,legal_source_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,id)
);
ALTER TABLE private.acquisition_disposition_policy_scopes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_disposition_policy_scopes FROM PUBLIC,anon,authenticated,service_role;
CREATE INDEX acquisition_disposition_policy_legal_source
 ON private.acquisition_disposition_policy_scopes(workspace_id,legal_source_id) WHERE legal_source_id IS NOT NULL;

ALTER TABLE public.acquisition_contract_reviews ADD COLUMN disposition_policy_snapshot jsonb,
 ADD CONSTRAINT acquisition_disposition_policy_snapshot_shape CHECK(disposition_policy_snapshot IS NULL
  OR (kind='disposition_findings' AND status IN ('approved','requires_resolution')
   AND jsonb_typeof(disposition_policy_snapshot)='object'
   AND disposition_policy_snapshot ?& ARRAY['reviewer','scope']
   AND jsonb_typeof(disposition_policy_snapshot->'reviewer')='object'
   AND jsonb_typeof(disposition_policy_snapshot->'scope')='object'));

-- The writer must lock these rows, retain both exact snapshots, bind verified
-- legal-source citations, and recheck this predicate after all authority waits.
-- This checks policy only: it does not authorize a reviewer/session, evidence,
-- contract, title decision, transition, marketing, assignment, or closing.
CREATE FUNCTION private.disposition_policy_current(p_workspace uuid,p_policy uuid,p_actor uuid,
 p_exit text,p_at timestamptz,p_snapshot jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT p_at IS NOT NULL AND isfinite(p_at) AND EXISTS(
  SELECT 1 FROM private.acquisition_contract_review_policies p
  JOIN private.acquisition_disposition_policy_scopes s ON s.policy_id=p.id
   AND s.workspace_id=p.workspace_id AND s.reviewer_id=p.reviewer_id
  WHERE p.id=p_policy AND p.workspace_id=p_workspace AND p.reviewer_id=p_actor
   AND p.kind='disposition_findings' AND p.purpose='purchase_contract' AND s.exit_type=p_exit
   AND p.revoked_at IS NULL AND s.revoked_at IS NULL
   AND p.valid_from<=p_at AND p_at<p.valid_until AND s.valid_from<=p_at AND p_at<s.valid_until
   AND p_snapshot=jsonb_build_object('reviewer',to_jsonb(p),'scope',to_jsonb(s))
 )
$$;
REVOKE ALL ON FUNCTION private.disposition_policy_current(uuid,uuid,uuid,text,timestamptz,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
