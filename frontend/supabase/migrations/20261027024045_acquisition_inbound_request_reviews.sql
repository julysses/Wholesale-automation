-- Append-only operator decisions; never mutate request evidence or authorize outreach.
BEGIN;
ALTER TABLE public.tasks ADD CONSTRAINT acquisition_task_workspace_identity UNIQUE(workspace_id,id);
CREATE TABLE public.acquisition_inbound_request_reviews (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, task_id uuid NOT NULL,
 sequence integer NOT NULL CHECK(sequence>0), request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 status text NOT NULL CHECK(status IN ('unassigned','assigned','on_hold','review_complete')),
 assigned_user_id uuid REFERENCES public.profiles(id), assignee_membership_updated_at timestamptz,
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), actor_membership_updated_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,task_id,sequence),
 FOREIGN KEY(workspace_id,task_id) REFERENCES public.tasks(workspace_id,id),
 CHECK((status='unassigned' AND assigned_user_id IS NULL AND assignee_membership_updated_at IS NULL)
  OR (status<>'unassigned' AND assigned_user_id IS NOT NULL AND assignee_membership_updated_at IS NOT NULL))
);
ALTER TABLE public.acquisition_inbound_request_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_inbound_request_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_inbound_request_reviews TO authenticated;
CREATE POLICY inbound_request_review_read ON public.acquisition_inbound_request_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER inbound_request_review_immutable BEFORE UPDATE OR DELETE ON public.acquisition_inbound_request_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_inbound_request_state(p_workspace uuid,p_task uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE task public.tasks%ROWTYPE; latest public.acquisition_inbound_request_reviews%ROWTYPE;
 request_current boolean; review_current boolean:=false; active boolean;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Inbound review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO task FROM public.tasks WHERE workspace_id=p_workspace AND id=p_task;
 IF NOT FOUND THEN RAISE EXCEPTION 'Request unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_inbound_request_reviews WHERE workspace_id=p_workspace AND task_id=p_task ORDER BY sequence DESC LIMIT 1;
 request_current:=NOT EXISTS(SELECT 1 FROM public.tasks newer WHERE newer.workspace_id=p_workspace
  AND newer.acquisition_integration_id=task.acquisition_integration_id AND newer.acquisition_call_id=task.acquisition_call_id
  AND newer.acquisition_request_kind=task.acquisition_request_kind AND newer.acquisition_revision>task.acquisition_revision);
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 IF latest.id IS NOT NULL THEN
  review_current:=coalesce(active AND request_current AND latest.request_hash=task.acquisition_request_hash
   AND EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
    WHERE m.workspace_id=p_workspace AND m.user_id=latest.actor_id AND m.status='active' AND m.role IN ('owner','admin','operator')
     AND m.updated_at=latest.actor_membership_updated_at AND p.status='approved')
   AND (latest.assigned_user_id IS NULL OR EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
    WHERE m.workspace_id=p_workspace AND m.user_id=latest.assigned_user_id AND m.status='active' AND m.role IN ('owner','admin','operator')
     AND m.updated_at=latest.assignee_membership_updated_at AND p.status='approved')),false);
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'task_id',p_task,'request_hash',task.acquisition_request_hash,
  'sequence',coalesce(latest.sequence,0),'latest_review',CASE WHEN latest.id IS NULL THEN NULL ELSE to_jsonb(latest) END,
  'request_current',request_current,'review_current',review_current,
  'status',CASE WHEN NOT request_current THEN 'superseded' WHEN latest.id IS NULL THEN 'pending_review' WHEN NOT review_current THEN 'requires_review' ELSE latest.status END,
  'assigned_user_id',CASE WHEN review_current THEN latest.assigned_user_id ELSE NULL END,
  'execution_authorized',false,'contact_permission_granted',false,'checked_at',statement_timestamp());
END $$;

CREATE FUNCTION private.review_acquisition_inbound_request(p_id uuid,p_workspace uuid,p_task uuid,p_expected_sequence integer,
 p_request_hash text,p_status text,p_assignee uuid,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE task public.tasks%ROWTYPE; saved public.acquisition_inbound_request_reviews%ROWTYPE;
 actor_role text; actor_updated timestamptz; assignee_updated timestamptz; current_state jsonb; active boolean;
BEGIN
 actor_role:=private.acquisition_role(p_workspace);
 IF coalesce(actor_role,'') NOT IN ('owner','admin','operator') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Inbound reviewer with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_task IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence NOT BETWEEN 0 AND 999999999
  OR p_request_hash IS NULL OR p_request_hash !~ '^[0-9a-f]{64}$'
  OR p_status IS NULL OR p_status NOT IN ('unassigned','assigned','on_hold','review_complete')
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000
  OR ((p_status='unassigned') IS DISTINCT FROM (p_assignee IS NULL)) THEN
  RAISE EXCEPTION 'Documented request review required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,m.role INTO actor_updated,actor_role FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin','operator') AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('inbound-request-review:'||p_id::text,0));
 SELECT * INTO task FROM public.tasks WHERE workspace_id=p_workspace AND id=p_task;
 IF NOT FOUND THEN RAISE EXCEPTION 'Request unavailable' USING ERRCODE='42501'; END IF;
 -- Serialize review against newer tool submissions on the same call.
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||task.acquisition_integration_id::text||':'||task.acquisition_call_id,0));
 SELECT * INTO saved FROM public.acquisition_inbound_request_reviews WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.task_id,saved.sequence,saved.request_hash,saved.status,saved.assigned_user_id,saved.review_note,saved.actor_id)
   IS DISTINCT FROM ROW(p_workspace,p_task,p_expected_sequence+1,p_request_hash,p_status,p_assignee,p_note,auth.uid()) THEN
   RAISE EXCEPTION 'Review request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'sequence',saved.sequence,'duplicate',true,'execution_authorized',false);
 END IF;
 current_state:=private.acquisition_inbound_request_state(p_workspace,p_task);
 IF (current_state->>'sequence')::integer<>p_expected_sequence OR task.acquisition_request_hash<>p_request_hash
  OR (current_state->>'request_current')::boolean IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Request review changed' USING ERRCODE='40001'; END IF;
 IF actor_role='operator' AND ((p_assignee IS NOT NULL AND p_assignee<>auth.uid())
  OR (current_state->>'assigned_user_id' IS NOT NULL AND (current_state->>'assigned_user_id')::uuid<>auth.uid())
  OR (p_status='unassigned' AND current_state->>'assigned_user_id' IS NULL)) THEN
  RAISE EXCEPTION 'Operator may manage only their own assignment' USING ERRCODE='42501'; END IF;
 IF p_assignee IS NOT NULL THEN
  SELECT m.updated_at INTO assignee_updated FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   WHERE m.workspace_id=p_workspace AND m.user_id=p_assignee AND m.status='active' AND m.role IN ('owner','admin','operator')
    AND p.status='approved' FOR SHARE OF m,p;
  IF NOT FOUND THEN RAISE EXCEPTION 'Assignee unavailable' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_status IN ('on_hold','review_complete') AND ((current_state->>'review_current')::boolean IS DISTINCT FROM true
  OR current_state->>'status' NOT IN ('assigned','on_hold') OR (current_state->>'assigned_user_id')::uuid IS DISTINCT FROM p_assignee) THEN
  RAISE EXCEPTION 'Current assignment required for review outcome' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_inbound_request_reviews(id,workspace_id,task_id,sequence,request_hash,status,assigned_user_id,
  assignee_membership_updated_at,review_note,actor_id,actor_membership_updated_at)
 VALUES(p_id,p_workspace,p_task,p_expected_sequence+1,p_request_hash,p_status,p_assignee,assignee_updated,p_note,auth.uid(),actor_updated);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_inbound_request_review',p_task::text,p_status,auth.uid()::text,p_workspace,
  jsonb_build_object('review_id',p_id,'sequence',p_expected_sequence+1,'assigned_user_id',p_assignee,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',p_id,'sequence',p_expected_sequence+1,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_inbound_request_state(p_workspace uuid,p_task uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_inbound_request_state(p_workspace,p_task) $$;
CREATE FUNCTION public.review_acquisition_inbound_request(p_id uuid,p_workspace uuid,p_task uuid,p_expected_sequence integer,p_request_hash text,p_status text,p_assignee uuid,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.review_acquisition_inbound_request(p_id,p_workspace,p_task,p_expected_sequence,p_request_hash,p_status,p_assignee,p_note) $$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_request_state(uuid,uuid),public.acquisition_inbound_request_state(uuid,uuid),
 private.review_acquisition_inbound_request(uuid,uuid,uuid,integer,text,text,uuid,text),public.review_acquisition_inbound_request(uuid,uuid,uuid,integer,text,text,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inbound_request_state(uuid,uuid),public.acquisition_inbound_request_state(uuid,uuid),
 private.review_acquisition_inbound_request(uuid,uuid,uuid,integer,text,text,uuid,text),public.review_acquisition_inbound_request(uuid,uuid,uuid,integer,text,text,uuid,text) TO authenticated;
COMMIT;
