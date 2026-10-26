-- Safe operational projection; no raw seller payloads, tokens or recovery writes.
BEGIN;
CREATE INDEX acquisition_inbox_workspace_id ON public.webhook_jobs(workspace_id,id) WHERE workspace_id IS NOT NULL;
CREATE FUNCTION private.acquisition_inquiry_health(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE active boolean; summary jsonb; item record; blockers text[]; guidance text;
 items jsonb:='[]'::jsonb; more boolean:=false;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace inquiry review required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Invalid inquiry page size' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 SELECT jsonb_build_object(
  'received',count(*),'completed',count(*) FILTER(WHERE j.state='completed'),
  'awaiting_worker',count(*) FILTER(WHERE j.state='ready'),
  'retrying',count(*) FILTER(WHERE j.state='retry'),
  'requires_review',count(*) FILTER(WHERE j.state='review'),
  'leased',count(*) FILTER(WHERE j.state='leased' AND j.lease_expires_at>statement_timestamp()),
  'expired_leases',count(*) FILTER(WHERE j.state='leased' AND j.lease_expires_at<=statement_timestamp()),
  'disabled_integration_pending',count(*) FILTER(WHERE j.state<>'completed' AND NOT i.enabled)) INTO summary
 FROM public.webhook_jobs w JOIN private.acquisition_inbox_processing j ON j.receipt_id=w.id
 JOIN private.acquisition_integrations i ON i.id=w.acquisition_integration_id WHERE w.workspace_id=p_workspace;
 FOR item IN SELECT w.id,w.created_at,w.acquisition_expires_at,w.acquisition_purged_at,i.id AS integration_id,i.provider,i.enabled,
   j.state,j.attempts,j.reason_code,j.next_attempt_at,j.lease_expires_at,j.updated_at
  FROM public.webhook_jobs w JOIN private.acquisition_inbox_processing j ON j.receipt_id=w.id
  JOIN private.acquisition_integrations i ON i.id=w.acquisition_integration_id
  WHERE w.workspace_id=p_workspace AND j.state<>'completed' AND (p_after IS NULL OR w.id>p_after)
  ORDER BY w.id LIMIT p_limit+1 LOOP
  IF jsonb_array_length(items)=p_limit THEN more:=true; EXIT; END IF;
  blockers:=ARRAY[]::text[];
  IF active IS DISTINCT FROM true THEN blockers:=array_append(blockers,'ACQUISITION_ACTIVATION_DISABLED'); END IF;
  IF NOT item.enabled THEN blockers:=array_append(blockers,'INTEGRATION_DISABLED'); END IF;
  IF item.acquisition_purged_at IS NOT NULL OR item.acquisition_expires_at<=statement_timestamp() THEN
   blockers:=array_append(blockers,'PAYLOAD_EXPIRED'); END IF;
  IF item.state='review' THEN blockers:=array_append(blockers,coalesce(item.reason_code,'REVIEW_REQUIRED')); END IF;
  IF item.state='leased' AND item.lease_expires_at<=statement_timestamp() THEN blockers:=array_append(blockers,'WORKER_LEASE_EXPIRED'); END IF;
  guidance:=CASE
   WHEN 'PAYLOAD_EXPIRED'=ANY(blockers) THEN 'Review retained evidence. Expired payloads cannot be replayed; any new seller contact requires separate eligibility.'
   WHEN item.reason_code='CREDENTIALS_INVALID' THEN 'Have an authorized integration administrator replace the expired or invalid Page credential and verify access before requesting recovery.'
   WHEN item.reason_code='PERMISSION_DENIED' THEN 'Verify app permissions and Page lead access with the integration administrator before requesting recovery.'
   WHEN item.reason_code='IDENTITY_CONFLICT' THEN 'Review Page, form and lead identity evidence. Do not merge unrelated properties or overwrite source evidence.'
   WHEN item.reason_code='RETRY_EXHAUSTED' THEN 'Review failed attempts and correct the cause before approving a new bounded recovery attempt.'
   WHEN item.reason_code IN ('INVALID_PROVIDER_DATA','UNSUPPORTED_EVENT') THEN 'Review the provider schema and preserved evidence before changing the processor or approving recovery.'
   WHEN NOT item.enabled OR active IS DISTINCT FROM true THEN 'Integration or acquisition activation is disabled. Follow the release approval process; this queue cannot enable it.'
   WHEN item.state='retry' THEN 'The worker may retry after the displayed time, subject to current gates and its attempt limit.'
   WHEN item.state='leased' AND item.lease_expires_at<=statement_timestamp() THEN 'Check worker health. An enabled worker can reclaim an expired lease within the attempt budget.'
   WHEN item.state='leased' THEN 'Processing lease is active. Wait for its outcome; do not manually replay the event.'
   ELSE 'Awaiting an enabled worker. Check worker runtime and configuration if the inquiry remains queued.' END;
  items:=items||jsonb_build_array(jsonb_build_object('receipt_id',item.id,'integration_id',item.integration_id,
   'provider',item.provider,'received_at',item.created_at,'state',item.state,'attempts',item.attempts,
   'reason_code',item.reason_code,'blockers',to_jsonb(blockers),'next_attempt_at',item.next_attempt_at,
   'lease_expires_at',item.lease_expires_at,'updated_at',item.updated_at,'guidance',guidance,
   'recovery_authorized',false));
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'summary',summary,'items',items,
  'next_after',CASE WHEN more THEN items->-1->>'receipt_id' ELSE NULL END,'ordering','receipt_id',
  'checked_at',statement_timestamp(),'worker_runtime_verified',false,'recovery_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_inquiry_health(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_inquiry_health(p_workspace,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION private.acquisition_inquiry_health(uuid,uuid,integer),public.acquisition_inquiry_health(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inquiry_health(uuid,uuid,integer),public.acquisition_inquiry_health(uuid,uuid,integer) TO authenticated;
COMMIT;
