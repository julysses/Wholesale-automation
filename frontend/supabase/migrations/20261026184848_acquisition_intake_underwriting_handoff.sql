-- Atomic qualified-intake handoff with downstream freshness enforcement.
BEGIN;
ALTER TABLE public.deal_analyses ADD CONSTRAINT deal_analyses_workspace_identity UNIQUE(workspace_id,id);
ALTER TABLE public.acquisition_intake_assessments ADD CONSTRAINT intake_assessment_identity UNIQUE(workspace_id,intake_id,id);
ALTER TABLE public.acquisition_intake_identity_reviews ADD CONSTRAINT intake_review_identity UNIQUE(workspace_id,intake_id,id);
CREATE TABLE public.acquisition_analysis_intakes (
 analysis_id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 intake_id uuid NOT NULL,
 assessment_id uuid NOT NULL,
 identity_review_id uuid NOT NULL,
 evidence_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,analysis_id) REFERENCES public.deal_analyses(workspace_id,id),
 FOREIGN KEY(workspace_id,intake_id,assessment_id) REFERENCES public.acquisition_intake_assessments(workspace_id,intake_id,id),
 FOREIGN KEY(workspace_id,intake_id,identity_review_id) REFERENCES public.acquisition_intake_identity_reviews(workspace_id,intake_id,id)
);
CREATE INDEX acquisition_analysis_intakes_source ON public.acquisition_analysis_intakes(workspace_id,intake_id,analysis_id);
ALTER TABLE public.acquisition_analysis_intakes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_analysis_intakes FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_analysis_intakes TO authenticated;
CREATE POLICY analysis_intake_read ON public.acquisition_analysis_intakes FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER analysis_intake_immutable BEFORE UPDATE OR DELETE ON public.acquisition_analysis_intakes
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

-- This internal predicate does not impersonate a user for worker calls. It checks
-- the saved immutable qualified assessment against its live source dependencies.
CREATE FUNCTION private.acquisition_intake_analysis_valid(p_analysis uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT NOT EXISTS(SELECT 1 FROM public.acquisition_analysis_intakes WHERE analysis_id=p_analysis) OR EXISTS(
 SELECT 1 FROM public.acquisition_analysis_intakes c
 JOIN public.deal_analyses a ON a.id=c.analysis_id AND a.workspace_id=c.workspace_id
 JOIN public.seller_intakes i ON i.id=c.intake_id AND i.workspace_id=c.workspace_id
 JOIN public.acquisition_intake_assessments q ON q.id=c.assessment_id AND q.intake_id=c.intake_id AND q.workspace_id=c.workspace_id
 JOIN public.acquisition_intake_identity_reviews r ON r.id=c.identity_review_id AND r.intake_id=c.intake_id AND r.workspace_id=c.workspace_id
 JOIN public.workspaces w ON w.id=c.workspace_id
 JOIN public.workspace_memberships m ON m.workspace_id=c.workspace_id AND m.user_id=r.actor_id
 JOIN public.profiles p ON p.id=r.actor_id
 WHERE c.analysis_id=p_analysis AND w.status='active' AND q.classification='qualified' AND q.policy_version='intake-qualification-v1'
  AND q.evidence_hash=c.evidence_hash AND q.assessment->>'preparation_hash'=i.preparation_hash
  AND q.assessment->>'identity_review_id'=r.id::text AND r.action='link_property'
  AND r.sequence=(SELECT max(sequence) FROM public.acquisition_intake_identity_reviews WHERE workspace_id=c.workspace_id AND intake_id=c.intake_id)
  AND r.target_lead_id=a.lead_id AND r.target_property_id=a.property_id
  AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=r.membership_updated_at AND p.status='approved'
  AND encode(sha256(convert_to(private.acquisition_identity_target(c.workspace_id,a.lead_id)::text,'UTF8')),'hex')=r.target_hash
  AND q.assessment->>'current_target_hash'=r.target_hash
  AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled));
$$;
CREATE FUNCTION private.lock_acquisition_intake_analysis(p_analysis uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE context public.acquisition_analysis_intakes%ROWTYPE; reviewer uuid; target uuid;
BEGIN
 SELECT * INTO context FROM public.acquisition_analysis_intakes WHERE analysis_id=p_analysis;
 IF NOT FOUND THEN RETURN; END IF;
 PERFORM 1 FROM private.acquisition_activation WHERE singleton FOR SHARE;
 PERFORM 1 FROM public.workspaces WHERE id=context.workspace_id FOR SHARE;
 PERFORM 1 FROM public.seller_intakes WHERE id=context.intake_id FOR SHARE;
 SELECT actor_id,target_lead_id INTO reviewer,target FROM public.acquisition_intake_identity_reviews WHERE id=context.identity_review_id;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
  WHERE m.workspace_id=context.workspace_id AND m.user_id=reviewer FOR SHARE OF m,p;
 PERFORM 1 FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
  JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
  WHERE b.workspace_id=context.workspace_id AND b.lead_id=target FOR SHARE OF b,l,p;
 IF NOT private.acquisition_intake_analysis_valid(p_analysis) THEN
  RAISE EXCEPTION 'Intake qualification changed; reassess before underwriting or approval' USING ERRCODE='40001'; END IF;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_intake_analysis_valid(uuid),private.lock_acquisition_intake_analysis(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.reserve_acquisition_intake_analysis(p_id uuid,p_workspace uuid,p_intake uuid,p_evidence_hash text,p_inputs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; context public.acquisition_analysis_intakes%ROWTYPE;
 saved public.deal_analyses%ROWTYPE; state jsonb; assessment jsonb; reserved jsonb; active boolean; target uuid; reviewer uuid;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace underwriting access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_evidence_hash IS NULL OR p_evidence_hash!~'^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Intake evidence reference required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin','operator') AND p.status='approved'
  AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Underwriting authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('intake-analysis-request:'||p_id,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('intake-assessment:'||p_id,0));
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=p_workspace AND id=p_intake FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO context FROM public.acquisition_analysis_intakes WHERE analysis_id=p_id;
 IF FOUND THEN
  SELECT * INTO saved FROM public.deal_analyses WHERE id=p_id;
  IF ROW(context.workspace_id,context.intake_id,context.evidence_hash,saved.acquisition_inputs,saved.created_by)
   IS DISTINCT FROM ROW(p_workspace,p_intake,p_evidence_hash,p_inputs,auth.uid()) THEN RAISE EXCEPTION 'Intake analysis request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'lead_id',saved.lead_id,'property_id',saved.property_id,
   'intake_id',p_intake,'assessment_id',context.assessment_id,'revision',saved.acquisition_revision,'status',saved.acquisition_status,
   'qualification_current',private.acquisition_intake_analysis_valid(p_id),'duplicate',true);
 END IF;
 SELECT target_lead_id,actor_id INTO target,reviewer FROM public.acquisition_intake_identity_reviews
  WHERE workspace_id=p_workspace AND intake_id=p_intake ORDER BY sequence DESC LIMIT 1;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
  WHERE m.workspace_id=p_workspace AND m.user_id=reviewer FOR SHARE OF m,p;
 PERFORM 1 FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
  WHERE b.workspace_id=p_workspace AND b.lead_id=target FOR SHARE OF b,l,p;
 state:=private.acquisition_intake_qualification_state(p_workspace,p_intake);
 IF state->>'evidence_hash' IS DISTINCT FROM p_evidence_hash OR state->'assessment'->>'classification' IS DISTINCT FROM 'qualified'
  OR state->'assessment'->'identity_link_current' IS DISTINCT FROM 'true'::jsonb THEN
  RAISE EXCEPTION 'Fresh qualified canonical intake required' USING ERRCODE='40001'; END IF;
 target:=(state->'assessment'->>'target_lead_id')::uuid;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-analysis:'||p_workspace::text||':'||target::text,0));
 IF EXISTS(SELECT 1 FROM public.deal_analyses WHERE id=p_id) THEN RAISE EXCEPTION 'Analysis already belongs to another request' USING ERRCODE='23505'; END IF;
 -- Snapshot and reservation commit together, including rollback on malformed inputs.
 assessment:=private.record_acquisition_intake_assessment(p_id,p_workspace,p_intake,(state->>'sequence')::integer,p_evidence_hash);
 reserved:=private.reserve_acquisition_analysis(p_id,p_workspace,target,p_inputs);
 INSERT INTO public.acquisition_analysis_intakes(analysis_id,workspace_id,intake_id,assessment_id,identity_review_id,evidence_hash)
 VALUES(p_id,p_workspace,p_intake,(assessment->>'assessment_id')::uuid,(state->'assessment'->>'identity_review_id')::uuid,p_evidence_hash);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_analysis',p_id::text,'intake_handoff',auth.uid()::text,
  jsonb_build_object('intake_id',p_intake,'source_lead_id',intake.lead_id,'canonical_lead_id',target,'assessment_id',assessment->'assessment_id','evidence_hash',p_evidence_hash),p_workspace);
 RETURN reserved||jsonb_build_object('intake_id',p_intake,'assessment_id',assessment->'assessment_id','qualification_current',true,'duplicate',false);
END $$;
CREATE FUNCTION public.reserve_acquisition_intake_analysis(p_id uuid,p_workspace uuid,p_intake uuid,p_evidence_hash text,p_inputs jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.reserve_acquisition_intake_analysis(p_id,p_workspace,p_intake,p_evidence_hash,p_inputs) $$;
REVOKE ALL ON FUNCTION private.reserve_acquisition_intake_analysis(uuid,uuid,uuid,text,jsonb),public.reserve_acquisition_intake_analysis(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.reserve_acquisition_intake_analysis(uuid,uuid,uuid,text,jsonb),public.reserve_acquisition_intake_analysis(uuid,uuid,uuid,text,jsonb) TO authenticated;

-- Preserve existing contracts and grants while enforcing source freshness.
CREATE OR REPLACE FUNCTION private.acquisition_calculation_actor_valid(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.deal_analyses a JOIN private.acquisition_analysis_jobs j ON j.analysis_id=a.id
  JOIN public.workspaces w ON w.id=a.workspace_id JOIN public.workspace_memberships m ON m.workspace_id=a.workspace_id AND m.user_id=a.created_by
  JOIN public.profiles p ON p.id=a.created_by JOIN auth.sessions s ON s.id=j.session_id AND s.user_id=a.created_by
  WHERE a.id=p_id AND private.acquisition_intake_analysis_valid(p_id) AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin','operator') AND p.status='approved'
   AND (s.not_after IS NULL OR s.not_after>now()) AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled));
$$;

CREATE OR REPLACE FUNCTION private.complete_acquisition_calculation(p_id uuid,p_workspace uuid,p_input_hash text,p_outputs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.deal_analyses%ROWTYPE; output jsonb; result_status text;
BEGIN
 PERFORM private.lock_acquisition_intake_analysis(p_id);
 SELECT * INTO saved FROM public.deal_analyses WHERE id=p_id AND workspace_id=p_workspace FOR UPDATE;
 IF NOT FOUND OR NOT private.acquisition_calculation_actor_valid(p_id) THEN
  RAISE EXCEPTION 'Analysis calculation is not authorized' USING ERRCODE='42501'; END IF;
 IF p_input_hash IS NULL OR p_input_hash IS DISTINCT FROM (SELECT input_hash FROM private.acquisition_analysis_jobs WHERE analysis_id=p_id) THEN
  RAISE EXCEPTION 'Analysis input identity mismatch' USING ERRCODE='23505'; END IF;
 result_status:=p_outputs->>'status';
 IF p_outputs IS NULL OR jsonb_typeof(p_outputs) IS DISTINCT FROM 'object' OR octet_length(p_outputs::text)>524288
 OR p_outputs->>'calculation_version' IS DISTINCT FROM saved.calculation_version
 OR p_outputs->'binding_offer' IS DISTINCT FROM 'false'::jsonb OR p_outputs->'human_approval_required' IS DISTINCT FROM 'true'::jsonb
 OR result_status IS NULL OR result_status NOT IN ('calculated','incomplete','invalid') THEN
  RAISE EXCEPTION 'Invalid calculation result' USING ERRCODE='22023'; END IF;
 IF result_status='invalid' THEN
  IF p_outputs->>'error_code' IS DISTINCT FROM 'INVALID_INPUTS' THEN RAISE EXCEPTION 'Invalid calculation rejection' USING ERRCODE='22023'; END IF;
 ELSE
  IF p_outputs->>'strategy' IS DISTINCT FROM saved.acquisition_strategy OR jsonb_typeof(p_outputs->'cases') IS DISTINCT FROM 'object'
   OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_outputs->'cases') key) IS DISTINCT FROM ARRAY['base','downside','upside'] THEN
   RAISE EXCEPTION 'Calculation cases do not match request' USING ERRCODE='22023'; END IF;
 END IF;
 output:=jsonb_set(p_outputs,'{persisted}','true'::jsonb);
 IF saved.acquisition_status<>'pending' THEN
  IF saved.acquisition_outputs IS DISTINCT FROM output THEN RAISE EXCEPTION 'Completed analysis is immutable' USING ERRCODE='23505'; END IF;
 ELSE
  UPDATE public.deal_analyses SET acquisition_outputs=output,acquisition_status=result_status WHERE id=p_id RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_analysis',p_id::text,'calculated','acquisition_calculator',
   jsonb_build_object('revision',saved.acquisition_revision,'status',result_status,'input_hash',p_input_hash,'calculation_version',saved.calculation_version),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'status',saved.acquisition_status,'revision',saved.acquisition_revision);
END $$;

CREATE OR REPLACE FUNCTION private.propose_acquisition_offer(p_id uuid,p_workspace uuid,p_analysis uuid,p_case text,p_amount numeric,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE analysis public.deal_analyses%ROWTYPE; saved public.offer_recommendations%ROWTYPE; ceiling numeric; case_output jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO analysis FROM public.deal_analyses WHERE id=p_analysis AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace analysis unavailable' USING ERRCODE='42501'; END IF;
 PERFORM private.lock_acquisition_intake_analysis(p_analysis);
 IF p_id IS NULL OR p_case IS NULL OR p_case NOT IN ('base','downside','upside') OR p_amount IS NULL
 OR NOT(p_amount>0 AND p_amount<1e12 AND p_amount=round(p_amount,2)) OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 1 AND 4000 THEN
  RAISE EXCEPTION 'Invalid offer proposal' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-analysis:'||p_workspace::text||':'||analysis.lead_id::text,0));
 SELECT * INTO saved FROM public.offer_recommendations WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM p_workspace OR saved.deal_analysis_id IS DISTINCT FROM p_analysis
   OR saved.acquisition_case IS DISTINCT FROM p_case OR saved.target_offer IS DISTINCT FROM p_amount
   OR saved.proposal_note IS DISTINCT FROM p_note OR saved.proposed_by IS DISTINCT FROM auth.uid() THEN
   RAISE EXCEPTION 'Offer reference conflict' USING ERRCODE='23505'; END IF;
 ELSE
  case_output:=analysis.acquisition_outputs->'cases'->p_case;
  IF analysis.acquisition_status IS DISTINCT FROM 'calculated' OR analysis.property_id IS NULL
   OR analysis.acquisition_revision IS DISTINCT FROM (SELECT max(acquisition_revision) FROM public.deal_analyses WHERE workspace_id=p_workspace AND lead_id=analysis.lead_id)
   OR case_output->>'status' IS DISTINCT FROM 'calculated' OR jsonb_typeof(case_output->'proposed_offer_range') IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Current complete bound scenario with an offer range required' USING ERRCODE='55000'; END IF;
  ceiling:=(case_output#>>'{proposed_offer_range,high}')::numeric;
  IF ceiling IS NULL OR NOT(ceiling>0 AND ceiling<1e12) OR p_amount>ceiling THEN
   RAISE EXCEPTION 'Offer exceeds scenario ceiling' USING ERRCODE='22023'; END IF;
  INSERT INTO public.offer_recommendations(id,lead_id,deal_analysis_id,workspace_id,acquisition_case,proposed_by,proposal_note,target_offer,ceiling_offer)
  VALUES(p_id,analysis.lead_id,p_analysis,p_workspace,p_case,auth.uid(),p_note,p_amount,ceiling) RETURNING * INTO saved;
  INSERT INTO public.acquisition_offer_events(id,workspace_id,offer_id,sequence,status,actor_id,note)
  VALUES(p_id,p_workspace,p_id,1,'proposed',auth.uid(),p_note);
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_offer',p_id::text,'proposed',auth.uid()::text,
   jsonb_build_object('analysis_id',p_analysis,'case',p_case,'amount',p_amount),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'analysis_id',saved.deal_analysis_id,'amount',saved.target_offer,'binding_offer',false);
END $$;

CREATE OR REPLACE FUNCTION private.review_acquisition_offer(p_id uuid,p_workspace uuid,p_offer uuid,p_expected_sequence integer,p_status text,p_note text,p_review_notes jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE offer public.offer_recommendations%ROWTYPE; previous public.acquisition_offer_events%ROWTYPE;
 saved public.acquisition_offer_events%ROWTYPE; role_name text; active boolean; key text;
BEGIN
 role_name:=private.acquisition_role(p_workspace);
 IF coalesce(role_name,'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 IF p_status IS NULL OR p_status NOT IN ('amount_approved','rejected','withdrawn','approval_revoked') OR p_id IS NULL
  OR p_expected_sequence IS NULL OR p_expected_sequence<1 OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 1 AND 4000
  OR p_review_notes IS NULL OR jsonb_typeof(p_review_notes) IS DISTINCT FROM 'object' OR octet_length(p_review_notes::text)>32768 THEN
  RAISE EXCEPTION 'Invalid offer review' USING ERRCODE='22023'; END IF;
 IF p_status<>'withdrawn' AND role_name NOT IN ('owner','admin') THEN RAISE EXCEPTION 'Owner or administrator approval required' USING ERRCODE='42501'; END IF;
 SELECT * INTO offer FROM public.offer_recommendations WHERE id=p_offer AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Offer unavailable' USING ERRCODE='42501'; END IF;
 IF p_status='amount_approved' THEN PERFORM private.lock_acquisition_intake_analysis(offer.deal_analysis_id); END IF;
 -- Same lock as scenario reservation prevents a concurrent revision from racing approval.
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-analysis:'||p_workspace::text||':'||offer.lead_id::text,0));
 PERFORM 1 FROM public.offer_recommendations WHERE id=p_offer FOR UPDATE;
 SELECT * INTO saved FROM public.acquisition_offer_events WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM p_workspace OR saved.offer_id IS DISTINCT FROM p_offer
   OR saved.sequence IS DISTINCT FROM p_expected_sequence+1 OR saved.status IS DISTINCT FROM p_status
   OR saved.note IS DISTINCT FROM p_note OR saved.review_notes IS DISTINCT FROM p_review_notes OR saved.actor_id IS DISTINCT FROM auth.uid() THEN
   RAISE EXCEPTION 'Review reference conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT * INTO previous FROM public.acquisition_offer_events WHERE offer_id=p_offer ORDER BY sequence DESC LIMIT 1;
  IF previous.sequence IS DISTINCT FROM p_expected_sequence THEN RAISE EXCEPTION 'Offer state changed; refresh review' USING ERRCODE='40001'; END IF;
  IF NOT((previous.status='proposed' AND p_status IN ('amount_approved','rejected','withdrawn')) OR
         (previous.status='amount_approved' AND p_status='approval_revoked')) THEN
   RAISE EXCEPTION 'Offer review transition is not allowed' USING ERRCODE='55000'; END IF;
  IF p_status='amount_approved' THEN
   SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
   IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation approval required' USING ERRCODE='55000'; END IF;
   IF NOT EXISTS(SELECT 1 FROM public.deal_analyses a WHERE a.id=offer.deal_analysis_id AND a.workspace_id=p_workspace AND a.acquisition_status='calculated'
      AND a.acquisition_revision=(SELECT max(acquisition_revision) FROM public.deal_analyses WHERE workspace_id=p_workspace AND lead_id=offer.lead_id)) THEN
    RAISE EXCEPTION 'Underwriting changed; prepare a new proposal' USING ERRCODE='55000'; END IF;
   FOREACH key IN ARRAY ARRAY['title','liens','occupancy','valuation','repairs','financing','downside'] LOOP
    IF jsonb_typeof(p_review_notes->key) IS DISTINCT FROM 'string' OR length(trim(p_review_notes->>key)) NOT BETWEEN 1 AND 4000 THEN
     RAISE EXCEPTION 'Document each required diligence review' USING ERRCODE='22023'; END IF;
   END LOOP;
  END IF;
  INSERT INTO public.acquisition_offer_events(id,workspace_id,offer_id,sequence,status,actor_id,note,review_notes)
  VALUES(p_id,p_workspace,p_offer,p_expected_sequence+1,p_status,auth.uid(),p_note,p_review_notes) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_offer',p_offer::text,p_status,auth.uid()::text,
   jsonb_build_object('event_id',p_id,'sequence',saved.sequence,'analysis_id',offer.deal_analysis_id,'amount',offer.target_offer),p_workspace);
 END IF;
 RETURN jsonb_build_object('event_id',saved.id,'offer_id',saved.offer_id,'sequence',saved.sequence,'status',saved.status,
  'binding_offer',false,'transmission_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION private.acquisition_offer_review_state(p_workspace uuid,p_offer uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE offer public.offer_recommendations%ROWTYPE; event public.acquisition_offer_events%ROWTYPE;
 analysis public.deal_analyses%ROWTYPE; current_revision integer; caller_role text; active boolean;
 blockers text[]:=ARRAY[]::text[]; actions text[]:=ARRAY[]::text[]; current_analysis boolean;
BEGIN
 caller_role:=private.acquisition_role(p_workspace);
 IF coalesce(caller_role,'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO offer FROM public.offer_recommendations WHERE id=p_offer AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Offer unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO event FROM public.acquisition_offer_events WHERE offer_id=p_offer ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO analysis FROM public.deal_analyses WHERE id=offer.deal_analysis_id AND workspace_id=p_workspace AND lead_id=offer.lead_id;
 SELECT max(acquisition_revision) INTO current_revision FROM public.deal_analyses WHERE workspace_id=p_workspace AND lead_id=offer.lead_id;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 current_analysis:=coalesce(analysis.acquisition_status='calculated' AND analysis.acquisition_revision=current_revision AND analysis.property_id IS NOT NULL,false);
 IF NOT private.acquisition_intake_analysis_valid(offer.deal_analysis_id) THEN
  current_analysis:=false; blockers:=array_append(blockers,'INTAKE_QUALIFICATION_CHANGED');
 END IF;
 IF NOT current_analysis THEN blockers:=array_append(blockers,'UNDERWRITING_CHANGED_OR_UNAVAILABLE'); END IF;
 IF active IS DISTINCT FROM true THEN blockers:=array_append(blockers,'ACQUISITION_ACTIVATION_DISABLED'); END IF;
 IF event.status IS DISTINCT FROM 'amount_approved' THEN blockers:=array_append(blockers,'AMOUNT_NOT_APPROVED');
 ELSE
  IF NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
    WHERE m.workspace_id=p_workspace AND m.user_id=event.actor_id AND m.status='active' AND m.role IN ('owner','admin')
     AND p.status='approved' AND m.updated_at<=event.created_at) THEN
   blockers:=array_append(blockers,'APPROVER_AUTHORITY_CHANGED');
  END IF;
 END IF;
 IF event.status='proposed' THEN
  actions:=array_append(actions,'withdrawn');
  IF caller_role IN ('owner','admin') THEN
   actions:=array_append(actions,'rejected');
   IF active AND current_analysis THEN actions:=array_append(actions,'amount_approved'); END IF;
  END IF;
 ELSIF event.status='amount_approved' AND caller_role IN ('owner','admin') THEN actions:=array_append(actions,'approval_revoked');
 END IF;
 RETURN jsonb_build_object('offer_id',offer.id,'workspace_id',p_workspace,'lead_id',offer.lead_id,'property_id',analysis.property_id,
  'analysis_id',offer.deal_analysis_id,'analysis_revision',analysis.acquisition_revision,'latest_analysis_revision',current_revision,
  'case',offer.acquisition_case,'amount',offer.target_offer,'ceiling',offer.ceiling_offer,'proposal_note',offer.proposal_note,
  'proposed_at',offer.generated_at,'latest_event_id',event.id,'sequence',event.sequence,'historical_status',event.status,
  'reviewed_by',CASE WHEN event.status='amount_approved' THEN event.actor_id ELSE NULL END,
  'reviewed_at',CASE WHEN event.status='amount_approved' THEN event.created_at ELSE NULL END,
  'amount_approval_current',cardinality(blockers)=0,'amount_review_blockers',to_jsonb(blockers),'available_review_actions',to_jsonb(actions),
  'binding_offer',false,'transmission_authorized',false,'execution_authorization',NULL,
  'transmission_blockers',jsonb_build_array('FINAL_DOCUMENT_APPROVAL_REQUIRED','APPROVAL_FRESHNESS_POLICY_REQUIRED','FRESH_OUTREACH_AUTHORIZATION_REQUIRED'),
  'checked_at',statement_timestamp());
END $$;
CREATE FUNCTION private.acquisition_intake_analysis_state(p_workspace uuid,p_analysis uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE context public.acquisition_analysis_intakes%ROWTYPE;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') OR NOT EXISTS(
  SELECT 1 FROM public.deal_analyses WHERE workspace_id=p_workspace AND id=p_analysis) THEN
  RAISE EXCEPTION 'Workspace analysis access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO context FROM public.acquisition_analysis_intakes WHERE workspace_id=p_workspace AND analysis_id=p_analysis;
 RETURN jsonb_build_object('analysis_id',p_analysis,'has_intake',context.analysis_id IS NOT NULL,'intake_id',context.intake_id,
  'assessment_id',context.assessment_id,'qualification_current',private.acquisition_intake_analysis_valid(p_analysis));
END $$;
CREATE FUNCTION public.acquisition_intake_analysis_state(p_workspace uuid,p_analysis uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_intake_analysis_state(p_workspace,p_analysis) $$;
REVOKE ALL ON FUNCTION private.acquisition_intake_analysis_state(uuid,uuid),public.acquisition_intake_analysis_state(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_intake_analysis_state(uuid,uuid),public.acquisition_intake_analysis_state(uuid,uuid) TO authenticated;

COMMIT;
