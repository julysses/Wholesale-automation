-- Internal purchase-path proposals under the canonical deal, never disposition
-- approval, marketing, assignment, contract amendment or closing authority.
-- Additive immutable child history; no legacy deal/buyer fields are rewritten.
-- Compensation: pause acquisition or withdraw a proposal through the RPC;
-- retain all plans and audits. Do not drop historical rows to roll back.
BEGIN;
CREATE TABLE public.acquisition_disposition_plans (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, contract_id uuid NOT NULL,
 contract_version integer NOT NULL CHECK(contract_version>0), sequence integer NOT NULL CHECK(sequence>0),
 status text NOT NULL CHECK(status IN ('proposed','withdrawn')),
 exit_type text NOT NULL CHECK(exit_type IN ('principal_acquisition','wholesale_assignment')),
 note text NOT NULL CHECK(length(note)<=4000 AND length(trim(note))>=20),
 execution_transition_id uuid NOT NULL, title_entry_id uuid NOT NULL,
 execution_status text GENERATED ALWAYS AS ('executed'::text) STORED,
 title_entry_status text GENERATED ALWAYS AS ('title_review'::text) STORED,
 original_plan_id uuid, original_plan_status text GENERATED ALWAYS AS (CASE WHEN status='withdrawn' THEN 'proposed'::text END) STORED,
 actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 actor_membership_updated_at timestamptz NOT NULL, request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK(isfinite(created_at)),
 CHECK((status='proposed' AND original_plan_id IS NULL) OR (status='withdrawn' AND original_plan_id IS NOT NULL AND original_plan_id<>id AND sequence>1)),
 UNIQUE(workspace_id,contract_id,contract_version,sequence),
 UNIQUE(workspace_id,contract_id,contract_version,id,status,exit_type,execution_transition_id,title_entry_id),
 FOREIGN KEY(workspace_id,contract_id,contract_version) REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 FOREIGN KEY(workspace_id,contract_id,contract_version,execution_transition_id,execution_status)
  REFERENCES public.acquisition_contract_transitions(workspace_id,contract_id,contract_version,id,recorded_status),
 FOREIGN KEY(workspace_id,contract_id,contract_version,title_entry_id,title_entry_status)
  REFERENCES public.acquisition_contract_transitions(workspace_id,contract_id,contract_version,id,recorded_status),
 FOREIGN KEY(workspace_id,contract_id,contract_version,original_plan_id,original_plan_status,exit_type,execution_transition_id,title_entry_id)
  REFERENCES public.acquisition_disposition_plans(workspace_id,contract_id,contract_version,id,status,exit_type,execution_transition_id,title_entry_id)
);
ALTER TABLE public.acquisition_disposition_plans ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_disposition_plans FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_disposition_plans TO authenticated;
CREATE POLICY acquisition_disposition_plan_read ON public.acquisition_disposition_plans FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin') AND auth.jwt()->>'aal'='aal2');
CREATE TRIGGER acquisition_disposition_plan_immutable BEFORE UPDATE OR DELETE ON public.acquisition_disposition_plans
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.record_disposition_plan(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_exit_type text,p_note text,p_original_plan uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE authority record; saved public.acquisition_disposition_plans%ROWTYPE; prior public.acquisition_disposition_plans%ROWTYPE;
 executed public.acquisition_contract_transitions%ROWTYPE; entered public.acquisition_contract_transitions%ROWTYPE;
 fingerprint text; stamped timestamptz; active boolean; seq integer; duplicate boolean:=false;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 2147483646
  OR p_status IS NULL OR p_status NOT IN ('proposed','withdrawn') OR p_exit_type IS NULL OR p_exit_type NOT IN ('principal_acquisition','wholesale_assignment')
  OR p_note IS NULL OR length(p_note)>4000 OR length(trim(p_note))<20
  OR (p_status='proposed' AND p_original_plan IS NOT NULL) OR (p_status='withdrawn' AND (p_original_plan IS NULL OR p_original_plan=p_id)) THEN
  RAISE EXCEPTION 'Exact internal purchase-path request required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('disposition-plan:'||p_id::text,0));
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_exit_type,p_note,p_original_plan,
  auth.uid(),auth.jwt()->>'session_id')::text,'UTF8')),'hex');
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Planning session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_disposition_plans WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Purchase-path request conflict' USING ERRCODE='23505'; END IF;
  duplicate:=true;
 ELSE
  SELECT * INTO prior FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
  seq:=coalesce(prior.sequence,0);
  IF seq<>p_expected_sequence THEN RAISE EXCEPTION 'Purchase-path history changed' USING ERRCODE='40001'; END IF;
  IF p_status='withdrawn' THEN
   IF prior.id IS DISTINCT FROM p_original_plan OR prior.status IS DISTINCT FROM 'proposed'
    OR prior.actor_id IS DISTINCT FROM auth.uid() OR prior.exit_type IS DISTINCT FROM p_exit_type THEN
    RAISE EXCEPTION 'Only the latest original personal proposal can be withdrawn' USING ERRCODE='55000'; END IF;
   executed.id:=prior.execution_transition_id; entered.id:=prior.title_entry_id;
  ELSE
   SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
   IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition paused' USING ERRCODE='55000'; END IF;
   IF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='title_review') THEN
    RAISE EXCEPTION 'Current title-review contract required for planning' USING ERRCODE='55000'; END IF;
   SELECT * INTO executed FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=2 AND previous_status='pending_signature' AND recorded_status='executed';
   SELECT * INTO entered FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
    AND contract_version=p_version AND sequence=3 AND previous_status='executed' AND recorded_status='title_review';
   IF executed.id IS NULL OR entered.id IS NULL OR executed.execution_review_id IS DISTINCT FROM entered.execution_review_id THEN
    RAISE EXCEPTION 'Recorded execution and title entry required' USING ERRCODE='55000'; END IF;
  END IF;
  stamped:=clock_timestamp();
  IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN
   RAISE EXCEPTION 'Planning session expired before save' USING ERRCODE='42501'; END IF;
  INSERT INTO public.acquisition_disposition_plans(id,workspace_id,contract_id,contract_version,sequence,status,exit_type,note,
   execution_transition_id,title_entry_id,original_plan_id,actor_id,session_id,actor_membership_updated_at,request_hash,created_at)
  VALUES(p_id,p_workspace,p_contract,p_version,seq+1,p_status,p_exit_type,p_note,executed.id,entered.id,p_original_plan,
   auth.uid(),(auth.jwt()->>'session_id')::uuid,authority.actor_updated,fingerprint,stamped) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
  VALUES('acquisition_disposition_plan',p_id::text,p_status,auth.uid()::text,p_workspace,jsonb_build_object('contract_id',p_contract,
   'contract_version',p_version,'sequence',saved.sequence,'exit_type',p_exit_type,'execution_transition_id',executed.id,
   'title_entry_id',entered.id,'original_plan_id',p_original_plan,'disposition_approved',false,'execution_authorized',false));
 END IF;
 RETURN jsonb_build_object('plan_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,
  'sequence',saved.sequence,'status',saved.status,'exit_type',saved.exit_type,'original_plan_id',saved.original_plan_id,
  'duplicate',duplicate,'plan_recorded',true,'disposition_approved',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_disposition_plan(uuid,uuid,uuid,integer,integer,text,text,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_disposition_plan(uuid,uuid,uuid,integer,integer,text,text,text,uuid) TO authenticated;
CREATE FUNCTION public.record_disposition_plan(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_expected_sequence integer,
 p_status text,p_exit_type text,p_note text,p_original_plan uuid) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.record_disposition_plan(p_id,p_workspace,p_contract,p_version,p_expected_sequence,p_status,p_exit_type,p_note,p_original_plan) $$;
REVOKE ALL ON FUNCTION public.record_disposition_plan(uuid,uuid,uuid,integer,integer,text,text,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_disposition_plan(uuid,uuid,uuid,integer,integer,text,text,text,uuid) TO authenticated;

CREATE FUNCTION private.disposition_plan_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE deal public.deals%ROWTYPE; latest public.acquisition_disposition_plans%ROWTYPE; readiness text; original jsonb; latest_json jsonb;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
   SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Purchase-path access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO deal FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract;
 SELECT * INTO latest FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
 IF coalesce(latest.sequence,0)=2147483647 THEN readiness:='history_limit_reached';
 ELSIF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN readiness:='paused';
 ELSIF deal.acquisition_version<>p_version OR deal.acquisition_status<>'title_review' OR NOT EXISTS(
  SELECT 1 FROM public.acquisition_contract_transitions executed JOIN public.acquisition_contract_transitions entered
   ON entered.workspace_id=executed.workspace_id AND entered.contract_id=executed.contract_id AND entered.contract_version=executed.contract_version
    AND entered.execution_review_id=executed.execution_review_id
   WHERE executed.workspace_id=p_workspace AND executed.contract_id=p_contract AND executed.contract_version=p_version
    AND executed.sequence=2 AND executed.recorded_status='executed' AND entered.sequence=3 AND entered.recorded_status='title_review') THEN readiness:='contract_unavailable';
 ELSE readiness:='ready_for_planning'; END IF;
 IF latest.id IS NOT NULL THEN
  latest_json:=jsonb_build_object('plan_id',latest.id,'sequence',latest.sequence,'status',latest.status,'exit_type',latest.exit_type,
   'note',latest.note,'original_plan_id',latest.original_plan_id,'created_at',latest.created_at);
  IF latest.sequence<2147483647 AND latest.status='proposed' AND latest.actor_id=auth.uid() THEN
   original:=jsonb_build_object('plan_id',latest.id,'exit_type',latest.exit_type,'expected_sequence',latest.sequence); END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'current_version',deal.acquisition_version,'current_status',deal.acquisition_status,'sequence',coalesce(latest.sequence,0),
  'readiness',readiness,'latest',latest_json,'withdrawal',original,'checked_at',statement_timestamp(),
  'disposition_approved',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.disposition_plan_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.disposition_plan_state(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.disposition_plan_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.disposition_plan_state(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.disposition_plan_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.disposition_plan_state(uuid,uuid,integer) TO authenticated;
COMMIT;
