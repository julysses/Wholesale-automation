-- Additive acquisition foundation. No legacy ownership backfill, scheduling,
-- provider call, or existing receipt/transport mutation. Apply only after approval.
BEGIN;

CREATE TABLE public.workspaces (
 id uuid PRIMARY KEY,
 name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 160),
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
 created_by uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.workspace_memberships (
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 user_id uuid NOT NULL REFERENCES public.profiles(id),
 role text NOT NULL CHECK (role IN ('owner','admin','operator','acquisition_caller','agency_manager')),
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id,user_id)
);
CREATE INDEX workspace_memberships_user_idx ON public.workspace_memberships(user_id,workspace_id);
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_memberships ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.workspaces,public.workspace_memberships FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.workspaces,public.workspace_memberships TO authenticated;

-- Reuse the existing audit ledger. Legacy rows and legacy append writers remain
-- valid. New acquisition events are immutable even through the service role.
ALTER TABLE public.audit_logs ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id);
CREATE INDEX audit_logs_workspace_time_idx ON public.audit_logs(workspace_id,occurred_at DESC);
REVOKE TRUNCATE ON public.audit_logs FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_session_valid() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS (
  SELECT 1 FROM auth.sessions s JOIN public.profiles p ON p.id=s.user_id
  WHERE p.id=auth.uid() AND p.status='approved'
   AND s.id::text=auth.jwt()->>'session_id'
   AND (s.not_after IS NULL OR s.not_after>now())
 );
$$;
REVOKE ALL ON FUNCTION private.acquisition_session_valid() FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_role(p_workspace uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT m.role FROM public.workspace_memberships m
 JOIN public.workspaces w ON w.id=m.workspace_id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid()
 AND m.status='active' AND w.status='active'
 AND private.acquisition_session_valid()
 AND (m.role NOT IN ('acquisition_caller','agency_manager') OR auth.jwt()->>'aal'='aal2');
$$;
REVOKE ALL ON FUNCTION private.acquisition_role(uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_role(uuid) TO authenticated;

CREATE POLICY workspace_member_read ON public.workspaces FOR SELECT TO authenticated
 USING (private.acquisition_role(id) IS NOT NULL);
CREATE POLICY membership_read ON public.workspace_memberships FOR SELECT TO authenticated
 USING (private.acquisition_role(workspace_id) IS NOT NULL AND
 (user_id=auth.uid() OR private.acquisition_role(workspace_id) IN ('owner','admin')));
CREATE POLICY acquisition_audit_read ON public.audit_logs AS RESTRICTIVE FOR SELECT TO authenticated
 USING (workspace_id IS NULL OR private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE FUNCTION private.protect_acquisition_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF OLD.workspace_id IS NOT NULL OR (TG_OP='UPDATE' AND NEW.workspace_id IS NOT NULL) THEN
  RAISE EXCEPTION 'Acquisition audit events are immutable' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_audit() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_audit BEFORE UPDATE OR DELETE ON public.audit_logs
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_audit();

CREATE FUNCTION private.create_acquisition_workspace(p_id uuid,p_name text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.workspaces%ROWTYPE;
BEGIN
 IF NOT private.acquisition_session_valid() OR NOT EXISTS (
  SELECT 1 FROM public.profiles WHERE id=auth.uid() AND role='admin' AND status='approved'
 ) THEN RAISE EXCEPTION 'Approved administrator session required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_name IS NULL OR length(btrim(p_name)) NOT BETWEEN 1 AND 160 THEN
  RAISE EXCEPTION 'Invalid workspace' USING ERRCODE='22023';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('acquisition-workspace:'||p_id,0));
 SELECT * INTO saved FROM public.workspaces WHERE id=p_id;
 IF FOUND THEN
  IF saved.created_by<>auth.uid() OR saved.name<>btrim(p_name)
   OR private.acquisition_role(p_id) IS DISTINCT FROM 'owner' THEN
   RAISE EXCEPTION 'Workspace creation conflicts with existing state' USING ERRCODE='42501';
  END IF;
  RETURN to_jsonb(saved);
 END IF;
 INSERT INTO public.workspaces(id,name,created_by) VALUES(p_id,btrim(p_name),auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.workspace_memberships(workspace_id,user_id,role) VALUES(p_id,auth.uid(),'owner');
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_workspace',p_id::text,'created',auth.uid()::text,to_jsonb(saved),p_id);
 RETURN to_jsonb(saved);
END $$;

CREATE FUNCTION private.set_acquisition_membership(p_workspace uuid,p_user uuid,p_role text,p_status text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE actor_role text; before_row public.workspace_memberships%ROWTYPE; saved public.workspace_memberships%ROWTYPE;
BEGIN
 -- Serialize membership administration, including last-owner protection.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('acquisition-workspace:'||p_workspace,0));
 actor_role:=private.acquisition_role(p_workspace);
 IF actor_role IS NULL OR actor_role NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Workspace administrator required' USING ERRCODE='42501';
 END IF;
 IF p_role IS NULL OR p_role NOT IN ('owner','admin','operator','acquisition_caller','agency_manager')
  OR p_status IS NULL OR p_status NOT IN ('active','revoked') THEN
  RAISE EXCEPTION 'Invalid membership' USING ERRCODE='22023';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_user AND (p_status='revoked' OR status='approved')) THEN
  RAISE EXCEPTION 'Approved target account required' USING ERRCODE='22023';
 END IF;
 SELECT * INTO before_row FROM public.workspace_memberships WHERE workspace_id=p_workspace AND user_id=p_user;
 IF actor_role<>'owner' AND (p_role IN ('owner','admin') OR before_row.role IN ('owner','admin')) THEN
  RAISE EXCEPTION 'Owner required to manage privileged membership' USING ERRCODE='42501';
 END IF;
 IF before_row.role='owner' AND before_row.status='active' AND (p_role<>'owner' OR p_status<>'active')
  AND NOT EXISTS(SELECT 1 FROM public.workspace_memberships WHERE workspace_id=p_workspace
   AND user_id<>p_user AND role='owner' AND status='active') THEN
  RAISE EXCEPTION 'Cannot remove the last owner' USING ERRCODE='22023';
 END IF;
 IF before_row.role=p_role AND before_row.status=p_status THEN RETURN to_jsonb(before_row); END IF;
 INSERT INTO public.workspace_memberships(workspace_id,user_id,role,status) VALUES(p_workspace,p_user,p_role,p_status)
 ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=excluded.role,status=excluded.status,updated_at=clock_timestamp()
 RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,old_value,new_value,workspace_id)
 VALUES('acquisition_membership',p_user::text,'membership_changed',auth.uid()::text,to_jsonb(before_row),to_jsonb(saved),p_workspace);
 RETURN to_jsonb(saved);
END $$;

-- Exposed RPC wrappers are SECURITY INVOKER. Authorization and all privileged
-- writes live in private; caller identity is derived from the verified JWT.
REVOKE ALL ON FUNCTION private.create_acquisition_workspace(uuid,text),
 private.set_acquisition_membership(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.create_acquisition_workspace(uuid,text),
 private.set_acquisition_membership(uuid,uuid,text,text) TO authenticated;
CREATE FUNCTION public.create_acquisition_workspace(p_id uuid,p_name text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.create_acquisition_workspace(p_id,p_name) $$;
CREATE FUNCTION public.set_acquisition_membership(p_workspace uuid,p_user uuid,p_role text,p_status text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.set_acquisition_membership(p_workspace,p_user,p_role,p_status) $$;
REVOKE ALL ON FUNCTION public.create_acquisition_workspace(uuid,text),
 public.set_acquisition_membership(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.create_acquisition_workspace(uuid,text),
 public.set_acquisition_membership(uuid,uuid,text,text) TO authenticated;
COMMIT;
