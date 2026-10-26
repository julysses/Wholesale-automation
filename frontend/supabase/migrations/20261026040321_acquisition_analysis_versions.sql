-- Reuse deal_analyses. New inputs are immutable; only the server calculator can
-- finalize outputs. No current lead MAO or offer is selected automatically.
BEGIN;
ALTER TABLE public.deal_analyses
 ADD COLUMN workspace_id uuid,
 ADD COLUMN property_id uuid,
 ADD COLUMN acquisition_revision integer,
 ADD COLUMN acquisition_strategy text,
 ADD COLUMN calculation_version text,
 ADD COLUMN acquisition_inputs jsonb,
 ADD COLUMN acquisition_outputs jsonb,
 ADD COLUMN acquisition_status text,
 ADD CONSTRAINT acquisition_analysis_binding FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 ADD CONSTRAINT acquisition_analysis_property FOREIGN KEY(workspace_id,lead_id,property_id) REFERENCES public.workspace_leads(workspace_id,lead_id,property_id),
 ADD CONSTRAINT acquisition_analysis_revision_unique UNIQUE(workspace_id,lead_id,acquisition_revision),
 ADD CONSTRAINT acquisition_analysis_shape CHECK(
  (workspace_id IS NULL AND acquisition_revision IS NULL AND acquisition_strategy IS NULL AND calculation_version IS NULL
   AND acquisition_inputs IS NULL AND acquisition_outputs IS NULL AND acquisition_status IS NULL AND property_id IS NULL)
  OR (workspace_id IS NOT NULL AND lead_id IS NOT NULL AND created_by IS NOT NULL AND acquisition_revision>0
   AND acquisition_revision IS NOT NULL AND acquisition_strategy IN ('fix_and_flip','rental','development','wholesale')
   AND acquisition_strategy IS NOT NULL AND calculation_version='acquisition-underwriting-v1' AND calculation_version IS NOT NULL
   AND jsonb_typeof(acquisition_inputs)='object' AND acquisition_inputs IS NOT NULL
   AND acquisition_status IN ('pending','calculated','incomplete','invalid') AND acquisition_status IS NOT NULL
   AND ((acquisition_status='pending' AND acquisition_outputs IS NULL) OR
        (acquisition_status<>'pending' AND jsonb_typeof(acquisition_outputs)='object' AND acquisition_outputs IS NOT NULL)))) ;
CREATE INDEX acquisition_analysis_history_idx ON public.deal_analyses(workspace_id,lead_id,acquisition_revision DESC) WHERE workspace_id IS NOT NULL;
REVOKE TRUNCATE ON public.deal_analyses FROM PUBLIC,anon,authenticated,service_role;
CREATE POLICY acquisition_analysis_workspace_read ON public.deal_analyses AS RESTRICTIVE FOR SELECT TO authenticated
 USING(workspace_id IS NULL OR private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE TABLE private.acquisition_analysis_jobs (
 analysis_id uuid PRIMARY KEY REFERENCES public.deal_analyses(id),
 session_id uuid NOT NULL, -- Retain provenance without blocking Auth session deletion.
 input_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE private.acquisition_analysis_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_analysis_jobs FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.sync_deal_to_lead()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 -- Applies to historic/legacy analysis writers as well as new acquisition rows.
 IF NEW.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=NEW.lead_id) THEN RETURN NEW; END IF;
 UPDATE public.leads SET estimated_arv=NEW.arv_low, mao=NEW.mao,
 estimated_repairs=coalesce(NEW.repair_cost_mid,NEW.repair_cost_high,estimated_repairs)
 WHERE id=NEW.lead_id;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.sync_deal_to_lead() FROM PUBLIC,anon,authenticated;

CREATE FUNCTION private.reserve_acquisition_analysis(p_id uuid,p_workspace uuid,p_lead uuid,p_inputs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.deal_analyses%ROWTYPE; binding public.workspace_leads%ROWTYPE; revision integer; strategy text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace underwriting access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO binding FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=p_lead;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace lead unavailable' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_inputs IS NULL OR jsonb_typeof(p_inputs) IS DISTINCT FROM 'object' OR octet_length(p_inputs::text)>131072
 OR jsonb_typeof(p_inputs->'cases') IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'Invalid underwriting request' USING ERRCODE='22023'; END IF;
 IF (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_inputs->'cases') key) IS DISTINCT FROM ARRAY['base','downside','upside'] THEN
  RAISE EXCEPTION 'Three explicit cases required' USING ERRCODE='22023'; END IF;
 strategy:=p_inputs#>>'{cases,base,strategy}';
 IF strategy IS NULL OR strategy NOT IN ('fix_and_flip','rental','development','wholesale') OR
 p_inputs#>>'{cases,downside,strategy}' IS DISTINCT FROM strategy OR p_inputs#>>'{cases,upside,strategy}' IS DISTINCT FROM strategy THEN
  RAISE EXCEPTION 'Consistent acquisition strategy required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('acquisition-analysis:'||p_workspace::text||':'||p_lead::text,0));
 SELECT * INTO saved FROM public.deal_analyses WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM p_workspace OR saved.lead_id IS DISTINCT FROM p_lead
   OR saved.created_by IS DISTINCT FROM auth.uid() OR saved.acquisition_inputs IS DISTINCT FROM p_inputs THEN
   RAISE EXCEPTION 'Analysis request identity conflict' USING ERRCODE='23505'; END IF;
 ELSE
  SELECT coalesce(max(acquisition_revision),0)+1 INTO revision FROM public.deal_analyses WHERE workspace_id=p_workspace AND lead_id=p_lead;
  INSERT INTO public.deal_analyses(id,lead_id,created_by,workspace_id,property_id,acquisition_revision,acquisition_strategy,
   calculation_version,acquisition_inputs,acquisition_status,assignment_fee,investor_buy_ratio,is_viable,summary)
  VALUES(p_id,p_lead,auth.uid(),p_workspace,binding.property_id,revision,strategy,'acquisition-underwriting-v1',p_inputs,'pending',
   NULL,NULL,NULL,'Acquisition scenario request; not an approved offer') RETURNING * INTO saved;
  INSERT INTO private.acquisition_analysis_jobs(analysis_id,session_id,input_hash)
  VALUES(p_id,(auth.jwt()->>'session_id')::uuid,encode(sha256(convert_to(p_inputs::text,'UTF8')),'hex'));
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_analysis',p_id::text,'requested',auth.uid()::text,
   jsonb_build_object('revision',revision,'strategy',strategy,'calculation_version',saved.calculation_version),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'lead_id',saved.lead_id,
  'property_id',saved.property_id,'revision',saved.acquisition_revision,'status',saved.acquisition_status,'calculation_version',saved.calculation_version);
END $$;

CREATE FUNCTION private.acquisition_calculation_actor_valid(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.deal_analyses a JOIN private.acquisition_analysis_jobs j ON j.analysis_id=a.id
  JOIN public.workspaces w ON w.id=a.workspace_id JOIN public.workspace_memberships m ON m.workspace_id=a.workspace_id AND m.user_id=a.created_by
  JOIN public.profiles p ON p.id=a.created_by JOIN auth.sessions s ON s.id=j.session_id AND s.user_id=a.created_by
  WHERE a.id=p_id AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin','operator') AND p.status='approved'
   AND (s.not_after IS NULL OR s.not_after>now()) AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled));
$$;
REVOKE ALL ON FUNCTION private.acquisition_calculation_actor_valid(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.read_acquisition_calculation(p_id uuid,p_workspace uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.deal_analyses%ROWTYPE;
BEGIN
 SELECT * INTO saved FROM public.deal_analyses WHERE id=p_id AND workspace_id=p_workspace;
 IF NOT FOUND OR NOT private.acquisition_calculation_actor_valid(p_id) THEN
  RAISE EXCEPTION 'Analysis calculation is not authorized' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'inputs',saved.acquisition_inputs,
  'input_hash',(SELECT input_hash FROM private.acquisition_analysis_jobs WHERE analysis_id=p_id),
  'calculation_version',saved.calculation_version,'status',saved.acquisition_status);
END $$;

CREATE FUNCTION private.complete_acquisition_calculation(p_id uuid,p_workspace uuid,p_input_hash text,p_outputs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.deal_analyses%ROWTYPE; output jsonb; result_status text;
BEGIN
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

CREATE FUNCTION private.protect_acquisition_analysis() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; function_owner text;
BEGIN
 scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id) ELSE NEW.workspace_id IS NOT NULL OR
  EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=NEW.lead_id) END;
 IF TG_OP='UPDATE' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL OR
  EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id); END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Acquisition analysis history is immutable' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.complete_acquisition_calculation(uuid,uuid,text,jsonb)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use reviewed acquisition analysis functions' USING ERRCODE='42501'; END IF;
 IF TG_OP='UPDATE' AND OLD.workspace_id IS NOT NULL THEN
  IF OLD.acquisition_status<>'pending' OR NEW.acquisition_status NOT IN ('calculated','incomplete','invalid')
   OR NEW.acquisition_outputs IS NULL OR
   (to_jsonb(NEW)-ARRAY['acquisition_outputs','acquisition_status']) IS DISTINCT FROM
   (to_jsonb(OLD)-ARRAY['acquisition_outputs','acquisition_status']) THEN
   RAISE EXCEPTION 'Acquisition analysis history is immutable' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_analysis() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_analysis_protected BEFORE INSERT OR UPDATE OR DELETE ON public.deal_analyses
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_analysis();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.deal_analyses
 FOR EACH ROW WHEN(NEW.workspace_id IS NOT NULL) EXECUTE FUNCTION private.require_acquisition_activation();

REVOKE ALL ON FUNCTION private.reserve_acquisition_analysis(uuid,uuid,uuid,jsonb),
 private.read_acquisition_calculation(uuid,uuid),private.complete_acquisition_calculation(uuid,uuid,text,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.reserve_acquisition_analysis(uuid,uuid,uuid,jsonb) TO authenticated;
GRANT EXECUTE ON FUNCTION private.read_acquisition_calculation(uuid,uuid),private.complete_acquisition_calculation(uuid,uuid,text,jsonb) TO service_role;
CREATE FUNCTION public.reserve_acquisition_analysis(p_id uuid,p_workspace uuid,p_lead uuid,p_inputs jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.reserve_acquisition_analysis(p_id,p_workspace,p_lead,p_inputs) $$;
CREATE FUNCTION public.read_acquisition_calculation(p_id uuid,p_workspace uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.read_acquisition_calculation(p_id,p_workspace) $$;
CREATE FUNCTION public.complete_acquisition_calculation(p_id uuid,p_workspace uuid,p_input_hash text,p_outputs jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.complete_acquisition_calculation(p_id,p_workspace,p_input_hash,p_outputs) $$;
REVOKE ALL ON FUNCTION public.reserve_acquisition_analysis(uuid,uuid,uuid,jsonb),
 public.read_acquisition_calculation(uuid,uuid),public.complete_acquisition_calculation(uuid,uuid,text,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_acquisition_analysis(uuid,uuid,uuid,jsonb) TO authenticated;
GRANT EXECUTE ON FUNCTION public.read_acquisition_calculation(uuid,uuid),public.complete_acquisition_calculation(uuid,uuid,text,jsonb) TO service_role;
COMMIT;
