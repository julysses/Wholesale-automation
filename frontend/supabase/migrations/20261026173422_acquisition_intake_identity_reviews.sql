-- Append-only reviewed associations; original inquiries and canonical bindings stay intact.
BEGIN;
ALTER TABLE public.seller_intakes ADD CONSTRAINT seller_intakes_workspace_identity UNIQUE(workspace_id,id);
CREATE TABLE public.acquisition_intake_identity_reviews (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 intake_id uuid NOT NULL,
 sequence integer NOT NULL CHECK(sequence>0),
 action text NOT NULL CHECK(action IN ('link_property','repeat_inquiry','revoke')),
 target_lead_id uuid,
 target_property_id uuid,
 preparation_hash text NOT NULL,
 target_hash text,
 target_snapshot jsonb,
 property_basis text,
 property_evidence_ref text,
 seller_evidence_ref text,
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 membership_updated_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,intake_id,sequence),
 FOREIGN KEY(workspace_id,intake_id) REFERENCES public.seller_intakes(workspace_id,id),
 FOREIGN KEY(workspace_id,target_lead_id,target_property_id) REFERENCES public.workspace_leads(workspace_id,lead_id,property_id),
 CHECK((action='revoke' AND target_lead_id IS NULL AND target_property_id IS NULL AND target_hash IS NULL AND target_snapshot IS NULL
    AND property_basis IS NULL AND property_evidence_ref IS NULL AND seller_evidence_ref IS NULL)
  OR (action IN ('link_property','repeat_inquiry') AND target_lead_id IS NOT NULL AND target_property_id IS NOT NULL
    AND target_hash IS NOT NULL AND target_snapshot IS NOT NULL AND jsonb_typeof(target_snapshot)='object'
    AND property_basis IS NOT NULL AND property_evidence_ref IS NOT NULL AND property_basis IN ('parcel_document','verified_address') AND length(trim(property_evidence_ref)) BETWEEN 10 AND 500
    AND (action='link_property' AND seller_evidence_ref IS NULL OR action='repeat_inquiry' AND seller_evidence_ref IS NOT NULL AND length(trim(seller_evidence_ref)) BETWEEN 10 AND 500)))
);
ALTER TABLE public.acquisition_intake_identity_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_intake_identity_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_intake_identity_reviews TO authenticated;
CREATE POLICY intake_identity_review_read ON public.acquisition_intake_identity_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER intake_identity_review_immutable BEFORE UPDATE OR DELETE ON public.acquisition_intake_identity_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_identity_target(p_workspace uuid,p_target uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object('lead_id',b.lead_id,'property_id',b.property_id,
 'property_address',l.property_address,'city',l.city,'state',l.state,'zip_code',l.zip_code,
 'owner_first_name',l.owner_first_name,'owner_last_name',l.owner_last_name,
 'contact_fingerprint',encode(sha256(convert_to(jsonb_build_array(
  private.acquisition_optional_contact('phone',l.owner_phone_1),private.acquisition_optional_contact('phone',l.owner_phone_2),
  private.acquisition_optional_contact('phone',l.owner_phone_3),private.acquisition_optional_contact('email',l.owner_email))::text,'UTF8')),'hex'),
 'county',p.county,'parcel_id',p.parcel_id,'county_address',p.address_std,'county_unit',p.unit,
 'county_city',p.city,'county_state',p.state,'county_zip',p.zip)
 FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
 JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
 WHERE b.workspace_id=p_workspace AND b.lead_id=p_target
$$;
REVOKE ALL ON FUNCTION private.acquisition_identity_target(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_intake_identity_state(p_workspace uuid,p_intake uuid,p_target uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; latest public.acquisition_intake_identity_reviews%ROWTYPE;
 target jsonb; target_hash text; current_target jsonb; current_hash text; active boolean; current_link boolean:=false;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace intake review access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=p_workspace AND id=p_intake;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 IF p_target IS NOT NULL THEN
  target:=private.acquisition_identity_target(p_workspace,p_target);
  IF target IS NULL OR p_target=intake.lead_id THEN RAISE EXCEPTION 'Canonical target unavailable' USING ERRCODE='42501'; END IF;
  target_hash:=encode(sha256(convert_to(target::text,'UTF8')),'hex');
 END IF;
 SELECT * INTO latest FROM public.acquisition_intake_identity_reviews WHERE workspace_id=p_workspace AND intake_id=p_intake ORDER BY sequence DESC LIMIT 1;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 IF latest.action IN ('link_property','repeat_inquiry') THEN
  current_target:=private.acquisition_identity_target(p_workspace,latest.target_lead_id);
  current_hash:=encode(sha256(convert_to(current_target::text,'UTF8')),'hex');
  current_link:=coalesce(active AND current_hash=latest.target_hash AND EXISTS(
   SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   WHERE m.workspace_id=p_workspace AND m.user_id=latest.actor_id AND m.status='active' AND m.role IN ('owner','admin')
    AND m.updated_at=latest.membership_updated_at AND p.status='approved'),false);
 END IF;
 RETURN jsonb_build_object('intake_id',intake.id,'source_lead_id',intake.lead_id,'preparation_hash',intake.preparation_hash,
  'sequence',coalesce(latest.sequence,0),'latest_review',CASE WHEN latest.id IS NULL THEN NULL ELSE to_jsonb(latest) END,
  'link_current',current_link,'target_snapshot',target,'target_hash',target_hash,
  'ownership_verified',false,'contact_permission_granted',false,'outreach_authorized',false);
END $$;

CREATE FUNCTION private.review_acquisition_intake_identity(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,
 p_preparation_hash text,p_action text,p_target uuid,p_target_hash text,p_property_basis text,p_property_evidence_ref text,p_seller_evidence_ref text,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; saved public.acquisition_intake_identity_reviews%ROWTYPE;
 latest public.acquisition_intake_identity_reviews%ROWTYPE; active boolean; member_updated timestamptz;
 target jsonb; fingerprint text; generation integer; target_property uuid;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Workspace identity administrator with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence<0 OR p_preparation_hash IS NULL
  OR p_action IS NULL OR p_action NOT IN ('link_property','repeat_inquiry','revoke')
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Documented identity review required' USING ERRCODE='22023'; END IF;
 IF p_action='revoke' THEN
  IF p_target IS NOT NULL OR p_target_hash IS NOT NULL OR p_property_basis IS NOT NULL OR p_property_evidence_ref IS NOT NULL OR p_seller_evidence_ref IS NOT NULL THEN
   RAISE EXCEPTION 'Revocation cannot assert a target' USING ERRCODE='22023'; END IF;
 ELSE
  IF p_target IS NULL OR p_target_hash IS NULL OR p_property_basis IS NULL OR p_property_basis NOT IN ('parcel_document','verified_address')
   OR p_property_evidence_ref IS NULL OR length(trim(p_property_evidence_ref)) NOT BETWEEN 10 AND 500
   OR (p_action='repeat_inquiry' AND (p_seller_evidence_ref IS NULL OR length(trim(p_seller_evidence_ref)) NOT BETWEEN 10 AND 500))
   OR (p_action='link_property' AND p_seller_evidence_ref IS NOT NULL) THEN
   RAISE EXCEPTION 'Independent property and applicable seller identity evidence required' USING ERRCODE='22023'; END IF;
 END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 -- Revocation remains possible while activation is held.
 IF p_action<>'revoke' AND active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at INTO member_updated FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid()
  AND m.status='active' AND m.role IN ('owner','admin') AND p.status='approved'
  AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('intake-identity-review:'||p_id,0));
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=p_workspace AND id=p_intake FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_intake_identity_reviews WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.intake_id,saved.sequence,saved.preparation_hash,saved.action,saved.target_lead_id,saved.target_hash,
    saved.property_basis,saved.property_evidence_ref,saved.seller_evidence_ref,saved.review_note,saved.actor_id)
   IS DISTINCT FROM ROW(p_workspace,p_intake,p_expected_sequence+1,p_preparation_hash,p_action,p_target,p_target_hash,
    p_property_basis,p_property_evidence_ref,p_seller_evidence_ref,p_note,auth.uid()) THEN
   RAISE EXCEPTION 'Identity review request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'sequence',saved.sequence,'duplicate',true,'outreach_authorized',false);
 END IF;
 SELECT * INTO latest FROM public.acquisition_intake_identity_reviews WHERE workspace_id=p_workspace AND intake_id=p_intake ORDER BY sequence DESC LIMIT 1;
 generation:=coalesce(latest.sequence,0)+1;
 IF p_expected_sequence<>generation-1 OR p_preparation_hash<>intake.preparation_hash THEN
  RAISE EXCEPTION 'Intake review state changed' USING ERRCODE='40001'; END IF;
 IF p_action='revoke' THEN
  IF latest.id IS NULL OR latest.action='revoke' THEN RAISE EXCEPTION 'No link to revoke' USING ERRCODE='55000'; END IF;
 ELSE
  IF p_target=intake.lead_id THEN RAISE EXCEPTION 'Self association prohibited' USING ERRCODE='22023'; END IF;
  -- Lock the canonical identity through commit; no phone-based property reassignment.
  PERFORM 1 FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
   JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
   WHERE b.workspace_id=p_workspace AND b.lead_id=p_target FOR SHARE OF b,l,p;
  IF NOT FOUND THEN RAISE EXCEPTION 'Canonical target unavailable' USING ERRCODE='42501'; END IF;
  target:=private.acquisition_identity_target(p_workspace,p_target);
  fingerprint:=encode(sha256(convert_to(target::text,'UTF8')),'hex');
  IF fingerprint IS DISTINCT FROM p_target_hash THEN RAISE EXCEPTION 'Target evidence changed' USING ERRCODE='40001'; END IF;
  target_property:=(target->>'property_id')::uuid;
 END IF;
 INSERT INTO public.acquisition_intake_identity_reviews(id,workspace_id,intake_id,sequence,action,target_lead_id,target_property_id,
  preparation_hash,target_hash,target_snapshot,property_basis,property_evidence_ref,seller_evidence_ref,review_note,actor_id,membership_updated_at)
 VALUES(p_id,p_workspace,p_intake,generation,p_action,p_target,target_property,p_preparation_hash,p_target_hash,target,
  p_property_basis,p_property_evidence_ref,p_seller_evidence_ref,p_note,auth.uid(),member_updated);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('seller_intake_identity',p_intake::text,p_action,auth.uid()::text,
  jsonb_build_object('review_id',p_id,'sequence',generation,'target_lead_id',p_target,'target_property_id',target_property,'outreach_authorized',false),p_workspace);
 RETURN jsonb_build_object('review_id',p_id,'sequence',generation,'duplicate',false,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_intake_identity_state(p_workspace uuid,p_intake uuid,p_target uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_intake_identity_state(p_workspace,p_intake,p_target) $$;
CREATE FUNCTION public.review_acquisition_intake_identity(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,
 p_preparation_hash text,p_action text,p_target uuid,p_target_hash text,p_property_basis text,p_property_evidence_ref text,p_seller_evidence_ref text,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.review_acquisition_intake_identity(p_id,p_workspace,p_intake,p_expected_sequence,p_preparation_hash,p_action,p_target,p_target_hash,p_property_basis,p_property_evidence_ref,p_seller_evidence_ref,p_note)
$$;
REVOKE ALL ON FUNCTION private.acquisition_intake_identity_state(uuid,uuid,uuid),public.acquisition_intake_identity_state(uuid,uuid,uuid),
 private.review_acquisition_intake_identity(uuid,uuid,uuid,integer,text,text,uuid,text,text,text,text,text),
 public.review_acquisition_intake_identity(uuid,uuid,uuid,integer,text,text,uuid,text,text,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_intake_identity_state(uuid,uuid,uuid),public.acquisition_intake_identity_state(uuid,uuid,uuid),
 private.review_acquisition_intake_identity(uuid,uuid,uuid,integer,text,text,uuid,text,text,text,text,text),
 public.review_acquisition_intake_identity(uuid,uuid,uuid,integer,text,text,uuid,text,text,text,text,text) TO authenticated;
COMMIT;
