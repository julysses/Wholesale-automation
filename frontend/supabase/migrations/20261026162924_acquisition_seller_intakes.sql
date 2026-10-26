-- Channel-neutral intake relation over canonical CRM leads and immutable receipts.
BEGIN;
ALTER TABLE public.workspace_leads ALTER COLUMN bound_by DROP NOT NULL,
 ADD COLUMN binding_integration_id uuid,
 ADD CONSTRAINT workspace_lead_binding_origin CHECK((bound_by IS NOT NULL AND binding_integration_id IS NULL) OR (bound_by IS NULL AND binding_integration_id IS NOT NULL)),
 ADD CONSTRAINT workspace_lead_binding_integration FOREIGN KEY(binding_integration_id,workspace_id) REFERENCES private.acquisition_integrations(id,workspace_id);
ALTER TABLE public.webhook_jobs ADD CONSTRAINT acquisition_receipt_workspace_unique UNIQUE(id,workspace_id);
CREATE TABLE public.seller_intakes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 lead_id uuid NOT NULL,
 receipt_id uuid NOT NULL UNIQUE,
 source_type text NOT NULL CHECK(source_type='facebook_native_form'),
 intake_version text NOT NULL CHECK(intake_version='seller-intake-v1'),
 classification text NOT NULL CHECK(classification IN ('incomplete','unqualified','requires_human_review')),
 prepared_answers jsonb NOT NULL CHECK(jsonb_typeof(prepared_answers)='object'),
 preparation_hash text NOT NULL,
 normalization_notes text[] NOT NULL DEFAULT ARRAY[]::text[],
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 FOREIGN KEY(receipt_id,workspace_id) REFERENCES public.webhook_jobs(id,workspace_id)
);
CREATE INDEX seller_intakes_workspace_created ON public.seller_intakes(workspace_id,created_at,id);
ALTER TABLE public.seller_intakes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.seller_intakes FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.seller_intakes TO authenticated;
CREATE POLICY seller_intakes_workspace_read ON public.seller_intakes FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER seller_intakes_immutable BEFORE UPDATE OR DELETE ON public.seller_intakes
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
ALTER TABLE private.acquisition_inbox_processing DROP CONSTRAINT acquisition_inbox_processing_state_check;
ALTER TABLE private.acquisition_inbox_processing ADD CONSTRAINT acquisition_inbox_processing_state_check
 CHECK(state IN ('ready','leased','retry','review','completed'));

-- These inquiries must not enter legacy unattended retention cleanup. A reviewed
-- acquisition retention workflow will manage CRM/intake evidence separately.
CREATE FUNCTION private.protect_acquisition_intake_retention() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF NEW.source='facebook_acquisition' THEN
  NEW.retention_deletable:=false; NEW.retention_action:='keep';
  NEW.retention_rule:='acquisition_intake_review'; NEW.retention_reason:='Acquisition intake retention review required';
  NEW.retention_due_at:=NULL;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_intake_retention() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER zz_acquisition_intake_retention BEFORE INSERT OR UPDATE ON public.leads
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_intake_retention();

CREATE FUNCTION private.complete_facebook_acquisition_intake(p_receipt uuid,p_lease uuid,p_prepared jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE receipt public.webhook_jobs%ROWTYPE; integration private.acquisition_integrations%ROWTYPE;
 job private.acquisition_inbox_processing%ROWTYPE; saved public.seller_intakes%ROWTYPE;
 active boolean; fingerprint text; answers jsonb; lead uuid; amount numeric;
 phone text; email text; notes text[]:=ARRAY[]::text[];
BEGIN
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=p_receipt AND workspace_id IS NOT NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Receipt unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO integration FROM private.acquisition_integrations WHERE id=receipt.acquisition_integration_id FOR SHARE;
 IF NOT FOUND OR NOT integration.enabled OR integration.provider<>'facebook' OR receipt.acquisition_event_type<>'leadgen' THEN
  RAISE EXCEPTION 'Facebook integration unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=receipt.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=p_receipt FOR UPDATE;
 SELECT * INTO job FROM private.acquisition_inbox_processing WHERE receipt_id=p_receipt FOR UPDATE;
 IF NOT FOUND OR p_lease IS NULL OR job.lease_token IS DISTINCT FROM p_lease THEN
  RAISE EXCEPTION 'Processing lease superseded' USING ERRCODE='40001'; END IF;
 IF p_prepared IS NULL OR jsonb_typeof(p_prepared)<>'object' OR octet_length(p_prepared::text)>1048576
  OR p_prepared->>'version' IS DISTINCT FROM 'seller-intake-v1'
  OR p_prepared->>'source_type' IS DISTINCT FROM 'facebook_native_form'
  OR p_prepared->>'external_lead_id' IS DISTINCT FROM receipt.external_event_id
  OR (receipt.acquisition_purged_at IS NULL AND receipt.payload->>'leadgen_id' IS DISTINCT FROM receipt.external_event_id)
  OR (receipt.payload->>'form_id' IS NOT NULL AND receipt.payload->>'form_id' IS DISTINCT FROM p_prepared->>'provider_form_id')
  OR coalesce(p_prepared->>'classification','') NOT IN ('incomplete','unqualified','requires_human_review')
  OR jsonb_typeof(p_prepared->'answers') IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_prepared->'field_evidence') IS DISTINCT FROM 'array'
  OR p_prepared->'property_verified' IS DISTINCT FROM 'false'::jsonb
  OR p_prepared->'ownership_verified' IS DISTINCT FROM 'false'::jsonb
  OR p_prepared->'contact_permission_granted' IS DISTINCT FROM 'false'::jsonb
  OR p_prepared->'outreach_authorized' IS DISTINCT FROM 'false'::jsonb
  OR p_prepared->'binding_offer' IS DISTINCT FROM 'false'::jsonb THEN
  RAISE EXCEPTION 'Invalid prepared seller intake' USING ERRCODE='22023'; END IF;
 answers:=p_prepared->'answers';
 IF EXISTS(SELECT 1 FROM jsonb_each(answers) kv WHERE jsonb_typeof(kv.value)<>'string' OR length(kv.value#>>'{}')>10000) THEN
  RAISE EXCEPTION 'Invalid seller answers' USING ERRCODE='22023'; END IF;
 IF p_prepared->>'asking_price' IS NOT NULL THEN
  IF (p_prepared->>'asking_price')!~'^[0-9]{1,10}\.[0-9]{2}$' THEN RAISE EXCEPTION 'Invalid seller price' USING ERRCODE='22023'; END IF;
  amount:=(p_prepared->>'asking_price')::numeric;
  IF amount>1000000000 THEN RAISE EXCEPTION 'Invalid seller price' USING ERRCODE='22023'; END IF;
 END IF;
 fingerprint:=encode(sha256(convert_to(p_prepared::text,'UTF8')),'hex');
 SELECT * INTO saved FROM public.seller_intakes WHERE receipt_id=p_receipt;
 IF FOUND THEN
  IF job.state<>'completed' OR saved.preparation_hash<>fingerprint THEN RAISE EXCEPTION 'Completed intake conflicts' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('intake_id',saved.id,'lead_id',saved.lead_id,'workspace_id',saved.workspace_id,'classification',saved.classification,'duplicate',true);
 END IF;
 IF job.state<>'leased' OR job.lease_expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'Processing lease expired or unavailable' USING ERRCODE='40001'; END IF;
 IF receipt.acquisition_purged_at IS NOT NULL OR receipt.acquisition_expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION 'Receipt payload expired' USING ERRCODE='55000'; END IF;
 -- No telephone/address-only merge and no inferred canonical property match.
 IF nullif(trim(answers->>'phone'),'') IS NOT NULL THEN
  BEGIN phone:=private.normalize_acquisition_contact('phone',answers->>'phone');
  EXCEPTION WHEN SQLSTATE '22023' THEN notes:=array_append(notes,'PHONE_REVIEW_REQUIRED'); END;
 END IF;
 IF nullif(trim(answers->>'email'),'') IS NOT NULL THEN
  BEGIN email:=private.normalize_acquisition_contact('email',answers->>'email');
  EXCEPTION WHEN SQLSTATE '22023' THEN notes:=array_append(notes,'EMAIL_REVIEW_REQUIRED'); END;
 END IF;
 lead:=gen_random_uuid();
 INSERT INTO public.leads(id,property_address,city,state,zip_code,owner_first_name,owner_last_name,
  owner_phone_1,owner_email,source,inbound_channel,asking_price,status,sms_sequence_active,email_sequence_active,ai_calling_paused)
 VALUES(lead,coalesce(answers->>'property_address',''),coalesce(answers->>'city',''),nullif(answers->>'state',''),nullif(answers->>'zip_code',''),
  nullif(answers->>'first_name',''),nullif(answers->>'last_name',''),phone,
  email,'facebook_acquisition','facebook_lead_ad',amount,'new',false,false,true);
 INSERT INTO public.workspace_leads(workspace_id,lead_id,bound_by,binding_integration_id)
 VALUES(receipt.workspace_id,lead,NULL,integration.id);
 INSERT INTO public.seller_intakes(workspace_id,lead_id,receipt_id,source_type,intake_version,classification,prepared_answers,preparation_hash,normalization_notes)
 VALUES(receipt.workspace_id,lead,p_receipt,'facebook_native_form','seller-intake-v1',p_prepared->>'classification',p_prepared,fingerprint,notes) RETURNING * INTO saved;
 UPDATE private.acquisition_inbox_processing SET state='completed',lease_expires_at=NULL,updated_at=clock_timestamp() WHERE receipt_id=p_receipt;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('seller_intake',saved.id::text,'created','integration:'||integration.id,
  jsonb_build_object('lead_id',lead,'receipt_id',p_receipt,'classification',saved.classification,'preparation_hash',fingerprint,'attempt',job.attempts),receipt.workspace_id);
 RETURN jsonb_build_object('intake_id',saved.id,'lead_id',lead,'workspace_id',saved.workspace_id,'classification',saved.classification,'duplicate',false);
END $$;
CREATE FUNCTION public.complete_facebook_acquisition_intake(p_receipt uuid,p_lease uuid,p_prepared jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.complete_facebook_acquisition_intake(p_receipt,p_lease,p_prepared) $$;
REVOKE ALL ON FUNCTION private.complete_facebook_acquisition_intake(uuid,uuid,jsonb),public.complete_facebook_acquisition_intake(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.complete_facebook_acquisition_intake(uuid,uuid,jsonb),public.complete_facebook_acquisition_intake(uuid,uuid,jsonb) TO service_role;
COMMIT;
