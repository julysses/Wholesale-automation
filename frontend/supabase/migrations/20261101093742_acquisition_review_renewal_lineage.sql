-- Add immutable renewal lineage without enabling a renewal writer or API.
-- Compensation: keep renewal unavailable; retain original rows and forward-fix.
BEGIN;
ALTER TABLE public.acquisition_contract_reviews
 ADD COLUMN renewal_root_id uuid,
 ADD COLUMN renewal_previous_id uuid,
 ADD COLUMN renewal_stream text GENERATED ALWAYS AS (coalesce(deadline_term,'')) STORED NOT NULL,
 ADD COLUMN renewal_parent_status text GENERATED ALWAYS AS (CASE WHEN renewal_root_id IS NOT NULL THEN 'approved'::text END) STORED,
 ADD CONSTRAINT acquisition_renewal_identity UNIQUE(workspace_id,contract_id,contract_version,kind,renewal_stream,id,status),
 ADD CONSTRAINT acquisition_renewal_shape CHECK(
  (renewal_root_id IS NULL AND renewal_previous_id IS NULL)
  OR (renewal_root_id IS NOT NULL AND renewal_previous_id IS NOT NULL
   AND status='approved' AND kind IN ('deadline_resolution','executed_contract','title_findings','disposition_findings')
   AND id<>renewal_root_id AND id<>renewal_previous_id AND sequence>1)),
 ADD CONSTRAINT acquisition_renewal_root FOREIGN KEY
 (workspace_id,contract_id,contract_version,kind,renewal_stream,renewal_root_id,renewal_parent_status)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,renewal_stream,id,status),
 ADD CONSTRAINT acquisition_renewal_previous FOREIGN KEY
 (workspace_id,contract_id,contract_version,kind,renewal_stream,renewal_previous_id,renewal_parent_status)
 REFERENCES public.acquisition_contract_reviews(workspace_id,contract_id,contract_version,kind,renewal_stream,id,status);
CREATE UNIQUE INDEX acquisition_renewal_one_successor ON public.acquisition_contract_reviews(renewal_previous_id)
 WHERE renewal_previous_id IS NOT NULL;
CREATE INDEX acquisition_renewal_root_chain ON public.acquisition_contract_reviews(renewal_root_id,sequence DESC)
 WHERE renewal_root_id IS NOT NULL;

CREATE FUNCTION private.guard_acquisition_review_renewal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE root public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 latest uuid; stream_sequence integer;
BEGIN
 IF NEW.renewal_root_id IS NULL AND NEW.renewal_previous_id IS NULL THEN RETURN NEW; END IF;
 -- Match controlled writers: deal advisory lock before canonical row lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:'||NEW.contract_id::text,0));
 PERFORM 1 FROM public.deals WHERE workspace_id=NEW.workspace_id AND id=NEW.contract_id FOR UPDATE;
 SELECT * INTO root FROM public.acquisition_contract_reviews WHERE id=NEW.renewal_root_id;
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE id=NEW.renewal_previous_id;
 IF root.id IS NULL OR prior.id IS NULL OR root.renewal_root_id IS NOT NULL
  OR root.status<>'approved' OR prior.status<>'approved'
  OR coalesce(prior.renewal_root_id,prior.id)<>root.id
  OR prior.sequence<root.sequence OR NEW.sequence<=prior.sequence
  OR prior.created_at<root.created_at OR NEW.created_at<prior.created_at THEN
  RAISE EXCEPTION 'Original approved renewal lineage required' USING ERRCODE='23514'; END IF;
 SELECT id INTO latest FROM public.acquisition_contract_reviews
  WHERE workspace_id=NEW.workspace_id AND contract_id=NEW.contract_id AND contract_version=NEW.contract_version
   AND kind=NEW.kind AND deadline_term IS NOT DISTINCT FROM NEW.deadline_term ORDER BY sequence DESC LIMIT 1;
 SELECT max(sequence) INTO stream_sequence FROM public.acquisition_contract_reviews
  WHERE workspace_id=NEW.workspace_id AND contract_id=NEW.contract_id AND contract_version=NEW.contract_version AND kind=NEW.kind;
 IF latest IS DISTINCT FROM prior.id OR NEW.sequence IS DISTINCT FROM stream_sequence+1 THEN
  RAISE EXCEPTION 'Latest unsuperseded review and exact stream sequence required' USING ERRCODE='23514'; END IF;
 -- Findings bind original cited bytes and interpretations. Fresh verification,
 -- reviewer/session/policy and bounded expiry belong to the future human writer.
 IF ROW(NEW.artifact_id,coalesce(NEW.evidence_version,NEW.contract_version),NEW.purpose,NEW.sha256,NEW.execution_findings,NEW.deadline_resolution,
  NEW.title_findings,NEW.title_execution_transition_id,NEW.disposition_findings,NEW.disposition_plan_id,
  NEW.disposition_exit_type,NEW.disposition_execution_id,NEW.disposition_title_entry_id,NEW.disposition_title_review_id)
 IS DISTINCT FROM ROW(root.artifact_id,root.source_version,root.purpose,root.sha256,root.execution_findings,root.deadline_resolution,
  root.title_findings,root.title_execution_transition_id,root.disposition_findings,root.disposition_plan_id,
  root.disposition_exit_type,root.disposition_execution_id,root.disposition_title_entry_id,root.disposition_title_review_id) THEN
  RAISE EXCEPTION 'Renewal cannot replace original findings or contract interest' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.guard_acquisition_review_renewal() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_review_renewal_insert BEFORE INSERT ON public.acquisition_contract_reviews
 FOR EACH ROW EXECUTE FUNCTION private.guard_acquisition_review_renewal();
-- Existing RLS, SELECT-only grants, withdrawal shape and immutable trigger remain.
COMMIT;
