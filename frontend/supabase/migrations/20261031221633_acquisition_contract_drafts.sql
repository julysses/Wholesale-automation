-- Draft records only. No signatures, title findings, assignment or distribution.
-- Compensation: keep acquisition activation disabled; preserve drafts/audit history.
BEGIN;
ALTER TABLE public.offer_recommendations ADD CONSTRAINT acquisition_offer_lead_identity UNIQUE(id,workspace_id,lead_id);
ALTER TABLE public.acquisition_owner_properties ADD CONSTRAINT acquisition_contract_seller_identity UNIQUE(id,workspace_id,lead_id,property_id);
ALTER TABLE public.deals
 ADD COLUMN workspace_id uuid,
 ADD COLUMN acquisition_status text,
 ADD COLUMN acquisition_version integer,
 ADD COLUMN acquisition_property_id uuid,
 ADD COLUMN acquisition_owner_relationship_id uuid,
 ADD COLUMN acquisition_offer_id uuid,
 ADD COLUMN acquisition_offer_sequence integer,
 ADD CONSTRAINT acquisition_deal_identity UNIQUE(id,workspace_id),
 ADD CONSTRAINT acquisition_deal_property FOREIGN KEY(workspace_id,lead_id,acquisition_property_id)
  REFERENCES public.workspace_leads(workspace_id,lead_id,property_id),
 ADD CONSTRAINT acquisition_deal_seller FOREIGN KEY(acquisition_owner_relationship_id,workspace_id,lead_id,acquisition_property_id)
  REFERENCES public.acquisition_owner_properties(id,workspace_id,lead_id,property_id),
 ADD CONSTRAINT acquisition_deal_offer FOREIGN KEY(acquisition_offer_id,workspace_id,lead_id)
  REFERENCES public.offer_recommendations(id,workspace_id,lead_id),
 ADD CONSTRAINT acquisition_deal_shape CHECK (
  (workspace_id IS NULL AND acquisition_status IS NULL AND acquisition_version IS NULL
   AND acquisition_property_id IS NULL AND acquisition_owner_relationship_id IS NULL
   AND acquisition_offer_id IS NULL AND acquisition_offer_sequence IS NULL) OR
  (workspace_id IS NOT NULL AND acquisition_status IS NOT NULL AND acquisition_status='draft'
   AND acquisition_version IS NOT NULL AND acquisition_version=1 AND acquisition_property_id IS NOT NULL
   AND acquisition_owner_relationship_id IS NOT NULL AND acquisition_offer_id IS NOT NULL
   AND acquisition_offer_sequence IS NOT NULL AND acquisition_offer_sequence>0
   AND stage='offer_made' AND contract_price IS NULL AND buyer_id IS NULL
   AND contract_date IS NULL AND closing_date IS NULL AND actual_close_date IS NULL
   AND psa_doc_url IS NULL AND assignment_doc_url IS NULL));
CREATE INDEX acquisition_deal_workspace_idx ON public.deals(workspace_id,id) WHERE workspace_id IS NOT NULL;
REVOKE TRUNCATE,TRIGGER ON public.deals FROM PUBLIC,anon,authenticated,service_role;
CREATE POLICY acquisition_contract_read ON public.deals AS RESTRICTIVE FOR SELECT TO authenticated
 USING(workspace_id IS NULL OR private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE TABLE public.acquisition_contract_versions (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 deal_id uuid NOT NULL,
 version integer NOT NULL CHECK(version=1),
 status text NOT NULL CHECK(status='draft'),
 request jsonb NOT NULL CHECK(jsonb_typeof(request)='object'),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(deal_id,version),
 FOREIGN KEY(deal_id,workspace_id) REFERENCES public.deals(id,workspace_id)
);
ALTER TABLE public.acquisition_contract_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contract_versions FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contract_versions TO authenticated;
CREATE POLICY acquisition_contract_version_read ON public.acquisition_contract_versions FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));

CREATE FUNCTION private.protect_acquisition_contract() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean:=false; function_owner text;
BEGIN
 IF TG_TABLE_NAME='acquisition_contract_versions' THEN scoped:=true;
 ELSE
  IF TG_OP<>'INSERT' THEN
   scoped:=OLD.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=OLD.lead_id);
  END IF;
  IF TG_OP<>'DELETE' THEN
   scoped:=scoped OR NEW.workspace_id IS NOT NULL OR EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=NEW.lead_id);
  END IF;
 END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Contract drafts and versions are immutable' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.protect_acquisition_contract()'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use controlled contract functions' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_contract() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_contract_protected BEFORE INSERT OR UPDATE OR DELETE ON public.deals
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_contract();
CREATE TRIGGER acquisition_contract_version_protected BEFORE INSERT OR UPDATE OR DELETE ON public.acquisition_contract_versions
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_contract();

CREATE FUNCTION private.create_acquisition_contract_draft(p_id uuid,p_workspace uuid,p_offer uuid,p_offer_sequence integer,p_relationship uuid,p_name text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE source public.offer_recommendations%ROWTYPE; seller public.acquisition_owner_properties%ROWTYPE;
 saved public.acquisition_contract_versions%ROWTYPE; deal public.deals%ROWTYPE;
 manifest jsonb; review jsonb; active boolean;
BEGIN
 IF p_id IS NULL OR p_workspace IS NULL OR p_offer IS NULL OR p_relationship IS NULL
 OR p_offer_sequence IS NULL OR p_offer_sequence<1 OR p_name IS NULL OR length(trim(p_name)) NOT BETWEEN 1 AND 500 THEN
  RAISE EXCEPTION 'Invalid draft request' USING ERRCODE='22023'; END IF;
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Workspace MFA session required' USING ERRCODE='42501'; END IF;
 SELECT * INTO source FROM public.offer_recommendations WHERE id=p_offer AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Offer unavailable' USING ERRCODE='42501'; END IF;
 -- Match existing CRM locks, then the existing underwriting/offer-review lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:'||p_id,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('deal-lead:'||source.lead_id,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-analysis:'||p_workspace::text||':'||source.lead_id::text,0));
 -- Pin authority and activation through commit; re-evaluate after every wait.
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace FOR SHARE;
 PERFORM 1 FROM public.profiles WHERE id=auth.uid() FOR SHARE;
 PERFORM 1 FROM public.workspace_memberships WHERE workspace_id=p_workspace AND user_id=auth.uid() FOR SHARE;
 PERFORM 1 FROM auth.sessions WHERE id::text=auth.jwt()->>'session_id' AND user_id=auth.uid() FOR SHARE;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator')
 OR NOT EXISTS(SELECT 1 FROM auth.sessions WHERE id::text=auth.jwt()->>'session_id' AND user_id=auth.uid()
  AND (not_after IS NULL OR not_after>clock_timestamp())) THEN
  RAISE EXCEPTION 'Current workspace session required' USING ERRCODE='42501'; END IF;
 manifest:=jsonb_build_object('workspace_id',p_workspace,'offer_id',p_offer,'offer_sequence',p_offer_sequence,
  'owner_relationship_id',p_relationship,'deal_name',trim(p_name));
 SELECT * INTO saved FROM public.acquisition_contract_versions WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id IS DISTINCT FROM p_workspace OR saved.actor_id IS DISTINCT FROM auth.uid() OR saved.request IS DISTINCT FROM manifest THEN
   RAISE EXCEPTION 'Draft request identity conflict' USING ERRCODE='23505'; END IF;
  -- Recover the original receipt even after approval/activation changed. This
  -- reports only the historical save, never current readiness or execution.
  RETURN jsonb_build_object('deal_id',saved.deal_id,'version',saved.version,'status',saved.status,'duplicate',true,'execution_authorized',false);
 END IF;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 IF EXISTS(SELECT 1 FROM public.deals WHERE id=p_id OR (lead_id=source.lead_id AND stage NOT IN ('closed','cancelled'))) THEN
  RAISE EXCEPTION 'Existing deal requires review' USING ERRCODE='23505'; END IF;
 SELECT * INTO seller FROM public.acquisition_owner_properties WHERE id=p_relationship AND workspace_id=p_workspace
  AND lead_id=source.lead_id AND property_id IS NOT NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace seller and property required' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=source.lead_id
  AND property_id=seller.property_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Property binding changed' USING ERRCODE='42501'; END IF;
 -- Pin the approving identity so a concurrent revocation cannot cross the save.
 PERFORM 1 FROM public.workspace_memberships m JOIN public.acquisition_offer_events e ON e.actor_id=m.user_id
  WHERE e.offer_id=p_offer AND e.sequence=p_offer_sequence AND m.workspace_id=p_workspace FOR SHARE OF m;
 PERFORM 1 FROM public.profiles p JOIN public.acquisition_offer_events e ON e.actor_id=p.id
  WHERE e.offer_id=p_offer AND e.sequence=p_offer_sequence FOR SHARE OF p;
 review:=private.acquisition_offer_review_state(p_workspace,p_offer);
 IF review->>'amount_approval_current' IS DISTINCT FROM 'true' OR (review->>'sequence')::integer IS DISTINCT FROM p_offer_sequence
 OR (review->>'property_id')::uuid IS DISTINCT FROM seller.property_id THEN
  RAISE EXCEPTION 'Current reviewed amount and property required' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS(SELECT 1 FROM auth.sessions WHERE id::text=auth.jwt()->>'session_id' AND user_id=auth.uid()
  AND (not_after IS NULL OR not_after>clock_timestamp())) THEN
  RAISE EXCEPTION 'Session expired during draft review' USING ERRCODE='42501'; END IF;
 INSERT INTO public.deals(id,lead_id,deal_name,stage,created_by,assigned_to,creation_manifest,workspace_id,
  acquisition_status,acquisition_version,acquisition_property_id,acquisition_owner_relationship_id,acquisition_offer_id,acquisition_offer_sequence)
 VALUES(p_id,source.lead_id,trim(p_name),'offer_made',auth.uid(),auth.uid(),manifest,p_workspace,'draft',1,seller.property_id,p_relationship,p_offer,p_offer_sequence)
 RETURNING * INTO deal;
 INSERT INTO public.acquisition_contract_versions(id,workspace_id,deal_id,version,status,request,actor_id)
 VALUES(p_id,p_workspace,p_id,1,'draft',manifest,auth.uid());
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_contract',p_id::text,'draft_created',auth.uid()::text,
  jsonb_build_object('version',1,'offer_id',p_offer,'offer_sequence',p_offer_sequence,'execution_authorized',false),p_workspace);
 RETURN jsonb_build_object('deal_id',p_id,'version',1,'status','draft','duplicate',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.create_acquisition_contract_draft(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.create_acquisition_contract_draft(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
CREATE FUNCTION public.create_acquisition_contract_draft(p_id uuid,p_workspace uuid,p_offer uuid,p_offer_sequence integer,p_relationship uuid,p_name text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.create_acquisition_contract_draft(p_id,p_workspace,p_offer,p_offer_sequence,p_relationship,p_name) $$;
REVOKE ALL ON FUNCTION public.create_acquisition_contract_draft(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.create_acquisition_contract_draft(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
COMMIT;
