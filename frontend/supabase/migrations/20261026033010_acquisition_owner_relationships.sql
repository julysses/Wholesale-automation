-- Explicit owner identities over canonical lead/property records. No name or
-- phone matching merges owners; these assertions do not establish legal title.
BEGIN;
ALTER TABLE public.workspace_leads ADD CONSTRAINT workspace_leads_property_identity UNIQUE(workspace_id,lead_id,property_id);
CREATE TABLE public.acquisition_owners (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 source_lead_id uuid NOT NULL,
 display_name text NOT NULL CHECK(length(trim(display_name)) BETWEEN 1 AND 320),
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status='unverified'),
 source_evidence jsonb NOT NULL CHECK(jsonb_typeof(source_evidence)='object'),
 created_by uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,source_lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id)
);
CREATE INDEX acquisition_owners_source_idx ON public.acquisition_owners(workspace_id,source_lead_id);
CREATE TABLE public.acquisition_owner_properties (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 owner_id uuid NOT NULL,
 lead_id uuid NOT NULL,
 property_id uuid,
 relationship text NOT NULL CHECK(relationship IN ('reported_owner','reported_representative')),
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status='unverified'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 recorded_by uuid NOT NULL REFERENCES public.profiles(id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,owner_id,lead_id,relationship),
 FOREIGN KEY(workspace_id,owner_id) REFERENCES public.acquisition_owners(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 FOREIGN KEY(workspace_id,lead_id,property_id) REFERENCES public.workspace_leads(workspace_id,lead_id,property_id)
);
CREATE INDEX acquisition_owner_properties_lead_idx ON public.acquisition_owner_properties(workspace_id,lead_id);
CREATE TABLE public.acquisition_owner_contacts (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 relationship_id uuid NOT NULL,
 contact_point_id uuid NOT NULL,
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status='unverified'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 recorded_by uuid NOT NULL REFERENCES public.profiles(id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,relationship_id,contact_point_id),
 FOREIGN KEY(workspace_id,relationship_id) REFERENCES public.acquisition_owner_properties(workspace_id,id),
 FOREIGN KEY(workspace_id,contact_point_id) REFERENCES public.acquisition_contact_points(workspace_id,id)
);
CREATE INDEX acquisition_owner_contacts_point_idx ON public.acquisition_owner_contacts(workspace_id,contact_point_id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['acquisition_owners','acquisition_owner_properties','acquisition_owner_contacts'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('CREATE POLICY acquisition_owner_read ON public.%I FOR SELECT TO authenticated USING(private.acquisition_role(workspace_id) IN (''owner'',''admin'',''operator''))',t);
  EXECUTE format('CREATE TRIGGER acquisition_owner_immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact()',t);
  EXECUTE format('CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation()',t);
 END LOOP;
END $$;

CREATE FUNCTION private.create_acquisition_owner(p_id uuid,p_workspace uuid,p_lead uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_owners%ROWTYPE; source public.leads%ROWTYPE; name text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') OR NOT EXISTS(
  SELECT 1 FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=p_lead) THEN
  RAISE EXCEPTION 'Workspace lead access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL THEN RAISE EXCEPTION 'Owner identity required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('owner:'||p_id::text,0));
 SELECT * INTO saved FROM public.acquisition_owners WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.source_lead_id<>p_lead THEN
   RAISE EXCEPTION 'Owner identity conflict' USING ERRCODE='23505'; END IF;
  RETURN to_jsonb(saved);
 END IF;
 SELECT * INTO source FROM public.leads WHERE id=p_lead;
 name:=trim(concat_ws(' ',nullif(trim(source.owner_first_name),''),nullif(trim(source.owner_last_name),'')));
 IF name='' OR length(name)>320 THEN RAISE EXCEPTION 'Owner name requires intake review' USING ERRCODE='22023'; END IF;
 INSERT INTO public.acquisition_owners(id,workspace_id,source_lead_id,display_name,source_evidence,created_by)
 VALUES(p_id,p_workspace,p_lead,name,jsonb_build_object('source','public.leads','lead_id',p_lead,
  'owner_first_name',source.owner_first_name,'owner_last_name',source.owner_last_name),auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_owner',p_id::text,'created_unverified',auth.uid()::text,
  jsonb_build_object('source_lead_id',p_lead,'verification_status','unverified'),p_workspace);
 RETURN to_jsonb(saved);
END $$;

CREATE FUNCTION private.associate_acquisition_owner(p_id uuid,p_workspace uuid,p_owner uuid,p_lead uuid,p_relationship text,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_owner_properties%ROWTYPE; binding public.workspace_leads%ROWTYPE;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
  SELECT 1 FROM public.acquisition_owners WHERE workspace_id=p_workspace AND id=p_owner) THEN
  RAISE EXCEPTION 'Workspace owner review required' USING ERRCODE='42501'; END IF;
 SELECT * INTO binding FROM public.workspace_leads WHERE workspace_id=p_workspace AND lead_id=p_lead;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace lead access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_relationship IS NULL OR p_relationship NOT IN ('reported_owner','reported_representative')
 OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 10 AND 2000 THEN
  RAISE EXCEPTION 'Relationship and review note required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('owner-relationship:'||p_id::text,0));
 SELECT * INTO saved FROM public.acquisition_owner_properties WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.owner_id<>p_owner OR saved.lead_id<>p_lead OR saved.relationship<>p_relationship
   OR saved.evidence->>'review_note' IS DISTINCT FROM trim(p_note) THEN
   RAISE EXCEPTION 'Relationship identity conflict' USING ERRCODE='23505'; END IF;
  RETURN to_jsonb(saved);
 END IF;
 INSERT INTO public.acquisition_owner_properties(id,workspace_id,owner_id,lead_id,property_id,relationship,evidence,recorded_by)
 VALUES(p_id,p_workspace,p_owner,p_lead,binding.property_id,p_relationship,
  jsonb_build_object('basis','operator_assertion','review_note',trim(p_note),'title_verified',false),auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('owner_property_relationship',p_id::text,'asserted',auth.uid()::text,
  jsonb_build_object('owner_id',p_owner,'lead_id',p_lead,'property_id',binding.property_id,'relationship',p_relationship,'verification_status','unverified'),p_workspace);
 RETURN to_jsonb(saved);
END $$;

CREATE FUNCTION private.associate_acquisition_owner_contact(p_id uuid,p_workspace uuid,p_relationship uuid,p_contact uuid,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_owner_contacts%ROWTYPE; relation public.acquisition_owner_properties%ROWTYPE; observations jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Workspace owner review required' USING ERRCODE='42501'; END IF;
 SELECT * INTO relation FROM public.acquisition_owner_properties WHERE workspace_id=p_workspace AND id=p_relationship;
 IF NOT FOUND THEN RAISE EXCEPTION 'Relationship unavailable' USING ERRCODE='42501'; END IF;
 SELECT jsonb_agg(id ORDER BY id) INTO observations FROM public.acquisition_contact_observations
 WHERE workspace_id=p_workspace AND lead_id=relation.lead_id AND contact_point_id=p_contact;
 IF observations IS NULL THEN RAISE EXCEPTION 'Contact observation must match relationship lead' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 10 AND 2000 THEN
  RAISE EXCEPTION 'Review note required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('owner-contact:'||p_id::text,0));
 SELECT * INTO saved FROM public.acquisition_owner_contacts WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.relationship_id<>p_relationship OR saved.contact_point_id<>p_contact
   OR saved.evidence->>'review_note' IS DISTINCT FROM trim(p_note) THEN
   RAISE EXCEPTION 'Contact association identity conflict' USING ERRCODE='23505'; END IF;
  RETURN to_jsonb(saved);
 END IF;
 INSERT INTO public.acquisition_owner_contacts(id,workspace_id,relationship_id,contact_point_id,evidence,recorded_by)
 VALUES(p_id,p_workspace,p_relationship,p_contact,
  jsonb_build_object('basis','operator_assertion','review_note',trim(p_note),'observation_ids',observations,'consent_inferred',false),auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('owner_contact_relationship',p_id::text,'asserted',auth.uid()::text,
  jsonb_build_object('relationship_id',p_relationship,'contact_point_id',p_contact,'verification_status','unverified'),p_workspace);
 RETURN to_jsonb(saved);
END $$;

REVOKE ALL ON FUNCTION private.create_acquisition_owner(uuid,uuid,uuid),
 private.associate_acquisition_owner(uuid,uuid,uuid,uuid,text,text),
 private.associate_acquisition_owner_contact(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.create_acquisition_owner(uuid,uuid,uuid),
 private.associate_acquisition_owner(uuid,uuid,uuid,uuid,text,text),
 private.associate_acquisition_owner_contact(uuid,uuid,uuid,uuid,text) TO authenticated;
CREATE FUNCTION public.create_acquisition_owner(p_id uuid,p_workspace uuid,p_lead uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.create_acquisition_owner(p_id,p_workspace,p_lead) $$;
CREATE FUNCTION public.associate_acquisition_owner(p_id uuid,p_workspace uuid,p_owner uuid,p_lead uuid,p_relationship text,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.associate_acquisition_owner(p_id,p_workspace,p_owner,p_lead,p_relationship,p_note) $$;
CREATE FUNCTION public.associate_acquisition_owner_contact(p_id uuid,p_workspace uuid,p_relationship uuid,p_contact uuid,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.associate_acquisition_owner_contact(p_id,p_workspace,p_relationship,p_contact,p_note) $$;
REVOKE ALL ON FUNCTION public.create_acquisition_owner(uuid,uuid,uuid),
 public.associate_acquisition_owner(uuid,uuid,uuid,uuid,text,text),
 public.associate_acquisition_owner_contact(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.create_acquisition_owner(uuid,uuid,uuid),
 public.associate_acquisition_owner(uuid,uuid,uuid,uuid,text,text),
 public.associate_acquisition_owner_contact(uuid,uuid,uuid,uuid,text) TO authenticated;
COMMIT;
