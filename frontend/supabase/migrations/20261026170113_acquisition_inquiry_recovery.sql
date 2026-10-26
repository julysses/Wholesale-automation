-- Human-reviewed bounded recovery. Never enables integrations or performs calls.
BEGIN;
CREATE TABLE public.acquisition_inquiry_recoveries (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 receipt_id uuid NOT NULL,
 cycle integer NOT NULL CHECK(cycle BETWEEN 1 AND 3),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 expected_updated_at timestamptz NOT NULL,
 reason_code text NOT NULL,
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 evidence_ref text NOT NULL CHECK(length(trim(evidence_ref)) BETWEEN 1 AND 500),
 previous_attempts integer NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(receipt_id,cycle),
 FOREIGN KEY(receipt_id,workspace_id) REFERENCES public.webhook_jobs(id,workspace_id)
);
ALTER TABLE public.acquisition_inquiry_recoveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_inquiry_recoveries FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_inquiry_recoveries TO authenticated;
CREATE POLICY acquisition_recoveries_read ON public.acquisition_inquiry_recoveries FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_recoveries_immutable BEFORE UPDATE OR DELETE ON public.acquisition_inquiry_recoveries
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.recover_acquisition_inquiry(p_id uuid,p_workspace uuid,p_receipt uuid,p_expected_updated_at timestamptz,p_expected_reason text,p_note text,p_evidence_ref text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE receipt public.webhook_jobs%ROWTYPE; integration private.acquisition_integrations%ROWTYPE;
 job private.acquisition_inbox_processing%ROWTYPE; saved public.acquisition_inquiry_recoveries%ROWTYPE;
 active boolean; generation integer;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Workspace recovery administrator with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_expected_updated_at IS NULL OR p_expected_reason IS NULL
  OR p_expected_reason NOT IN ('CREDENTIALS_INVALID','PERMISSION_DENIED','RETRY_EXHAUSTED','INVALID_PROVIDER_DATA','IDENTITY_CONFLICT','UNSUPPORTED_EVENT')
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000
  OR p_evidence_ref IS NULL OR length(trim(p_evidence_ref)) NOT BETWEEN 1 AND 500 THEN
  RAISE EXCEPTION 'Documented recovery review required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=p_receipt AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inquiry unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO integration FROM private.acquisition_integrations WHERE id=receipt.acquisition_integration_id FOR SHARE;
 IF NOT integration.enabled THEN RAISE EXCEPTION 'Integration disabled' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 -- Hold authority through commit; revocation/suspension cannot race the reset.
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
  JOIN auth.sessions s ON s.user_id=p.id
  WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin')
   AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp())
  FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Recovery authority changed' USING ERRCODE='42501'; END IF;
 -- Stable request identity also serializes accidental UUID reuse across receipts.
 PERFORM pg_advisory_xact_lock(hashtextextended('inquiry-recovery:'||p_id,0));
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=p_receipt FOR UPDATE;
 SELECT * INTO job FROM private.acquisition_inbox_processing WHERE receipt_id=p_receipt FOR UPDATE;
 SELECT * INTO saved FROM public.acquisition_inquiry_recoveries WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.receipt_id,saved.actor_id,saved.expected_updated_at,saved.reason_code,saved.review_note,saved.evidence_ref)
   IS DISTINCT FROM ROW(p_workspace,p_receipt,auth.uid(),p_expected_updated_at,p_expected_reason,p_note,p_evidence_ref) THEN
   RAISE EXCEPTION 'Recovery request identity conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('recovery_id',saved.id,'receipt_id',saved.receipt_id,'cycle',saved.cycle,'duplicate',true,'outreach_authorized',false);
 END IF;
 IF job.state IS DISTINCT FROM 'review' OR job.updated_at IS DISTINCT FROM p_expected_updated_at OR job.reason_code IS DISTINCT FROM p_expected_reason THEN
  RAISE EXCEPTION 'Inquiry review state changed' USING ERRCODE='40001'; END IF;
 IF receipt.acquisition_purged_at IS NOT NULL OR receipt.acquisition_expires_at<=clock_timestamp() OR EXISTS(SELECT 1 FROM public.seller_intakes WHERE receipt_id=p_receipt) THEN
  RAISE EXCEPTION 'Inquiry cannot be replayed' USING ERRCODE='55000'; END IF;
 SELECT count(*)+1 INTO generation FROM public.acquisition_inquiry_recoveries WHERE receipt_id=p_receipt;
 IF generation>3 THEN RAISE EXCEPTION 'Reviewed recovery budget exhausted' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_inquiry_recoveries(id,workspace_id,receipt_id,cycle,actor_id,expected_updated_at,reason_code,review_note,evidence_ref,previous_attempts)
 VALUES(p_id,p_workspace,p_receipt,generation,auth.uid(),p_expected_updated_at,p_expected_reason,p_note,p_evidence_ref,job.attempts);
 UPDATE private.acquisition_inbox_processing SET state='ready',attempts=0,lease_token=NULL,lease_expires_at=NULL,
  next_attempt_at=clock_timestamp(),reason_code=NULL,requested_reason=NULL,settled_outcome=NULL,updated_at=clock_timestamp() WHERE receipt_id=p_receipt;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbox',p_receipt::text,'recovery_approved',auth.uid()::text,
  jsonb_build_object('recovery_id',p_id,'cycle',generation,'previous_attempts',job.attempts,'previous_reason',p_expected_reason),p_workspace);
 RETURN jsonb_build_object('recovery_id',p_id,'receipt_id',p_receipt,'cycle',generation,'duplicate',false,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.recover_acquisition_inquiry(p_id uuid,p_workspace uuid,p_receipt uuid,p_expected_updated_at timestamptz,p_expected_reason text,p_note text,p_evidence_ref text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.recover_acquisition_inquiry(p_id,p_workspace,p_receipt,p_expected_updated_at,p_expected_reason,p_note,p_evidence_ref) $$;
REVOKE ALL ON FUNCTION private.recover_acquisition_inquiry(uuid,uuid,uuid,timestamptz,text,text,text),public.recover_acquisition_inquiry(uuid,uuid,uuid,timestamptz,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.recover_acquisition_inquiry(uuid,uuid,uuid,timestamptz,text,text,text),public.recover_acquisition_inquiry(uuid,uuid,uuid,timestamptz,text,text,text) TO authenticated;
COMMIT;
