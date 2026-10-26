-- No legacy records are automatically reassigned. Scoped access uses canonical
-- lead/property IDs, not copies. Caller enrollment remains behind release gates.
BEGIN;
ALTER TABLE public.profiles ADD COLUMN acquisition_only boolean NOT NULL DEFAULT false;

CREATE TABLE public.workspace_leads (
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 lead_id uuid NOT NULL REFERENCES public.leads(id),
 property_id uuid REFERENCES wholesale_ingest.properties(id),
 assigned_user_id uuid,
 bound_by uuid NOT NULL REFERENCES public.profiles(id),
 bound_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,lead_id),
 UNIQUE(lead_id),
 UNIQUE(property_id),
 FOREIGN KEY(workspace_id,assigned_user_id) REFERENCES public.workspace_memberships(workspace_id,user_id)
);
CREATE INDEX workspace_leads_assignment_idx ON public.workspace_leads(workspace_id,assigned_user_id,lead_id);
ALTER TABLE public.workspace_leads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.workspace_leads FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.workspace_leads TO authenticated,service_role;

CREATE FUNCTION private.acquisition_legacy_access() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.profiles WHERE id=auth.uid() AND status='approved' AND NOT acquisition_only);
$$;
REVOKE ALL ON FUNCTION private.acquisition_legacy_access() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_legacy_access() TO authenticated;

CREATE FUNCTION private.acquisition_can_read_lead(p_lead uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.workspace_leads b WHERE b.lead_id=p_lead
  AND private.acquisition_role(b.workspace_id) IN ('owner','admin','operator'));
$$;
REVOKE ALL ON FUNCTION private.acquisition_can_read_lead(uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_can_read_lead(uuid) TO authenticated;

CREATE FUNCTION private.acquisition_lead_is_bound(p_lead uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=p_lead);
$$;
REVOKE ALL ON FUNCTION private.acquisition_lead_is_bound(uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_lead_is_bound(uuid) TO authenticated;

CREATE POLICY workspace_leads_read ON public.workspace_leads FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

-- Close inherited shared-table access for acquisition-only identities. Existing
-- permissive/approved policies remain in place and cannot OR around these rules.
DO $$ DECLARE t record;
BEGIN
 FOR t IN SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname IN ('public','wholesale_ingest') AND c.relkind IN ('r','p')
  AND NOT (n.nspname='public' AND c.relname IN ('profiles','workspaces','workspace_memberships','workspace_leads','leads','audit_logs'))
 LOOP
  EXECUTE format('CREATE POLICY acquisition_legacy_boundary ON %I.%I AS RESTRICTIVE FOR ALL TO authenticated USING ((SELECT private.acquisition_legacy_access())) WITH CHECK ((SELECT private.acquisition_legacy_access()))',t.nspname,t.relname);
 END LOOP;
END $$;
CREATE POLICY acquisition_lead_read ON public.leads AS RESTRICTIVE FOR SELECT TO authenticated
 USING ((NOT private.acquisition_lead_is_bound(id) AND private.acquisition_legacy_access()) OR private.acquisition_can_read_lead(id));
CREATE POLICY acquisition_lead_insert ON public.leads AS RESTRICTIVE FOR INSERT TO authenticated
 WITH CHECK (NOT private.acquisition_lead_is_bound(id) AND private.acquisition_legacy_access());
CREATE POLICY acquisition_lead_update ON public.leads AS RESTRICTIVE FOR UPDATE TO authenticated
 USING (NOT private.acquisition_lead_is_bound(id) AND private.acquisition_legacy_access())
 WITH CHECK (NOT private.acquisition_lead_is_bound(id) AND private.acquisition_legacy_access());
CREATE POLICY acquisition_lead_delete ON public.leads AS RESTRICTIVE FOR DELETE TO authenticated
 USING (NOT private.acquisition_lead_is_bound(id) AND private.acquisition_legacy_access());
CREATE POLICY acquisition_audit_legacy_boundary ON public.audit_logs AS RESTRICTIVE FOR SELECT TO authenticated
 USING (workspace_id IS NOT NULL OR private.acquisition_legacy_access());

-- Sticky restriction: revoking/demoting a membership never restores legacy CRM
-- access. Platform admin accounts cannot be enrolled as limited callers.
CREATE FUNCTION private.acquisition_restrict_account() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.role IN ('acquisition_caller','agency_manager') AND EXISTS(
  SELECT 1 FROM public.profiles WHERE id=NEW.user_id AND role='admin'
 ) THEN RAISE EXCEPTION 'Use a limited non-administrator account' USING ERRCODE='22023'; END IF;
 IF NEW.role<>'owner' THEN
  UPDATE public.profiles SET acquisition_only=true WHERE id=NEW.user_id;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_restrict_account() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_restrict_account AFTER INSERT OR UPDATE ON public.workspace_memberships
 FOR EACH ROW EXECUTE FUNCTION private.acquisition_restrict_account();
-- Cover memberships created after the foundation migration but before this one.
-- Abort rather than leaving an existing platform-admin caller able to escape.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
  WHERE m.role IN ('acquisition_caller','agency_manager') AND p.role='admin') THEN
  RAISE EXCEPTION 'Separate existing platform administrator and limited caller accounts before upgrading';
 END IF;
END $$;
UPDATE public.profiles p SET acquisition_only=true WHERE EXISTS(
 SELECT 1 FROM public.workspace_memberships m WHERE m.user_id=p.id AND m.role<>'owner'
);

CREATE FUNCTION private.bind_acquisition_lead(p_workspace uuid,p_lead uuid,p_property uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.workspace_leads%ROWTYPE;
BEGIN
 IF private.acquisition_role(p_workspace) IS DISTINCT FROM 'owner' OR NOT EXISTS(
  SELECT 1 FROM public.profiles WHERE id=auth.uid() AND role='admin' AND NOT acquisition_only
 ) THEN RAISE EXCEPTION 'Legacy administrator and workspace owner required' USING ERRCODE='42501'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('acquisition-lead:'||p_lead,0));
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead) THEN
  RAISE EXCEPTION 'Lead unavailable' USING ERRCODE='22023'; END IF;
 IF p_property IS NOT NULL AND NOT EXISTS(
  SELECT 1 FROM wholesale_ingest.properties WHERE id=p_property AND lead_id=p_lead
 ) THEN RAISE EXCEPTION 'Verified property-to-lead association required' USING ERRCODE='22023'; END IF;
 SELECT * INTO saved FROM public.workspace_leads WHERE lead_id=p_lead;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.property_id IS DISTINCT FROM p_property THEN
   RAISE EXCEPTION 'Lead binding conflicts with existing ownership' USING ERRCODE='23505';
  END IF;
  RETURN to_jsonb(saved);
 END IF;
 INSERT INTO public.workspace_leads(workspace_id,lead_id,property_id,bound_by)
 VALUES(p_workspace,p_lead,p_property,auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_lead',p_lead::text,'bound',auth.uid()::text,to_jsonb(saved),p_workspace);
 RETURN to_jsonb(saved);
END $$;

CREATE FUNCTION private.assign_acquisition_lead(p_workspace uuid,p_lead uuid,p_user uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.workspace_leads%ROWTYPE; previous public.workspace_leads%ROWTYPE;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Workspace administrator required' USING ERRCODE='42501'; END IF;
 IF p_user IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
  WHERE m.workspace_id=p_workspace AND m.user_id=p_user AND m.status='active' AND p.status='approved') THEN
  RAISE EXCEPTION 'Active workspace member required' USING ERRCODE='22023'; END IF;
 SELECT * INTO previous FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Lead unavailable' USING ERRCODE='42501'; END IF;
 IF previous.assigned_user_id IS NOT DISTINCT FROM p_user THEN RETURN to_jsonb(previous); END IF;
 UPDATE public.workspace_leads SET assigned_user_id=p_user WHERE workspace_id=p_workspace AND lead_id=p_lead RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,old_value,new_value,workspace_id)
 VALUES('acquisition_lead',p_lead::text,'assigned',auth.uid()::text,to_jsonb(previous),to_jsonb(saved),p_workspace);
 RETURN to_jsonb(saved);
END $$;

CREATE FUNCTION private.list_acquisition_leads(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE actor_role text;
BEGIN
 actor_role:=private.acquisition_role(p_workspace);
 IF actor_role IS NULL THEN RAISE EXCEPTION 'Workspace membership required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Invalid page size' USING ERRCODE='22023'; END IF;
 RETURN coalesce((SELECT jsonb_agg(to_jsonb(item) ORDER BY item.lead_id) FROM (
  SELECT b.lead_id,b.property_id,b.assigned_user_id,l.property_address,l.city,l.state,l.zip_code,
   l.property_type,l.sqft,l.status,l.total_score,l.motivation_tag
  FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
  WHERE b.workspace_id=p_workspace AND (p_after IS NULL OR b.lead_id>p_after)
   AND (actor_role IN ('owner','admin','operator') OR b.assigned_user_id=auth.uid())
  ORDER BY b.lead_id LIMIT p_limit
 ) item),'[]'::jsonb);
END $$;

REVOKE ALL ON FUNCTION private.bind_acquisition_lead(uuid,uuid,uuid),
 private.assign_acquisition_lead(uuid,uuid,uuid),private.list_acquisition_leads(uuid,uuid,integer)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.bind_acquisition_lead(uuid,uuid,uuid),
 private.assign_acquisition_lead(uuid,uuid,uuid),private.list_acquisition_leads(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.bind_acquisition_lead(p_workspace uuid,p_lead uuid,p_property uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.bind_acquisition_lead(p_workspace,p_lead,p_property) $$;
CREATE FUNCTION public.assign_acquisition_lead(p_workspace uuid,p_lead uuid,p_user uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.assign_acquisition_lead(p_workspace,p_lead,p_user) $$;
CREATE FUNCTION public.list_acquisition_leads(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.list_acquisition_leads(p_workspace,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION public.bind_acquisition_lead(uuid,uuid,uuid),
 public.assign_acquisition_lead(uuid,uuid,uuid),public.list_acquisition_leads(uuid,uuid,integer)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.bind_acquisition_lead(uuid,uuid,uuid),
 public.assign_acquisition_lead(uuid,uuid,uuid),public.list_acquisition_leads(uuid,uuid,integer) TO authenticated;
COMMIT;
