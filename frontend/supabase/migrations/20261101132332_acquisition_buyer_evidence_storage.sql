-- Buyer evidence belongs to an exact canonical buyer revision, never a fake
-- campaign or contract. Registration, upload and verification remain unavailable
-- until their dedicated authenticated workflows are implemented and reviewed.
-- Compensation: pause acquisition/revoke later buyer evidence entrypoints;
-- preserve ownership, retention, immutable evidence and audit history.
BEGIN;
ALTER TABLE private.acquisition_evidence_policies
 DROP CONSTRAINT acquisition_evidence_policies_purpose_check,
 ADD CONSTRAINT acquisition_evidence_policies_purpose_check CHECK(purpose IN (
  'mail_content','mail_destination','purchase_contract','title_report','assignment_agreement',
  'seller_disclosure','assignee_disclosure','closing_statement','supporting_document',
  'buyer_identity','buyer_funds','buyer_closing_history'));

ALTER TABLE public.acquisition_evidence_artifacts
 ADD COLUMN buyer_id uuid,
 ADD COLUMN buyer_revision integer,
 DROP CONSTRAINT acquisition_evidence_target,
 ADD CONSTRAINT acquisition_evidence_target CHECK(
  (buyer_id IS NULL AND buyer_revision IS NULL AND campaign_id IS NOT NULL
   AND contract_id IS NULL AND contract_version IS NULL AND purpose IN ('mail_content','mail_destination')) OR
  (buyer_id IS NULL AND buyer_revision IS NULL AND campaign_id IS NULL
   AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0
   AND purpose IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document')) OR
  (buyer_id IS NOT NULL AND buyer_revision IS NOT NULL AND buyer_revision>0 AND campaign_id IS NULL
   AND contract_id IS NULL AND contract_version IS NULL AND purpose IN ('buyer_identity','buyer_funds','buyer_closing_history'))),
 ADD CONSTRAINT acquisition_evidence_buyer_revision FOREIGN KEY(workspace_id,buyer_id,buyer_revision)
  REFERENCES private.acquisition_buyer_versions(workspace_id,buyer_id,revision),
 ADD CONSTRAINT acquisition_evidence_buyer_identity UNIQUE(workspace_id,buyer_id,buyer_revision,id),
 ADD CONSTRAINT acquisition_evidence_buyer_purpose UNIQUE(workspace_id,buyer_id,buyer_revision,id,purpose);
CREATE INDEX acquisition_evidence_buyer ON public.acquisition_evidence_artifacts(workspace_id,buyer_id,buyer_revision,id)
 WHERE buyer_id IS NOT NULL;

ALTER TABLE public.acquisition_evidence_revocations
 ADD COLUMN buyer_id uuid,
 ADD COLUMN buyer_revision integer,
 DROP CONSTRAINT acquisition_revocation_target,
 ADD CONSTRAINT acquisition_revocation_target CHECK(
  (buyer_id IS NULL AND buyer_revision IS NULL AND campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL) OR
  (buyer_id IS NULL AND buyer_revision IS NULL AND campaign_id IS NULL AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0) OR
  (buyer_id IS NOT NULL AND buyer_revision IS NOT NULL AND buyer_revision>0 AND campaign_id IS NULL AND contract_id IS NULL AND contract_version IS NULL)),
 ADD CONSTRAINT acquisition_revocation_buyer FOREIGN KEY(workspace_id,buyer_id,buyer_revision,artifact_id)
  REFERENCES public.acquisition_evidence_artifacts(workspace_id,buyer_id,buyer_revision,id);

-- Existing contract/mail metadata stays readable under its current policies.
-- Buyer financial/identity metadata never inherits the operator read grant.
CREATE POLICY acquisition_buyer_evidence_boundary ON public.acquisition_evidence_artifacts
 AS RESTRICTIVE FOR ALL TO authenticated
 USING(buyer_id IS NULL OR (auth.jwt()->>'aal'='aal2' AND private.acquisition_role(workspace_id) IN ('owner','admin')))
 WITH CHECK(buyer_id IS NULL OR (auth.jwt()->>'aal'='aal2' AND private.acquisition_role(workspace_id) IN ('owner','admin')));
CREATE POLICY acquisition_buyer_evidence_boundary ON public.acquisition_evidence_revocations
 AS RESTRICTIVE FOR ALL TO authenticated
 USING(buyer_id IS NULL OR (auth.jwt()->>'aal'='aal2' AND private.acquisition_role(workspace_id) IN ('owner','admin')))
 WITH CHECK(buyer_id IS NULL OR (auth.jwt()->>'aal'='aal2' AND private.acquisition_role(workspace_id) IN ('owner','admin')));

-- No buyer retention policy, upload slot, scanner scope or approval is seeded.
-- Existing private Storage policy helper must deny this new ownership branch,
-- including downloads, until the dedicated buyer evidence path is implemented.
CREATE OR REPLACE FUNCTION private.acquisition_evidence_object_access(p_name text, p_upload boolean)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; evidence_role text; stamped timestamptz:=clock_timestamp();
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR p_upload IS NULL OR p_name IS NULL OR p_name !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{64}$' THEN RETURN false; END IF;
 -- Validate path before UUID casting; use the primary key then exact key equality.
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts a
 WHERE a.id=split_part(p_name,'/',2)::uuid
  AND p_name=a.workspace_id::text||'/'||a.id::text||'/'||a.expected_sha256;
 IF NOT FOUND OR artifact.created_at>stamped OR artifact.retain_until<=stamped THEN RETURN false; END IF;
 IF artifact.buyer_id IS NOT NULL THEN RETURN false; END IF;
 evidence_role:=private.acquisition_role(artifact.workspace_id);
 IF coalesce(evidence_role,'') NOT IN ('owner','admin','operator')
  OR (evidence_role='operator' AND artifact.created_by IS DISTINCT FROM auth.uid()) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM auth.sessions s WHERE s.id::text=auth.jwt()->>'session_id'
  AND s.user_id=auth.uid() AND (s.not_after IS NULL OR s.not_after>stamped)) THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations r
  WHERE r.workspace_id=artifact.workspace_id AND r.artifact_id=artifact.id) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_evidence_policies p
  WHERE p.id=artifact.retention_policy_id AND p.workspace_id=artifact.workspace_id AND p.purpose=artifact.purpose
   AND p.revoked_at IS NULL AND p.valid_from<=stamped AND p.valid_until>stamped) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM storage.buckets b WHERE b.id='acquisition-evidence' AND b.name=b.id
  AND b.public IS FALSE AND b.file_size_limit=10485760 AND b.type='STANDARD' AND b.versioning_status='DISABLED'
  AND b.lifecycle_configuration IS NULL AND b.allowed_mime_types=ARRAY['application/pdf','image/png','image/jpeg','text/plain']) THEN RETURN false; END IF;
 IF p_upload THEN
  RETURN artifact.created_by=auth.uid() AND storage.allow_only_operation('object.upload')
   AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
   AND (
    (artifact.campaign_id IS NOT NULL AND artifact.contract_id IS NULL AND artifact.contract_version IS NULL
     AND EXISTS(SELECT 1 FROM public.ad_campaigns c WHERE c.workspace_id=artifact.workspace_id
      AND c.id=artifact.campaign_id AND c.acquisition_channel='direct_mail' AND c.status='draft'))
    OR
    (artifact.campaign_id IS NULL AND artifact.contract_id IS NOT NULL AND artifact.contract_version IS NOT NULL
     AND EXISTS(SELECT 1 FROM public.deals d JOIN public.acquisition_contract_versions v
       ON v.workspace_id=d.workspace_id AND v.deal_id=d.id AND v.version=d.acquisition_version
      WHERE d.id=artifact.contract_id AND d.workspace_id=artifact.workspace_id
       AND d.acquisition_version=artifact.contract_version AND d.acquisition_status IN ('draft','pending_signature','title_review') AND v.status='draft')
     AND EXISTS(SELECT 1 FROM private.acquisition_evidence_upload_slots slot
      WHERE slot.workspace_id=artifact.workspace_id AND slot.actor_id=auth.uid()
       AND slot.campaign_id IS NULL AND slot.contract_id=artifact.contract_id
       AND slot.contract_version=artifact.contract_version AND slot.artifact_id=artifact.id
       AND slot.started_at<=stamped AND slot.expires_at>stamped))
   );
 END IF;
 RETURN storage.allow_any_operation(ARRAY['object.get_authenticated','object.get_authenticated_info']);
END $function$;

COMMIT;
