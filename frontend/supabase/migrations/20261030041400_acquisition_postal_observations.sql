-- Additive provenance only. No postal normalization, verification or mailing authority.
BEGIN;
CREATE TABLE public.acquisition_postal_observations (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 relationship_id uuid NOT NULL,
 raw_address text NOT NULL CHECK(length(trim(raw_address))>0 AND octet_length(raw_address)<=4096),
 source_kind text NOT NULL DEFAULT 'lead_owner_mailing_address' CHECK(source_kind='lead_owner_mailing_address'),
 source_evidence jsonb NOT NULL CHECK(jsonb_typeof(source_evidence)='object'),
 source_hash bytea NOT NULL CHECK(octet_length(source_hash)=32),
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status='unverified'),
 recorded_by uuid NOT NULL REFERENCES public.profiles(id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,relationship_id) REFERENCES public.acquisition_owner_properties(workspace_id,id)
);
CREATE INDEX acquisition_postal_relationship_idx ON public.acquisition_postal_observations(workspace_id,relationship_id,recorded_at DESC);
ALTER TABLE public.acquisition_postal_observations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_postal_observations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_postal_observations TO authenticated;
CREATE POLICY acquisition_postal_read ON public.acquisition_postal_observations FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_postal_immutable BEFORE UPDATE OR DELETE ON public.acquisition_postal_observations
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT ON public.acquisition_postal_observations
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();

CREATE FUNCTION private.import_acquisition_postal_observation(p_id uuid,p_workspace uuid,p_relationship uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_postal_observations%ROWTYPE; relation public.acquisition_owner_properties%ROWTYPE;
 raw text; evidence jsonb; stamped timestamptz;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
 OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Postal provenance access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_relationship IS NULL THEN RAISE EXCEPTION 'Observation identity required' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('postal-observation:'||p_id::text,0));
 -- Hold actual authority rows through commit and recheck wall-clock expiry after waits.
 PERFORM 1 FROM public.workspaces w JOIN public.workspace_memberships m ON m.workspace_id=w.id
 JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id AND s.id::text=auth.jwt()->>'session_id'
 WHERE w.id=p_workspace AND m.user_id=auth.uid() FOR SHARE OF w,m,p,s;
 stamped:=clock_timestamp();
 IF NOT EXISTS(SELECT 1 FROM public.workspaces w JOIN public.workspace_memberships m ON m.workspace_id=w.id
 JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id AND s.id::text=auth.jwt()->>'session_id'
 WHERE w.id=p_workspace AND w.status='active' AND m.user_id=auth.uid() AND m.status='active'
 AND m.role IN ('owner','admin','operator') AND p.status='approved' AND (s.not_after IS NULL OR s.not_after>stamped)) THEN
  RAISE EXCEPTION 'Current postal provenance access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO relation FROM public.acquisition_owner_properties WHERE workspace_id=p_workspace AND id=p_relationship;
 IF NOT FOUND THEN RAISE EXCEPTION 'Owner relationship unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_postal_observations WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.relationship_id<>p_relationship THEN
   RAISE EXCEPTION 'Postal observation identity conflict' USING ERRCODE='23505'; END IF;
  -- Exact historical recovery remains possible; it never grants verification.
  RETURN to_jsonb(saved)||jsonb_build_object('duplicate',true,'execution_authorized',false);
 END IF;
 SELECT owner_mailing_address INTO raw FROM public.leads WHERE id=relation.lead_id FOR SHARE;
 IF raw IS NULL OR length(trim(raw))=0 OR octet_length(raw)>4096 THEN
  RAISE EXCEPTION 'Owner mailing address requires review' USING ERRCODE='22023'; END IF;
 -- Acquire the activation lock before the final wall-clock session check.
 -- The insert trigger reuses this lock and cannot introduce a new expiry wait.
 PERFORM 1 FROM private.acquisition_activation WHERE singleton FOR SHARE;
 -- Source or activation waits can outlive a session while authority rows stay locked.
 IF NOT EXISTS(SELECT 1 FROM auth.sessions s WHERE s.user_id=auth.uid() AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp())) THEN
  RAISE EXCEPTION 'Current postal session required' USING ERRCODE='42501'; END IF;
 evidence:=jsonb_build_object('source','public.leads','field','owner_mailing_address','lead_id',relation.lead_id,
  'owner_id',relation.owner_id,'relationship_id',relation.id,'raw_address',raw,'ownership_verified',false);
 INSERT INTO public.acquisition_postal_observations(id,workspace_id,relationship_id,raw_address,source_evidence,source_hash,recorded_by)
 VALUES(p_id,p_workspace,p_relationship,raw,evidence,extensions.digest(convert_to(evidence::text,'UTF8'),'sha256'),auth.uid()) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_postal_observation',p_id::text,'imported_unverified',auth.uid()::text,p_workspace,
  jsonb_build_object('relationship_id',p_relationship,'source_hash',encode(saved.source_hash,'hex'),'verification_status','unverified'));
 RETURN to_jsonb(saved)||jsonb_build_object('duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.import_acquisition_postal_observation(p_id uuid,p_workspace uuid,p_relationship uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.import_acquisition_postal_observation(p_id,p_workspace,p_relationship)
$$;
REVOKE ALL ON FUNCTION private.import_acquisition_postal_observation(uuid,uuid,uuid),public.import_acquisition_postal_observation(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.import_acquisition_postal_observation(uuid,uuid,uuid),public.import_acquisition_postal_observation(uuid,uuid,uuid) TO authenticated;
COMMIT;
