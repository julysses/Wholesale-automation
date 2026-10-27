-- Call-scoped immutable seller intake revisions over the existing CRM.
BEGIN;
ALTER TABLE public.call_events ADD CONSTRAINT acquisition_call_event_workspace_unique UNIQUE(id,workspace_id);
ALTER TABLE public.seller_intakes
 ALTER COLUMN receipt_id DROP NOT NULL,
 DROP CONSTRAINT seller_intakes_source_type_check,
 ADD COLUMN inbound_integration_id uuid,
 ADD COLUMN inbound_call_id text,
 ADD COLUMN inbound_event_id uuid,
 ADD COLUMN inbound_request_id uuid,
 ADD COLUMN inbound_revision integer,
 ADD CONSTRAINT seller_intakes_inbound_route_fk FOREIGN KEY(inbound_integration_id,workspace_id) REFERENCES private.acquisition_inbound_routes(integration_id,workspace_id),
 ADD CONSTRAINT seller_intakes_inbound_event_fk FOREIGN KEY(inbound_event_id,workspace_id) REFERENCES public.call_events(id,workspace_id),
 ADD CONSTRAINT seller_intakes_origin CHECK (
  (source_type='facebook_native_form' AND receipt_id IS NOT NULL AND inbound_integration_id IS NULL AND inbound_call_id IS NULL
   AND inbound_event_id IS NULL AND inbound_request_id IS NULL AND inbound_revision IS NULL)
  OR (source_type='retell_inbound' AND receipt_id IS NULL AND inbound_integration_id IS NOT NULL AND inbound_call_id IS NOT NULL
   AND inbound_call_id ~ '^[A-Za-z0-9_-]{1,200}$' AND inbound_event_id IS NOT NULL AND inbound_request_id IS NOT NULL
   AND inbound_revision IS NOT NULL AND inbound_revision>0));
CREATE UNIQUE INDEX seller_intakes_inbound_request ON public.seller_intakes(inbound_integration_id,inbound_request_id) WHERE source_type='retell_inbound';
CREATE UNIQUE INDEX seller_intakes_inbound_revision ON public.seller_intakes(inbound_integration_id,inbound_call_id,inbound_revision) WHERE source_type='retell_inbound';
ALTER TABLE public.acquisition_lead_sources
 ALTER COLUMN receipt_id DROP NOT NULL,
 DROP CONSTRAINT acquisition_lead_sources_source_type_check,
 ADD COLUMN inbound_event_id uuid,
 ADD COLUMN inbound_revision integer,
 ADD CONSTRAINT acquisition_source_inbound_event_fk FOREIGN KEY(inbound_event_id,workspace_id) REFERENCES public.call_events(id,workspace_id),
 ADD CONSTRAINT acquisition_source_origin CHECK (
  (source_type='facebook_native_form' AND receipt_id IS NOT NULL AND inbound_event_id IS NULL AND inbound_revision IS NULL)
  OR (source_type='retell_inbound' AND receipt_id IS NULL AND inbound_event_id IS NOT NULL AND inbound_revision IS NOT NULL AND inbound_revision>0
   AND form_id IS NULL AND external_campaign_id IS NULL AND adset_id IS NULL AND ad_id IS NULL AND submitted_at_raw IS NULL AND utm_data IS NULL));
CREATE OR REPLACE FUNCTION private.record_acquisition_lead_source(p_intake uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; receipt public.webhook_jobs%ROWTYPE; evidence jsonb;
BEGIN
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source intake unavailable'; END IF;
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
 IF NEW.source IN ('facebook_acquisition','retell_inbound_acquisition') THEN
  NEW.retention_deletable:=false; NEW.retention_action:='keep';
  NEW.retention_rule:='acquisition_intake_review'; NEW.retention_reason:='Acquisition intake retention review required';
  NEW.retention_due_at:=NULL;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION private.record_acquisition_inbound_intake(p_integration uuid,p_number text,p_agent text,p_agent_version integer,
 p_call text,p_request uuid,p_expected_revision integer,p_prepared jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; event public.call_events%ROWTYPE;
 saved public.seller_intakes%ROWTYPE; latest public.seller_intakes%ROWTYPE;
 fingerprint text; answers jsonb; lead uuid; phone text; email text; amount numeric; k text; notes text[]:=ARRAY[]::text[];
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND provider='retell' AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number OR route.agent_id IS DISTINCT FROM p_agent
  OR route.agent_version IS DISTINCT FROM p_agent_version THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_request IS NULL OR p_expected_revision IS NULL
  OR p_expected_revision NOT BETWEEN 0 AND 999999999 OR p_prepared IS NULL OR jsonb_typeof(p_prepared)<>'object'
  OR octet_length(p_prepared::text)>131072 OR (SELECT count(*) FROM jsonb_object_keys(p_prepared))<>15
  OR NOT p_prepared ?& ARRAY['version','answers','field_evidence','asking_price','authority_asserted','classification','reason_codes','missing_fields','conflicting_fields','ambiguous_fields','property_verified','ownership_verified','contact_permission_granted','outreach_authorized','binding_offer']
  OR p_prepared->>'version' IS DISTINCT FROM 'seller-intake-v1'
  OR coalesce(p_prepared->>'classification','') NOT IN ('incomplete','unqualified','requires_human_review')
  OR jsonb_typeof(p_prepared->'answers') IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_prepared->'authority_asserted') NOT IN ('boolean','null') THEN
  RAISE EXCEPTION 'Invalid prepared inbound intake' USING ERRCODE='22023'; END IF;
 FOREACH k IN ARRAY ARRAY['property_verified','ownership_verified','contact_permission_granted','outreach_authorized','binding_offer'] LOOP
  IF p_prepared->k IS DISTINCT FROM 'false'::jsonb THEN RAISE EXCEPTION 'Intake cannot authorize action' USING ERRCODE='22023'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['field_evidence','reason_codes','missing_fields','conflicting_fields','ambiguous_fields'] LOOP
  IF jsonb_typeof(p_prepared->k) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid intake evidence' USING ERRCODE='22023'; END IF;
 END LOOP;
 answers:=p_prepared->'answers';
 IF answers='{}'::jsonb OR EXISTS(SELECT 1 FROM jsonb_each(answers) WHERE jsonb_typeof(value)<>'string' OR length(value#>>'{}')>2000
  OR key NOT IN ('property_address','city','state','zip_code','county','full_name','first_name','last_name','phone','email','motivation','timeline','condition','asking_price','occupancy','authority','interested')) THEN
  RAISE EXCEPTION 'Invalid inbound answers' USING ERRCODE='22023'; END IF;
 IF p_prepared->'asking_price' IS DISTINCT FROM 'null'::jsonb THEN
  IF jsonb_typeof(p_prepared->'asking_price') IS DISTINCT FROM 'string' OR p_prepared->>'asking_price' !~ '^[0-9]{1,10}\.[0-9]{2}$' THEN RAISE EXCEPTION 'Invalid price' USING ERRCODE='22023'; END IF;
  amount:=(p_prepared->>'asking_price')::numeric;
  IF amount>1000000000 THEN RAISE EXCEPTION 'Invalid price' USING ERRCODE='22023'; END IF;
 END IF;
 fingerprint:=encode(sha256(convert_to(p_prepared::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound-intake:'||p_integration::text||':'||p_request::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||p_call,0));
 SELECT * INTO saved FROM public.seller_intakes WHERE inbound_integration_id=p_integration AND inbound_request_id=p_request;
 IF FOUND THEN
  IF saved.inbound_call_id IS DISTINCT FROM p_call OR saved.inbound_revision<>p_expected_revision+1 OR saved.preparation_hash<>fingerprint THEN
   RAISE EXCEPTION 'Inbound intake request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'lead_id',saved.lead_id,'workspace_id',saved.workspace_id,'revision',saved.inbound_revision,'duplicate',true,'execution_authorized',false);
 END IF;
 SELECT * INTO event FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
  AND acquisition_event_type='call_started' AND acquisition_projection->>'call_status'='ongoing';
 IF NOT FOUND OR EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
   AND acquisition_event_type IN ('call_ended','call_analyzed')) THEN RAISE EXCEPTION 'Ongoing inbound ledger required' USING ERRCODE='55000'; END IF;
 SELECT * INTO latest FROM public.seller_intakes WHERE inbound_integration_id=p_integration AND inbound_call_id=p_call ORDER BY inbound_revision DESC LIMIT 1;
 IF coalesce(latest.inbound_revision,0)<>p_expected_revision THEN RAISE EXCEPTION 'Inbound intake revision changed' USING ERRCODE='40001'; END IF;
 IF latest.id IS NULL THEN
  IF nullif(trim(answers->>'phone'),'') IS NOT NULL THEN
   BEGIN phone:=private.normalize_acquisition_contact('phone',answers->>'phone'); EXCEPTION WHEN SQLSTATE '22023' THEN notes:=array_append(notes,'PHONE_REVIEW_REQUIRED'); END;
  END IF;
  IF nullif(trim(answers->>'email'),'') IS NOT NULL THEN
   BEGIN email:=private.normalize_acquisition_contact('email',answers->>'email'); EXCEPTION WHEN SQLSTATE '22023' THEN notes:=array_append(notes,'EMAIL_REVIEW_REQUIRED'); END;
  END IF;
  lead:=gen_random_uuid();
  INSERT INTO public.leads(id,property_address,city,state,zip_code,owner_first_name,owner_last_name,owner_phone_1,owner_email,
   source,inbound_channel,asking_price,status,sms_sequence_active,email_sequence_active,ai_calling_paused)
  VALUES(lead,coalesce(answers->>'property_address',''),coalesce(answers->>'city',''),nullif(answers->>'state',''),nullif(answers->>'zip_code',''),
   nullif(answers->>'first_name',''),nullif(answers->>'last_name',''),phone,email,'retell_inbound_acquisition','retell_inbound',amount,'new',false,false,true);
  INSERT INTO public.workspace_leads(workspace_id,lead_id,bound_by,binding_integration_id) VALUES(route.workspace_id,lead,NULL,p_integration);
 ELSE
  lead:=latest.lead_id;
  -- Never mutate a reviewed canonical identity or previous seller assertion.
  notes:=array_append(notes,'CRM_INITIAL_ASSERTIONS_PRESERVED');
 END IF;
 INSERT INTO public.seller_intakes(workspace_id,lead_id,receipt_id,source_type,intake_version,classification,prepared_answers,preparation_hash,normalization_notes,
  inbound_integration_id,inbound_call_id,inbound_event_id,inbound_request_id,inbound_revision)
 VALUES(route.workspace_id,lead,NULL,'retell_inbound','seller-intake-v1',p_prepared->>'classification',p_prepared,fingerprint,notes,
  p_integration,p_call,event.id,p_request,p_expected_revision+1) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('seller_intake',saved.id::text,'created','inbound_intake',jsonb_build_object('lead_id',lead,'revision',saved.inbound_revision,'preparation_hash',fingerprint,'inbound_event_id',event.id),route.workspace_id);
 RETURN jsonb_build_object('id',saved.id,'lead_id',lead,'workspace_id',route.workspace_id,'revision',saved.inbound_revision,'duplicate',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_inbound_intake(uuid,text,text,integer,text,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_inbound_intake(uuid,text,text,integer,text,uuid,integer,jsonb) TO service_role;
CREATE FUNCTION public.record_acquisition_inbound_intake(p_integration uuid,p_number text,p_agent text,p_agent_version integer,
 p_call text,p_request uuid,p_expected_revision integer,p_prepared jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_inbound_intake(p_integration,p_number,p_agent,p_agent_version,p_call,p_request,p_expected_revision,p_prepared) $$;
REVOKE ALL ON FUNCTION public.record_acquisition_inbound_intake(uuid,text,text,integer,text,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_acquisition_inbound_intake(uuid,text,text,integer,text,uuid,integer,jsonb) TO service_role;
CREATE OR REPLACE FUNCTION private.evaluate_acquisition_intake(p_workspace uuid,p_intake uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; prepared jsonb; answers jsonb; identity_state jsonb; target jsonb;
 active boolean; classification text; reasons text[]:=ARRAY[]::text[]; missing text[]:=ARRAY[]::text[];
 name text; valid_contact boolean; structurally_valid boolean; county text; state text; result jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace intake access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=p_workspace AND id=p_intake;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 prepared:=intake.prepared_answers; answers:=prepared->'answers';
 identity_state:=private.acquisition_intake_identity_state(p_workspace,p_intake,NULL);
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 IF identity_state->'latest_review'->>'target_lead_id' IS NOT NULL THEN
  target:=private.acquisition_identity_target(p_workspace,(identity_state->'latest_review'->>'target_lead_id')::uuid);
 END IF;
 structurally_valid:=coalesce(jsonb_typeof(answers)='object'
  AND jsonb_typeof(prepared->'conflicting_fields')='array' AND jsonb_typeof(prepared->'ambiguous_fields')='array'
  AND jsonb_typeof(prepared->'missing_fields')='array'
  AND (jsonb_typeof(prepared->'authority_asserted') IN ('boolean','null'))
  AND prepared->>'version'='seller-intake-v1',false);
 IF structurally_valid THEN
  FOREACH name IN ARRAY ARRAY['property_address','city','state','authority','condition','timeline','motivation','asking_price'] LOOP
   IF nullif(trim(answers->>name),'') IS NULL THEN missing:=array_append(missing,name); END IF;
  END LOOP;
  valid_contact:=private.acquisition_optional_contact('phone',answers->>'phone') IS NOT NULL
   OR private.acquisition_optional_contact('email',answers->>'email') IS NOT NULL;
  IF NOT valid_contact THEN missing:=array_append(missing,'valid_contact'); END IF;
 END IF;
 county:=private.acquisition_identity_text(target->>'county');
 state:=private.acquisition_identity_text(target->>'county_state');
 IF state='texas' THEN state:='tx'; END IF;
 IF NOT structurally_valid THEN classification:='requires_human_review'; reasons:=ARRAY['INTAKE_EVIDENCE_INVALID'];
 ELSIF intake.source_type='retell_inbound' AND EXISTS(SELECT 1 FROM public.seller_intakes newer WHERE newer.inbound_integration_id=intake.inbound_integration_id AND newer.inbound_call_id=intake.inbound_call_id AND newer.inbound_revision>intake.inbound_revision) THEN
  classification:='requires_human_review'; reasons:=ARRAY['SUPERSEDED_INBOUND_INTAKE'];
 ELSIF jsonb_array_length(prepared->'conflicting_fields')>0 OR jsonb_array_length(prepared->'ambiguous_fields')>0 THEN
  classification:='requires_human_review'; reasons:=ARRAY['AMBIGUOUS_OR_CONFLICTING_ANSWERS'];
 ELSIF prepared->'authority_asserted'='false'::jsonb OR lower(trim(answers->>'interested')) IN ('no','false','0') THEN
  classification:='unqualified'; reasons:=ARRAY['SELLER_DENIES_AUTHORITY_OR_INTEREST'];
 ELSIF identity_state->'link_current'='true'::jsonb AND identity_state->'latest_review'->>'action'='repeat_inquiry' THEN
  classification:='duplicate'; reasons:=ARRAY['REVIEWED_REPEAT_INQUIRY'];
 ELSIF cardinality(missing)>0 THEN classification:='incomplete'; reasons:=ARRAY['MISSING_REQUIRED_ANSWERS'];
 ELSIF prepared->'authority_asserted' IS DISTINCT FROM 'true'::jsonb
  OR prepared->>'asking_price' IS NULL OR prepared->>'asking_price' !~ '^[0-9]{1,10}\.[0-9]{2}$' THEN
  classification:='requires_human_review'; reasons:=ARRAY['AUTHORITY_OR_PRICE_UNRESOLVED'];
 ELSIF active IS DISTINCT FROM true THEN classification:='requires_human_review'; reasons:=ARRAY['ACQUISITION_ACTIVATION_DISABLED'];
 ELSIF identity_state->'link_current' IS DISTINCT FROM 'true'::jsonb THEN
  classification:='requires_human_review'; reasons:=ARRAY['CURRENT_CANONICAL_PROPERTY_REVIEW_REQUIRED'];
 ELSIF state IS NULL OR county IS NULL THEN classification:='requires_human_review'; reasons:=ARRAY['CANONICAL_TERRITORY_MISSING'];
 ELSIF state<>'tx' OR county NOT IN ('dallas','collin') THEN
  classification:='unqualified'; reasons:=ARRAY['OUTSIDE_INITIAL_TERRITORY'];
 ELSE classification:='qualified'; reasons:=ARRAY['COMPLETE_INTAKE_WITH_REVIEWED_IN_TERRITORY_PROPERTY'];
 END IF;
 result:=jsonb_build_object('policy_version','intake-qualification-v1','workspace_id',p_workspace,'intake_id',p_intake,
  'source_lead_id',intake.lead_id,'preparation_hash',intake.preparation_hash,
  'classification',classification,'reason_codes',to_jsonb(reasons),'missing_fields',to_jsonb(missing),
  'identity_review_id',identity_state->'latest_review'->'id','identity_sequence',identity_state->'sequence',
  'identity_link_current',identity_state->'link_current','target_lead_id',identity_state->'latest_review'->'target_lead_id',
  'target_property_id',identity_state->'latest_review'->'target_property_id',
  'target_snapshot',target,'current_target_hash',encode(sha256(convert_to(target::text,'UTF8')),'hex'),
  'canonical_county',county,'canonical_state',state,'activation_enabled',coalesce(active,false),
  'territory_basis','canonical_county_record','ownership_verified',false,'contact_permission_granted',false,
  'outreach_authorized',false,'binding_offer',false);
 RETURN result;
END $$;

COMMIT;
