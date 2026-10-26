-- Versioned acquisition screening, not title verification or execution permission.
BEGIN;
CREATE TABLE public.acquisition_intake_assessments (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 intake_id uuid NOT NULL,
 sequence integer NOT NULL CHECK(sequence>0),
 policy_version text NOT NULL CHECK(policy_version='intake-qualification-v1'),
 classification text NOT NULL CHECK(classification IN ('qualified','incomplete','duplicate','unqualified','requires_human_review')),
 evidence_hash text NOT NULL,
 assessment jsonb NOT NULL CHECK(jsonb_typeof(assessment)='object'),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,intake_id,sequence),
 FOREIGN KEY(workspace_id,intake_id) REFERENCES public.seller_intakes(workspace_id,id)
);
ALTER TABLE public.acquisition_intake_assessments ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_intake_assessments FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_intake_assessments TO authenticated;
CREATE POLICY intake_assessments_read ON public.acquisition_intake_assessments FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER intake_assessments_immutable BEFORE UPDATE OR DELETE ON public.acquisition_intake_assessments
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.evaluate_acquisition_intake(p_workspace uuid,p_intake uuid)
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
REVOKE ALL ON FUNCTION private.evaluate_acquisition_intake(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_intake_qualification_state(p_workspace uuid,p_intake uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE assessment jsonb; fingerprint text; latest public.acquisition_intake_assessments%ROWTYPE;
BEGIN
 assessment:=private.evaluate_acquisition_intake(p_workspace,p_intake);
 fingerprint:=encode(sha256(convert_to(assessment::text,'UTF8')),'hex');
 SELECT * INTO latest FROM public.acquisition_intake_assessments WHERE workspace_id=p_workspace AND intake_id=p_intake ORDER BY sequence DESC LIMIT 1;
 RETURN jsonb_build_object('assessment',assessment,'evidence_hash',fingerprint,'sequence',coalesce(latest.sequence,0),
  'latest_assessment',CASE WHEN latest.id IS NULL THEN NULL ELSE to_jsonb(latest) END,
  'assessment_current',coalesce(latest.evidence_hash=fingerprint,false));
END $$;

CREATE FUNCTION private.record_acquisition_intake_assessment(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,p_evidence_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; latest_identity public.acquisition_intake_identity_reviews%ROWTYPE;
 saved public.acquisition_intake_assessments%ROWTYPE; state jsonb; active boolean; generation integer;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace intake assessment access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence<0 OR p_evidence_hash IS NULL OR p_evidence_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'Assessment reference and expected state required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin','operator')
  AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Assessment authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('intake-assessment:'||p_id,0));
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=p_workspace AND id=p_intake FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_intake_assessments WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.intake_id,saved.sequence,saved.evidence_hash,saved.actor_id)
   IS DISTINCT FROM ROW(p_workspace,p_intake,p_expected_sequence+1,p_evidence_hash,auth.uid()) THEN
   RAISE EXCEPTION 'Assessment request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('assessment_id',saved.id,'sequence',saved.sequence,'classification',saved.classification,'duplicate',true,'outreach_authorized',false);
 END IF;
 SELECT * INTO latest_identity FROM public.acquisition_intake_identity_reviews WHERE workspace_id=p_workspace AND intake_id=p_intake ORDER BY sequence DESC LIMIT 1;
 IF latest_identity.id IS NOT NULL THEN
  -- Serialize identity validity against reviewer revocation and canonical edits.
  PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   WHERE m.workspace_id=p_workspace AND m.user_id=latest_identity.actor_id FOR SHARE OF m,p;
  PERFORM 1 FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
   JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
   WHERE b.workspace_id=p_workspace AND b.lead_id=latest_identity.target_lead_id FOR SHARE OF b,l,p;
 END IF;
 state:=private.acquisition_intake_qualification_state(p_workspace,p_intake);
 IF (state->>'sequence')::integer<>p_expected_sequence OR state->>'evidence_hash'<>p_evidence_hash THEN
  RAISE EXCEPTION 'Assessment evidence changed' USING ERRCODE='40001'; END IF;
 generation:=p_expected_sequence+1;
 INSERT INTO public.acquisition_intake_assessments(id,workspace_id,intake_id,sequence,policy_version,classification,evidence_hash,assessment,actor_id)
 VALUES(p_id,p_workspace,p_intake,generation,'intake-qualification-v1',state->'assessment'->>'classification',p_evidence_hash,state->'assessment',auth.uid());
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('seller_intake_assessment',p_intake::text,'assessed',auth.uid()::text,
  jsonb_build_object('assessment_id',p_id,'sequence',generation,'classification',state->'assessment'->>'classification','evidence_hash',p_evidence_hash),p_workspace);
 RETURN jsonb_build_object('assessment_id',p_id,'sequence',generation,'classification',state->'assessment'->>'classification','duplicate',false,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_intake_qualification_state(p_workspace uuid,p_intake uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_intake_qualification_state(p_workspace,p_intake) $$;
CREATE FUNCTION public.record_acquisition_intake_assessment(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,p_evidence_hash text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.record_acquisition_intake_assessment(p_id,p_workspace,p_intake,p_expected_sequence,p_evidence_hash) $$;
REVOKE ALL ON FUNCTION private.acquisition_intake_qualification_state(uuid,uuid),public.acquisition_intake_qualification_state(uuid,uuid),
 private.record_acquisition_intake_assessment(uuid,uuid,uuid,integer,text),public.record_acquisition_intake_assessment(uuid,uuid,uuid,integer,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_intake_qualification_state(uuid,uuid),public.acquisition_intake_qualification_state(uuid,uuid),
 private.record_acquisition_intake_assessment(uuid,uuid,uuid,integer,text),public.record_acquisition_intake_assessment(uuid,uuid,uuid,integer,text) TO authenticated;
COMMIT;
