-- Read-only executed-status handoff in the existing lifecycle choice function.
-- No policies, approvals, signatures or transitions are created.
-- Compensation: disable acquisition; retain all existing history.
BEGIN;
CREATE OR REPLACE FUNCTION private.contract_transition_choice(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE review jsonb; deal public.deals%ROWTYPE; seq integer; held text; choice jsonb:=NULL; checked timestamptz;
BEGIN
 -- Reuse exact workspace/owner/admin/MFA/live-session and historical-version access.
 review:=private.signature_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO deal FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract;
 SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_transitions
  WHERE workspace_id=p_workspace AND contract_id=p_contract;
 checked:=clock_timestamp();
 IF deal.acquisition_version<>p_version THEN held:='version_changed';
 ELSIF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN held:='paused';
 ELSIF deal.acquisition_status='executed' AND seq=2 THEN held:='execution_recorded';
 ELSIF deal.acquisition_status='pending_signature' AND seq=1 THEN
  review:=private.execution_review_state(p_workspace,p_contract,p_version);
  checked:=clock_timestamp();
  IF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked
   OR NOT private.execution_review_current((review->>'review_id')::uuid,checked) THEN held:='execution_review_required';
  ELSE
   held:='ready_for_human_review';
   choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','pending_signature',
    'target_status','executed','execution_review_id',review->>'review_id','expires_at',review->>'expires_at');
  END IF;
 ELSIF deal.acquisition_status IS DISTINCT FROM 'draft' OR seq<>0 THEN held:='history_requires_review';
 ELSIF review->>'approval_current' IS DISTINCT FROM 'true' OR (review->>'expires_at')::timestamptz<=checked THEN held:='signature_review_required';
 ELSE
  held:='ready_for_human_review';
  choice:=jsonb_build_object('expected_version',p_version,'expected_sequence',seq,'expected_status','draft',
   'target_status','pending_signature','signature_review_id',review->>'review_id','expires_at',review->>'expires_at');
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'current_version',deal.acquisition_version,'current_status',deal.acquisition_status,'sequence',seq,
  'status',held,'candidate',choice,'checked_at',checked,'execution_authorized',false);
END $$;
COMMIT;
