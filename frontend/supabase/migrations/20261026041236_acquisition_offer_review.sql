-- Internal offer amount review. No transmission or binding-document approval.
BEGIN;
ALTER TABLE public.deal_analyses ADD CONSTRAINT acquisition_analysis_identity UNIQUE(id,workspace_id,lead_id);
ALTER TABLE public.offer_recommendations
 ADD COLUMN workspace_id uuid,
 ADD COLUMN acquisition_case text,
 ADD COLUMN proposed_by uuid REFERENCES auth.users(id),
 ADD COLUMN proposal_note text,
 ADD CONSTRAINT acquisition_offer_identity UNIQUE(id,workspace_id),
 ADD CONSTRAINT acquisition_offer_analysis FOREIGN KEY(deal_analysis_id,workspace_id,lead_id)
  REFERENCES public.deal_analyses(id,workspace_id,lead_id),
 ADD CONSTRAINT acquisition_offer_shape CHECK(
  (workspace_id IS NULL AND acquisition_case IS NULL AND proposed_by IS NULL AND proposal_note IS NULL) OR
  (workspace_id IS NOT NULL AND deal_analysis_id IS NOT NULL AND lead_id IS NOT NULL AND proposed_by IS NOT NULL
   AND acquisition_case IS NOT NULL AND acquisition_case IN ('base','downside','upside')
   AND target_offer IS NOT NULL AND target_offer>0 AND target_offer<1e12 AND target_offer=round(target_offer,2)
   AND ceiling_offer IS NOT NULL AND target_offer<=ceiling_offer
   AND proposal_note IS NOT NULL AND length(trim(proposal_note)) BETWEEN 1 AND 4000));
REVOKE TRUNCATE ON public.offer_recommendations FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.acquisition_offer_access(p_lead uuid,p_analysis uuid,p_workspace uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE scopes uuid[];
BEGIN
 SELECT array_agg(DISTINCT workspace_id) INTO scopes FROM (
  SELECT b.workspace_id FROM public.workspace_leads b WHERE b.lead_id=p_lead
  UNION SELECT b.workspace_id FROM public.workspace_leads b JOIN public.deal_analyses a ON a.lead_id=b.lead_id WHERE a.id=p_analysis
  UNION SELECT a.workspace_id FROM public.deal_analyses a WHERE a.id=p_analysis AND a.workspace_id IS NOT NULL
  UNION SELECT p_workspace WHERE p_workspace IS NOT NULL
 ) parents;
 IF coalesce(cardinality(scopes),0)=0 THEN RETURN private.acquisition_legacy_access(); END IF;
 RETURN cardinality(scopes)=1 AND coalesce(private.acquisition_role(scopes[1]) IN ('owner','admin','operator'),false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_offer_access(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_offer_access(uuid,uuid,uuid) TO authenticated;
CREATE POLICY acquisition_offer_read ON public.offer_recommendations AS RESTRICTIVE FOR SELECT TO authenticated
 USING(private.acquisition_offer_access(lead_id,deal_analysis_id,workspace_id));

CREATE TABLE public.acquisition_offer_events (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 offer_id uuid NOT NULL,
 sequence integer NOT NULL CHECK(sequence>0),
 status text NOT NULL CHECK(status IN ('proposed','amount_approved','rejected','withdrawn','approval_revoked')),
 actor_id uuid NOT NULL REFERENCES auth.users(id),
 note text NOT NULL CHECK(length(trim(note)) BETWEEN 1 AND 4000),
 review_notes jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(review_notes)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(offer_id,sequence),
 FOREIGN KEY(offer_id,workspace_id) REFERENCES public.offer_recommendations(id,workspace_id)
);
ALTER TABLE public.acquisition_offer_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_offer_events FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_offer_events TO authenticated;
CREATE POLICY acquisition_offer_event_read ON public.acquisition_offer_events FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE FUNCTION private.protect_acquisition_offer() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; function_owner text;
BEGIN
 IF TG_TABLE_NAME='acquisition_offer_events' THEN scoped:=true;
 ELSE
  scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id)
   ELSE NEW.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=NEW.lead_id) END;
  IF TG_OP<>'DELETE' THEN scoped:=scoped OR EXISTS(SELECT 1 FROM public.deal_analyses a WHERE a.id=NEW.deal_analysis_id
   AND (a.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads b WHERE b.lead_id=a.lead_id))); END IF;
  IF TG_OP<>'INSERT' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id)
   OR EXISTS(SELECT 1 FROM public.deal_analyses a WHERE a.id=OLD.deal_analysis_id AND
    (a.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads b WHERE b.lead_id=a.lead_id))); END IF;
 END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Offer history is immutable' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.protect_acquisition_offer()'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use acquisition offer review functions' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_offer() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_offer_protected BEFORE INSERT OR UPDATE OR DELETE ON public.offer_recommendations
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_offer();
CREATE TRIGGER acquisition_offer_events_protected BEFORE INSERT OR UPDATE OR DELETE ON public.acquisition_offer_events
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_offer();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.offer_recommendations
 FOR EACH ROW WHEN(NEW.workspace_id IS NOT NULL) EXECUTE FUNCTION private.require_acquisition_activation();

CREATE FUNCTION private.propose_acquisition_offer(p_id uuid,p_workspace uuid,p_analysis uuid,p_case text,p_amount numeric,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE analysis public.deal_analyses%ROWTYPE; saved public.offer_recommendations%ROWTYPE; ceiling numeric; case_output jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO analysis FROM public.deal_analyses WHERE id=p_analysis AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace analysis unavailable' USING ERRCODE='42501'; END IF;
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

CREATE FUNCTION private.review_acquisition_offer(p_id uuid,p_workspace uuid,p_offer uuid,p_expected_sequence integer,p_status text,p_note text,p_review_notes jsonb)
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
REVOKE ALL ON FUNCTION private.propose_acquisition_offer(uuid,uuid,uuid,text,numeric,text),
 private.review_acquisition_offer(uuid,uuid,uuid,integer,text,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.propose_acquisition_offer(uuid,uuid,uuid,text,numeric,text),
 private.review_acquisition_offer(uuid,uuid,uuid,integer,text,text,jsonb) TO authenticated;
CREATE FUNCTION public.propose_acquisition_offer(p_id uuid,p_workspace uuid,p_analysis uuid,p_case text,p_amount numeric,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.propose_acquisition_offer(p_id,p_workspace,p_analysis,p_case,p_amount,p_note) $$;
CREATE FUNCTION public.review_acquisition_offer(p_id uuid,p_workspace uuid,p_offer uuid,p_expected_sequence integer,p_status text,p_note text,p_review_notes jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.review_acquisition_offer(p_id,p_workspace,p_offer,p_expected_sequence,p_status,p_note,p_review_notes) $$;
REVOKE ALL ON FUNCTION public.propose_acquisition_offer(uuid,uuid,uuid,text,numeric,text),
 public.review_acquisition_offer(uuid,uuid,uuid,integer,text,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.propose_acquisition_offer(uuid,uuid,uuid,text,numeric,text),
 public.review_acquisition_offer(uuid,uuid,uuid,integer,text,text,jsonb) TO authenticated;
COMMIT;
