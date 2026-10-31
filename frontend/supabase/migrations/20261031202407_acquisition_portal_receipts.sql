-- Portal receipts reuse the existing intake master; no public HTTP activation.
BEGIN;
ALTER TABLE public.lead_form_configs ADD CONSTRAINT portal_form_receipt_identity UNIQUE(id,workspace_id,campaign_id);
ALTER TABLE public.lead_form_submissions
 ADD COLUMN workspace_id uuid,
 ADD COLUMN acquisition_campaign_id uuid,
 ADD COLUMN acquisition_request_hash text,
 ADD CONSTRAINT portal_receipt_scope UNIQUE(id,workspace_id),
 ADD CONSTRAINT portal_receipt_lead_scope UNIQUE(id,workspace_id,lead_id),
 ADD CONSTRAINT portal_receipt_form_scope FOREIGN KEY(form_id,workspace_id,acquisition_campaign_id)
 REFERENCES public.lead_form_configs(id,workspace_id,campaign_id),
 ADD CONSTRAINT portal_receipt_shape CHECK(
 (workspace_id IS NULL AND acquisition_campaign_id IS NULL AND acquisition_request_hash IS NULL)
 OR (workspace_id IS NOT NULL AND acquisition_campaign_id IS NOT NULL AND form_id IS NOT NULL AND lead_id IS NOT NULL
 AND acquisition_request_hash IS NOT NULL AND acquisition_request_hash ~ '^[0-9a-f]{64}$'
 AND processing_status IS NOT NULL AND processing_status='processed' AND request_manifest IS NOT NULL AND jsonb_typeof(request_manifest)='object'
 AND ip_address IS NULL AND user_agent IS NULL));
CREATE INDEX portal_receipt_workspace ON public.lead_form_submissions(workspace_id,created_at,id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.lead_form_submissions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS acquisition_legacy_boundary ON public.lead_form_submissions;
CREATE POLICY portal_receipt_read ON public.lead_form_submissions AS RESTRICTIVE FOR SELECT TO authenticated
 USING((workspace_id IS NULL AND private.acquisition_legacy_access()) OR
 private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

ALTER TABLE public.workspace_leads ADD COLUMN binding_portal_receipt_id uuid,
 DROP CONSTRAINT workspace_lead_binding_origin,
 ADD CONSTRAINT workspace_lead_binding_origin CHECK(
 (bound_by IS NOT NULL AND binding_integration_id IS NULL AND binding_portal_receipt_id IS NULL) OR
 (bound_by IS NULL AND binding_integration_id IS NOT NULL AND binding_portal_receipt_id IS NULL) OR
 (bound_by IS NULL AND binding_integration_id IS NULL AND binding_portal_receipt_id IS NOT NULL)),
 ADD CONSTRAINT workspace_lead_portal_origin FOREIGN KEY(binding_portal_receipt_id,workspace_id,lead_id)
 REFERENCES public.lead_form_submissions(id,workspace_id,lead_id);
ALTER TABLE public.seller_intakes ADD COLUMN portal_receipt_id uuid UNIQUE,
 ADD CONSTRAINT seller_intake_portal_origin FOREIGN KEY(portal_receipt_id,workspace_id,lead_id)
 REFERENCES public.lead_form_submissions(id,workspace_id,lead_id);
ALTER TABLE public.acquisition_lead_sources ALTER COLUMN integration_id DROP NOT NULL,
 ADD COLUMN portal_receipt_id uuid UNIQUE,
 ADD COLUMN portal_campaign_id uuid,
 ADD CONSTRAINT acquisition_source_portal_origin FOREIGN KEY(portal_receipt_id,workspace_id,lead_id)
 REFERENCES public.lead_form_submissions(id,workspace_id,lead_id),
 ADD CONSTRAINT acquisition_source_portal_campaign FOREIGN KEY(portal_campaign_id,workspace_id)
 REFERENCES public.ad_campaigns(id,workspace_id);
ALTER TABLE public.seller_intakes DROP CONSTRAINT seller_intakes_origin, ADD CONSTRAINT seller_intakes_origin CHECK ((portal_receipt_id IS NULL AND ((source_type='facebook_native_form' AND receipt_id IS NOT NULL AND inbound_integration_id IS NULL AND inbound_call_id IS NULL
   AND inbound_event_id IS NULL AND inbound_request_id IS NULL AND inbound_revision IS NULL)
  OR (source_type='retell_inbound' AND receipt_id IS NULL AND inbound_integration_id IS NOT NULL AND inbound_call_id IS NOT NULL
   AND inbound_call_id ~ '^[A-Za-z0-9_-]{1,200}$' AND inbound_event_id IS NOT NULL AND inbound_request_id IS NOT NULL
   AND inbound_revision IS NOT NULL AND inbound_revision>0))) OR (source_type='online_offer_portal' AND portal_receipt_id IS NOT NULL AND receipt_id IS NULL AND inbound_integration_id IS NULL AND inbound_call_id IS NULL AND inbound_event_id IS NULL AND inbound_request_id IS NULL AND inbound_revision IS NULL));
ALTER TABLE public.acquisition_lead_sources DROP CONSTRAINT acquisition_source_origin, ADD CONSTRAINT acquisition_source_origin CHECK ((portal_receipt_id IS NULL AND portal_campaign_id IS NULL AND integration_id IS NOT NULL AND ((source_type='facebook_native_form' AND receipt_id IS NOT NULL AND inbound_event_id IS NULL AND inbound_revision IS NULL)
  OR (source_type='retell_inbound' AND receipt_id IS NULL AND inbound_event_id IS NOT NULL AND inbound_revision IS NOT NULL AND inbound_revision>0
   AND form_id IS NULL AND external_campaign_id IS NULL AND adset_id IS NULL AND ad_id IS NULL AND submitted_at_raw IS NULL AND utm_data IS NULL))) OR (source_type='online_offer_portal' AND portal_receipt_id IS NOT NULL AND portal_campaign_id IS NOT NULL AND integration_id IS NULL AND receipt_id IS NULL AND inbound_event_id IS NULL AND inbound_revision IS NULL AND external_campaign_id IS NULL AND adset_id IS NULL AND ad_id IS NULL AND submitted_at_raw IS NULL AND utm_data IS NULL));

-- Invoker trigger distinguishes guarded definer transactions from raw API writes.
CREATE OR REPLACE FUNCTION private.reject_acquisition_form_submission() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scope uuid;
BEGIN
 IF TG_OP='TRUNCATE' THEN RAISE EXCEPTION 'Receipt history cannot be truncated' USING ERRCODE='42501'; END IF;
 IF TG_OP IN ('UPDATE','DELETE') AND OLD.workspace_id IS NOT NULL THEN
  RAISE EXCEPTION 'Portal receipt is immutable' USING ERRCODE='42501'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF NEW.form_id IS NOT NULL THEN
  SELECT workspace_id INTO scope FROM public.lead_form_configs WHERE id=NEW.form_id FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Form parent unavailable' USING ERRCODE='23503'; END IF;
 END IF;
 IF scope IS NOT NULL OR NEW.workspace_id IS NOT NULL THEN
  IF current_user IN ('anon','authenticated','service_role') OR TG_OP<>'INSERT' OR scope IS DISTINCT FROM NEW.workspace_id THEN
   RAISE EXCEPTION 'Use acquisition submission workflow' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER reject_acquisition_form_submission ON public.lead_form_submissions;
CREATE TRIGGER reject_acquisition_form_submission BEFORE INSERT OR UPDATE OR DELETE ON public.lead_form_submissions
 FOR EACH ROW EXECUTE FUNCTION private.reject_acquisition_form_submission();
CREATE TRIGGER portal_receipt_no_truncate BEFORE TRUNCATE ON public.lead_form_submissions
 FOR EACH STATEMENT EXECUTE FUNCTION private.reject_acquisition_form_submission();
CREATE OR REPLACE FUNCTION private.record_acquisition_lead_source(p_intake uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; receipt public.webhook_jobs%ROWTYPE; evidence jsonb;
BEGIN
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source intake unavailable'; END IF;
 IF intake.source_type='online_offer_portal' THEN
  INSERT INTO public.acquisition_lead_sources(id,workspace_id,lead_id,source_type,preparation_hash,external_lead_id,portal_receipt_id,portal_campaign_id,form_id)
  SELECT intake.id,intake.workspace_id,intake.lead_id,intake.source_type,intake.preparation_hash,r.id::text,r.id,r.acquisition_campaign_id,r.form_id::text
  FROM public.lead_form_submissions r WHERE r.id=intake.portal_receipt_id AND r.workspace_id=intake.workspace_id AND r.lead_id=intake.lead_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Portal source receipt unavailable'; END IF;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_lead_source',intake.id::text,'source_recorded','online_offer_intake',
   jsonb_build_object('lead_id',intake.lead_id,'portal_receipt_id',intake.portal_receipt_id,'preparation_hash',intake.preparation_hash),intake.workspace_id);
  RETURN;
 END IF;
 IF intake.source_type='retell_inbound' THEN
  INSERT INTO public.acquisition_lead_sources(id,workspace_id,lead_id,receipt_id,integration_id,source_type,preparation_hash,external_lead_id,inbound_event_id,inbound_revision)
  VALUES(intake.id,intake.workspace_id,intake.lead_id,NULL,intake.inbound_integration_id,'retell_inbound',intake.preparation_hash,intake.inbound_call_id,intake.inbound_event_id,intake.inbound_revision);
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_lead_source',intake.id::text,'source_recorded','inbound_intake',
   jsonb_build_object('lead_id',intake.lead_id,'inbound_event_id',intake.inbound_event_id,'inbound_revision',intake.inbound_revision,'preparation_hash',intake.preparation_hash),intake.workspace_id);
  RETURN;
 END IF;
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=intake.receipt_id AND workspace_id=intake.workspace_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source receipt unavailable'; END IF;
 evidence:=intake.prepared_answers->'provider_evidence';
 INSERT INTO public.acquisition_lead_sources(id,workspace_id,lead_id,receipt_id,integration_id,source_type,preparation_hash,external_lead_id,
  form_id,external_campaign_id,adset_id,ad_id,submitted_at_raw,utm_data)
 VALUES(intake.id,intake.workspace_id,intake.lead_id,intake.receipt_id,receipt.acquisition_integration_id,intake.source_type,intake.preparation_hash,receipt.external_event_id,
  private.acquisition_source_identifier(evidence,'form_id'),private.acquisition_source_identifier(evidence,'campaign_id'),
  private.acquisition_source_identifier(evidence,'adset_id'),private.acquisition_source_identifier(evidence,'ad_id'),
  CASE WHEN jsonb_typeof(evidence->'created_time')='string' AND length(evidence->>'created_time')<=200 THEN evidence->>'created_time' ELSE NULL END,NULL)
 ON CONFLICT(id) DO NOTHING;
 IF FOUND THEN
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_lead_source',intake.id::text,'source_recorded','intake_ingestion',
   jsonb_build_object('receipt_id',receipt.id,'lead_id',intake.lead_id,'projection_version','source-touch-v1','preparation_hash',intake.preparation_hash),intake.workspace_id);
 END IF;
END $$;
CREATE OR REPLACE FUNCTION private.protect_acquisition_intake_retention() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF NEW.source IN ('facebook_acquisition','retell_inbound_acquisition','online_offer_acquisition') THEN
  NEW.retention_deletable:=false; NEW.retention_action:='keep';
  NEW.retention_rule:='acquisition_intake_review'; NEW.retention_reason:='Acquisition intake retention review required';
  NEW.retention_due_at:=NULL;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION private.accept_acquisition_online_offer(p_form_key text,p_submission uuid,p_prepared jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE definition jsonb; publication private.acquisition_form_publications%ROWTYPE;
 saved public.lead_form_submissions%ROWTYPE; fingerprint text; answers jsonb; lead uuid; intake uuid; amount numeric;
 evidence jsonb; selections jsonb; key text;
BEGIN
 -- Fresh checks take the same publication/workspace locks as the display path.
 definition:=private.read_acquisition_public_form(p_form_key);
 IF p_submission IS NULL OR p_prepared IS NULL OR jsonb_typeof(p_prepared)<>'object' OR octet_length(p_prepared::text)>65536
  OR p_prepared->>'version' IS DISTINCT FROM 'seller-intake-v1'
  OR p_prepared->>'source_type' IS DISTINCT FROM 'online_offer_portal'
  OR p_prepared->>'submission_id' IS DISTINCT FROM p_submission::text
  OR p_prepared->>'form_key' IS DISTINCT FROM p_form_key
  OR p_prepared->>'form_version' IS DISTINCT FROM definition->>'version'
  OR p_prepared->'request_evidence'->'form' IS DISTINCT FROM definition
  OR p_prepared->'request_evidence'->'submission'->>'submission_id' IS DISTINCT FROM p_submission::text
  OR p_prepared->'request_evidence'->'submission'->>'form_version' IS DISTINCT FROM definition->>'version'
  OR jsonb_typeof(p_prepared->'answers') IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_prepared->'field_evidence') IS DISTINCT FROM 'array'
  OR coalesce(p_prepared->>'classification','') NOT IN ('incomplete','unqualified','requires_human_review') THEN
  RAISE EXCEPTION 'Invalid prepared portal inquiry' USING ERRCODE='22023'; END IF;
 FOREACH key IN ARRAY ARRAY['property_verified','ownership_verified','contact_permission_granted','outreach_authorized','binding_offer'] LOOP
  IF p_prepared->key IS DISTINCT FROM 'false'::jsonb THEN RAISE EXCEPTION 'Invalid inquiry authority' USING ERRCODE='22023'; END IF;
 END LOOP;
 evidence:=p_prepared->'request_evidence'; selections:=evidence->'submission'->'selections';
 IF jsonb_typeof(selections) IS DISTINCT FROM 'object' OR selections->'privacy_acknowledged' IS DISTINCT FROM 'true'::jsonb THEN
  RAISE EXCEPTION 'Privacy acknowledgement required' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each(selections) e WHERE e.key NOT IN ('privacy_acknowledged','human_callback_requested','email_reply_requested') OR jsonb_typeof(e.value)<>'boolean') THEN
  RAISE EXCEPTION 'Invalid inquiry selections' USING ERRCODE='22023'; END IF;
 answers:=p_prepared->'answers';
 IF EXISTS(SELECT 1 FROM jsonb_each(answers) e WHERE jsonb_typeof(e.value)<>'string' OR length(e.value#>>'{}')>10000)
  OR coalesce(length(trim(answers->>'property_address')),0)=0 OR coalesce(length(trim(answers->>'city')),0)=0 THEN
  RAISE EXCEPTION 'Invalid seller answers' USING ERRCODE='22023'; END IF;
 IF p_prepared->>'asking_price' IS NOT NULL THEN
  IF p_prepared->>'asking_price' !~ '^[0-9]{1,10}\.[0-9]{2}$' THEN RAISE EXCEPTION 'Invalid seller price' USING ERRCODE='22023'; END IF;
  amount:=(p_prepared->>'asking_price')::numeric;
  IF amount>1000000000 THEN RAISE EXCEPTION 'Invalid seller price' USING ERRCODE='22023'; END IF;
 END IF;
 fingerprint:=encode(sha256(convert_to(p_prepared::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('form-submission:'||p_submission::text,0));
 -- Receipt contention may outlive approval even though shared locks are held.
 definition:=private.read_acquisition_public_form(p_form_key);
 SELECT * INTO publication FROM private.acquisition_form_publications WHERE form_key=p_form_key;
 SELECT * INTO saved FROM public.lead_form_submissions WHERE id=p_submission FOR UPDATE;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM publication.workspace_id OR saved.form_id IS DISTINCT FROM publication.form_id
   OR saved.acquisition_request_hash IS DISTINCT FROM fingerprint OR saved.request_manifest IS DISTINCT FROM p_prepared THEN
   RAISE EXCEPTION 'Inquiry identity conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('submission_id',p_submission,'status','received','duplicate',true);
 END IF;
 lead:=gen_random_uuid();
 INSERT INTO public.leads(id,property_address,city,state,zip_code,owner_first_name,owner_last_name,owner_phone_1,owner_email,
 source,inbound_channel,asking_price,status,sms_sequence_active,email_sequence_active,ai_calling_paused)
 VALUES(lead,answers->>'property_address',answers->>'city',answers->>'state',answers->>'zip_code',answers->>'first_name',answers->>'last_name',
 CASE WHEN answers->>'phone' IS NULL THEN NULL ELSE private.normalize_acquisition_contact('phone',answers->>'phone') END,
 CASE WHEN answers->>'email' IS NULL THEN NULL ELSE private.normalize_acquisition_contact('email',answers->>'email') END,
 'online_offer_acquisition','online_offer_portal',amount,'new',false,false,true);
 INSERT INTO public.lead_form_submissions(id,form_id,lead_id,workspace_id,acquisition_campaign_id,acquisition_request_hash,raw_answers,request_manifest,processing_status)
 VALUES(p_submission,publication.form_id,lead,publication.workspace_id,publication.campaign_id,fingerprint,evidence,p_prepared,'processed');
 UPDATE public.leads SET form_submission_id=p_submission WHERE id=lead;
 INSERT INTO public.workspace_leads(workspace_id,lead_id,binding_portal_receipt_id)
 VALUES(publication.workspace_id,lead,p_submission);
 INSERT INTO public.seller_intakes(workspace_id,lead_id,portal_receipt_id,source_type,intake_version,classification,prepared_answers,preparation_hash)
 VALUES(publication.workspace_id,lead,p_submission,'online_offer_portal','seller-intake-v1',p_prepared->>'classification',p_prepared,fingerprint)
 RETURNING id INTO intake;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('seller_intake',intake::text,'created','online_offer_intake',jsonb_build_object('lead_id',lead,'portal_receipt_id',p_submission,
 'form_id',publication.form_id,'classification',p_prepared->>'classification','preparation_hash',fingerprint),publication.workspace_id);
 RETURN jsonb_build_object('submission_id',p_submission,'status','received','duplicate',false);
END $$;
CREATE FUNCTION public.accept_acquisition_online_offer(p_form_key text,p_submission uuid,p_prepared jsonb) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.accept_acquisition_online_offer(p_form_key,p_submission,p_prepared) $$;
REVOKE ALL ON FUNCTION private.accept_acquisition_online_offer(text,uuid,jsonb),public.accept_acquisition_online_offer(text,uuid,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.accept_acquisition_online_offer(text,uuid,jsonb),public.accept_acquisition_online_offer(text,uuid,jsonb) TO service_role;
CREATE OR REPLACE FUNCTION private.acquisition_property_source_touches(p_workspace uuid,p_lead uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE source public.acquisition_lead_sources%ROWTYPE; property uuid; identity_state jsonb; campaign_state jsonb;
 snapshot public.acquisition_source_campaign_reviews%ROWTYPE; items jsonb:='[]'::jsonb;
 scanned integer:=0; excluded integer:=0; last_scanned uuid; more boolean:=false;
 association text; identity_review uuid; current_attribution boolean; attribution_status text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace property reporting access required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit<1 OR p_limit>50 THEN RAISE EXCEPTION 'Invalid source page size' USING ERRCODE='22023'; END IF;
 SELECT b.property_id INTO property FROM public.workspace_leads b JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
 WHERE b.workspace_id=p_workspace AND b.lead_id=p_lead;
 IF NOT FOUND THEN RAISE EXCEPTION 'Canonical workspace property unavailable' USING ERRCODE='42501'; END IF;
 -- Historical target references locate candidates; current review evaluation is
 -- decisive. Bound candidate pages prevent unlimited per-source policy calls.
 FOR source IN
  WITH candidates AS (
   (SELECT id FROM public.acquisition_lead_sources WHERE workspace_id=p_workspace AND lead_id=p_lead AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit+1)
   UNION
   (SELECT DISTINCT intake_id FROM public.acquisition_intake_identity_reviews WHERE workspace_id=p_workspace AND target_lead_id=p_lead AND (p_after IS NULL OR intake_id>p_after) ORDER BY intake_id LIMIT p_limit+1)
  ) SELECT s.* FROM public.acquisition_lead_sources s JOIN candidates c ON c.id=s.id
    WHERE s.workspace_id=p_workspace ORDER BY s.id LIMIT p_limit+1
 LOOP
  IF scanned=p_limit THEN more:=true; EXIT; END IF;
  scanned:=scanned+1; last_scanned:=source.id; identity_review:=NULL; association:='original_lead';
  IF source.lead_id<>p_lead THEN
   identity_state:=private.acquisition_intake_identity_state(p_workspace,source.id,NULL);
   IF identity_state->'link_current' IS DISTINCT FROM 'true'::jsonb
    OR identity_state->'latest_review'->>'target_lead_id' IS DISTINCT FROM p_lead::text
    OR identity_state->'latest_review'->>'target_property_id' IS DISTINCT FROM property::text THEN
    excluded:=excluded+1; CONTINUE; END IF;
   identity_review:=(identity_state->'latest_review'->>'id')::uuid;
   association:=CASE identity_state->'latest_review'->>'action' WHEN 'repeat_inquiry' THEN 'reviewed_repeat_inquiry' ELSE 'reviewed_property' END;
  END IF;
  campaign_state:=NULL; snapshot:=NULL; current_attribution:=false; attribution_status:='campaign_evidence_unavailable';
  IF source.external_campaign_id IS NOT NULL THEN
   BEGIN campaign_state:=private.acquisition_campaign_link_state(p_workspace,source.id);
   EXCEPTION WHEN SQLSTATE '55000' THEN campaign_state:=NULL;
   END;
  END IF;
  IF campaign_state IS NOT NULL THEN
   attribution_status:='campaign_review_not_current';
   IF campaign_state->'link_current'='true'::jsonb THEN
    SELECT * INTO snapshot FROM public.acquisition_source_campaign_reviews
     WHERE workspace_id=p_workspace AND source_id=source.id AND link_review_id=(campaign_state->'latest_review'->>'id')::uuid;
    current_attribution:=FOUND;
    attribution_status:=CASE WHEN current_attribution THEN 'current_captured_attribution' ELSE 'current_review_not_captured' END;
   END IF;
  END IF;
  IF NOT current_attribution THEN
   SELECT * INTO snapshot FROM public.acquisition_source_campaign_reviews
    WHERE workspace_id=p_workspace AND source_id=source.id ORDER BY created_at DESC,id DESC LIMIT 1;
  END IF;
  IF source.source_type='online_offer_portal' THEN attribution_status:='recorded_portal_campaign'; END IF;
  items:=items||jsonb_build_array(jsonb_build_object(
   'source_id',source.id,'original_lead_id',source.lead_id,'receipt_id',source.receipt_id,'integration_id',source.integration_id,
   'portal_receipt_id',source.portal_receipt_id,'portal_campaign_id',source.portal_campaign_id,'source_type',source.source_type,'inbound_revision',source.inbound_revision,'inbound_event_id',source.inbound_event_id,'preparation_hash',source.preparation_hash,'external_lead_id',source.external_lead_id,
   'form_id',source.form_id,'external_campaign_id',source.external_campaign_id,'adset_id',source.adset_id,'ad_id',source.ad_id,
   'submitted_at_raw',source.submitted_at_raw,'utm_data',source.utm_data,'association',association,'identity_review_id',identity_review,
   'attribution_status',attribution_status,'attribution_current',current_attribution,
   'current_campaign_id',CASE WHEN current_attribution THEN snapshot.campaign_id ELSE NULL END,
   'captured_attribution',CASE WHEN snapshot.id IS NULL THEN NULL ELSE jsonb_build_object('id',snapshot.id,'link_review_id',snapshot.link_review_id,
      'campaign_id',snapshot.campaign_id,'created_at',snapshot.created_at) END));
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'canonical_lead_id',p_lead,'property_id',property,
  'items',items,'next_after',CASE WHEN more THEN last_scanned ELSE NULL END,'scanned_count',scanned,'excluded_count',excluded,
  'count_scope','bounded_candidate_page','totals_available',false,'checked_at',statement_timestamp(),
  'ownership_verified',false,'contact_permission_granted',false,'execution_authorized',false);
END $$;

COMMIT;
