-- Bind the future disposition handoff to exact approved original decisions.
-- This extends the existing immutable lifecycle ledger, not a second CRM.
-- The existing writer and canonical deal guard still reject disposition_review;
-- activation requires the separately verified current-authority writer/read path.
-- Compensation: leave handoff unavailable or pause acquisition; preserve originals.
BEGIN;
ALTER TABLE public.acquisition_contract_transitions
 ADD CONSTRAINT acquisition_disposition_execution_identity
 UNIQUE(workspace_id,contract_id,contract_version,id,recorded_status,execution_review_id),
 ADD COLUMN disposition_review_id uuid,
 ADD COLUMN disposition_plan_id uuid,
 ADD COLUMN disposition_exit_type text,
 ADD COLUMN disposition_execution_id uuid,
 ADD COLUMN disposition_title_entry_id uuid,
 ADD COLUMN disposition_title_review_id uuid,
 ADD COLUMN disposition_review_kind text GENERATED ALWAYS AS (CASE WHEN disposition_review_id IS NOT NULL THEN 'disposition_findings'::text END) STORED,
 ADD COLUMN disposition_review_status text GENERATED ALWAYS AS (CASE WHEN disposition_review_id IS NOT NULL THEN 'approved'::text END) STORED,
 ADD COLUMN disposition_title_status text GENERATED ALWAYS AS (CASE WHEN disposition_review_id IS NOT NULL THEN 'approved'::text END) STORED,
 ADD COLUMN disposition_execution_status text GENERATED ALWAYS AS (CASE WHEN disposition_review_id IS NOT NULL THEN 'executed'::text END) STORED,
 ADD CONSTRAINT acquisition_transition_disposition_original FOREIGN KEY
 (workspace_id,contract_id,contract_version,disposition_review_kind,disposition_review_id,disposition_review_status,
  disposition_plan_id,disposition_exit_type,disposition_execution_id,disposition_title_entry_id,disposition_title_review_id,disposition_title_status)
 REFERENCES public.acquisition_contract_reviews
 (workspace_id,contract_id,contract_version,kind,id,status,disposition_plan_id,disposition_exit_type,disposition_execution_id,
  disposition_title_entry_id,disposition_title_review_id,disposition_title_status),
 ADD CONSTRAINT acquisition_transition_disposition_execution FOREIGN KEY
 (workspace_id,contract_id,contract_version,disposition_execution_id,disposition_execution_status,execution_review_id)
 REFERENCES public.acquisition_contract_transitions(workspace_id,contract_id,contract_version,id,recorded_status,execution_review_id),
 ADD CONSTRAINT acquisition_transition_disposition_shape CHECK(
  (recorded_status<>'disposition_review' AND disposition_review_id IS NULL AND disposition_plan_id IS NULL
   AND disposition_exit_type IS NULL AND disposition_execution_id IS NULL AND disposition_title_entry_id IS NULL AND disposition_title_review_id IS NULL)
  OR (recorded_status='disposition_review' AND disposition_review_id IS NOT NULL AND disposition_plan_id IS NOT NULL
   AND disposition_exit_type IS NOT NULL AND disposition_exit_type IN ('principal_acquisition','wholesale_assignment')
   AND disposition_execution_id IS NOT NULL AND disposition_title_entry_id IS NOT NULL AND disposition_title_review_id IS NOT NULL)),
 DROP CONSTRAINT acquisition_transition_supported_edge,
 ADD CONSTRAINT acquisition_transition_supported_edge CHECK(
  (previous_status='draft' AND recorded_status='pending_signature' AND sequence=1
   AND signature_review_id IS NOT NULL AND execution_review_id IS NULL AND execution_review_kind IS NULL)
  OR (previous_status='pending_signature' AND recorded_status='executed' AND sequence=2
   AND signature_review_id IS NULL AND execution_review_id IS NOT NULL AND execution_review_kind='executed_contract' AND execution_review_kind IS NOT NULL)
  OR (previous_status='executed' AND recorded_status='title_review' AND sequence=3
   AND signature_review_id IS NULL AND execution_review_id IS NOT NULL AND execution_review_kind='executed_contract' AND execution_review_kind IS NOT NULL)
  OR (previous_status='title_review' AND recorded_status='disposition_review' AND sequence=4
   AND signature_review_id IS NULL AND execution_review_id IS NOT NULL AND execution_review_kind='executed_contract' AND execution_review_kind IS NOT NULL));
-- Existing role/MFA/session RLS, SELECT-only grants, immutable trigger and
-- exact-request/sequence indexes are unchanged. No policy is provisioned.
COMMIT;
