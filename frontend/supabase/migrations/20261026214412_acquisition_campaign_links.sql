-- Reviewed attribution only; does not configure provider routing or publish ads.
BEGIN;
ALTER TABLE public.ad_campaigns ADD CONSTRAINT acquisition_campaign_workspace_unique UNIQUE(workspace_id,id);
CREATE TABLE public.acquisition_campaign_links (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 integration_id uuid NOT NULL,
 external_campaign_id text NOT NULL CHECK(external_campaign_id ~ '^[0-9]{1,200}$'),
 sequence integer NOT NULL CHECK(sequence>0),
 action text NOT NULL CHECK(action IN ('link','revoke')),
 campaign_id uuid,
 ad_account_id text,
 intake_id uuid NOT NULL,
 preparation_hash text NOT NULL,
 evidence_ref text NOT NULL CHECK(length(trim(evidence_ref)) BETWEEN 10 AND 500),
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 membership_updated_at timestamptz NOT NULL,
 integration_approval_ref text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(integration_id,external_campaign_id,sequence),
 FOREIGN KEY(integration_id,workspace_id) REFERENCES private.acquisition_integrations(id,workspace_id),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id),
 FOREIGN KEY(workspace_id,intake_id) REFERENCES public.seller_intakes(workspace_id,id),
 CHECK((action='link' AND campaign_id IS NOT NULL AND ad_account_id IS NOT NULL AND ad_account_id ~ '^[0-9]{1,200}$')
  OR (action='revoke' AND campaign_id IS NULL AND ad_account_id IS NULL))
);
CREATE INDEX acquisition_campaign_links_workspace ON public.acquisition_campaign_links(workspace_id,id);
CREATE INDEX acquisition_campaign_links_external ON public.acquisition_campaign_links(external_campaign_id,integration_id,sequence DESC);
ALTER TABLE public.acquisition_campaign_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_campaign_links FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_campaign_links TO authenticated;
CREATE POLICY acquisition_campaign_links_read ON public.acquisition_campaign_links FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_campaign_links_immutable BEFORE UPDATE OR DELETE ON public.acquisition_campaign_links
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_campaign_link_state(p_workspace uuid,p_intake uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; integration private.acquisition_integrations%ROWTYPE;
 external_id text; latest public.acquisition_campaign_links%ROWTYPE; active boolean; current_link boolean:=false;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Campaign read access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 SELECT i.* INTO integration FROM private.acquisition_integrations i JOIN public.webhook_jobs j ON j.acquisition_integration_id=i.id AND j.workspace_id=i.workspace_id
 WHERE j.id=intake.receipt_id AND i.workspace_id=p_workspace AND i.provider='facebook';
 external_id:=intake.prepared_answers->'provider_evidence'->>'campaign_id';
 IF integration.id IS NULL OR intake.source_type<>'facebook_native_form' OR jsonb_typeof(intake.prepared_answers->'provider_evidence'->'campaign_id') IS DISTINCT FROM 'string'
  OR external_id IS NULL OR external_id !~ '^[0-9]{1,200}$'
  OR intake.prepared_answers->'provider_evidence'->>'id' IS DISTINCT FROM intake.prepared_answers->>'external_lead_id'
  OR intake.prepared_answers->'provider_evidence'->>'form_id' IS DISTINCT FROM intake.prepared_answers->>'provider_form_id'
  OR EXISTS(SELECT 1 FROM public.webhook_jobs j WHERE j.id=intake.receipt_id AND j.payload->>'campaign_id' IS NOT NULL AND j.payload->>'campaign_id'<>external_id) THEN
  RAISE EXCEPTION 'Verified campaign evidence unavailable' USING ERRCODE='55000'; END IF;
 SELECT * INTO latest FROM public.acquisition_campaign_links WHERE integration_id=integration.id AND external_campaign_id=external_id ORDER BY sequence DESC LIMIT 1;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 IF latest.action='link' AND active AND integration.enabled AND integration.approval_ref IS NOT DISTINCT FROM latest.integration_approval_ref THEN
  SELECT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   JOIN public.workspaces w ON w.id=m.workspace_id JOIN public.ad_campaigns c ON c.id=latest.campaign_id AND c.workspace_id=w.id
   WHERE m.workspace_id=p_workspace AND m.user_id=latest.actor_id AND m.status='active' AND m.role IN ('owner','admin')
    AND m.updated_at=latest.membership_updated_at AND p.status='approved' AND w.status='active' AND c.acquisition_channel='facebook') INTO current_link;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'intake_id',p_intake,'preparation_hash',intake.preparation_hash,
  'integration_id',integration.id,'page_id',integration.account_id,'external_campaign_id',external_id,
  'sequence',coalesce(latest.sequence,0),'latest_review',CASE WHEN latest.id IS NOT NULL THEN to_jsonb(latest) ELSE NULL END,
  'link_current',current_link,'internal_campaign_id',CASE WHEN current_link THEN latest.campaign_id ELSE NULL END,
  'execution_authorized',false);
END $$;

CREATE FUNCTION private.review_acquisition_campaign_link(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,
 p_preparation_hash text,p_action text,p_campaign uuid,p_ad_account text,p_evidence_ref text,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE state jsonb; intake public.seller_intakes%ROWTYPE; integration private.acquisition_integrations%ROWTYPE;
 latest public.acquisition_campaign_links%ROWTYPE; saved public.acquisition_campaign_links%ROWTYPE;
 external_id text; member_updated timestamptz; active boolean; generation integer;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Campaign administrator with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_expected_sequence IS NULL OR p_expected_sequence<0 OR p_preparation_hash IS NULL
  OR p_action IS NULL OR p_action NOT IN ('link','revoke') OR p_evidence_ref IS NULL OR length(trim(p_evidence_ref)) NOT BETWEEN 10 AND 500
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000
  OR (p_action='link' AND (p_campaign IS NULL OR p_ad_account IS NULL OR p_ad_account !~ '^[0-9]{1,200}$'))
  OR (p_action='revoke' AND (p_campaign IS NOT NULL OR p_ad_account IS NOT NULL)) THEN
  RAISE EXCEPTION 'Documented account ownership review required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at INTO member_updated FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('campaign-link-request:'||p_id::text,0));
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake AND workspace_id=p_workspace FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Intake unavailable' USING ERRCODE='42501'; END IF;
 SELECT i.* INTO integration FROM private.acquisition_integrations i JOIN public.webhook_jobs j ON j.acquisition_integration_id=i.id AND j.workspace_id=i.workspace_id
 WHERE j.id=intake.receipt_id AND i.workspace_id=p_workspace AND i.provider='facebook' FOR SHARE OF i,j;
 state:=private.acquisition_campaign_link_state(p_workspace,p_intake);
 external_id:=state->>'external_campaign_id';
 -- Serialize across Pages/workspaces: an external campaign cannot be claimed twice.
 PERFORM pg_advisory_xact_lock(hashtextextended('facebook-campaign-link:'||external_id,0));
 SELECT * INTO saved FROM public.acquisition_campaign_links WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.intake_id,saved.sequence,saved.preparation_hash,saved.action,saved.campaign_id,saved.ad_account_id,saved.evidence_ref,saved.review_note,saved.actor_id)
   IS DISTINCT FROM ROW(p_workspace,p_intake,p_expected_sequence+1,p_preparation_hash,p_action,p_campaign,p_ad_account,p_evidence_ref,p_note,auth.uid()) THEN
   RAISE EXCEPTION 'Campaign link request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'sequence',saved.sequence,'duplicate',true,'execution_authorized',false);
 END IF;
 SELECT * INTO latest FROM public.acquisition_campaign_links WHERE integration_id=integration.id AND external_campaign_id=external_id ORDER BY sequence DESC LIMIT 1;
 generation:=coalesce(latest.sequence,0)+1;
 IF p_expected_sequence<>generation-1 OR p_preparation_hash<>intake.preparation_hash THEN RAISE EXCEPTION 'Campaign evidence changed' USING ERRCODE='40001'; END IF;
 IF p_action='revoke' THEN
  IF latest.id IS NULL OR latest.action<>'link' THEN RAISE EXCEPTION 'No campaign link to revoke' USING ERRCODE='55000'; END IF;
 ELSE
  IF active IS DISTINCT FROM true OR NOT integration.enabled THEN RAISE EXCEPTION 'Acquisition integration activation required' USING ERRCODE='55000'; END IF;
  IF latest.action='link' THEN RAISE EXCEPTION 'Revoke prior campaign link before replacing it' USING ERRCODE='55000'; END IF;
  IF EXISTS(SELECT 1 FROM (SELECT DISTINCT ON (integration_id) action FROM public.acquisition_campaign_links
    WHERE external_campaign_id=external_id ORDER BY integration_id,sequence DESC) current_reviews WHERE action='link') THEN
   RAISE EXCEPTION 'External campaign has an unreconciled ownership review' USING ERRCODE='55000'; END IF;
  PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='facebook' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Workspace Facebook campaign unavailable' USING ERRCODE='42501'; END IF;
 END IF;
 INSERT INTO public.acquisition_campaign_links(id,workspace_id,integration_id,external_campaign_id,sequence,action,campaign_id,ad_account_id,
  intake_id,preparation_hash,evidence_ref,review_note,actor_id,membership_updated_at,integration_approval_ref)
 VALUES(p_id,p_workspace,integration.id,external_id,generation,p_action,p_campaign,p_ad_account,p_intake,p_preparation_hash,p_evidence_ref,p_note,auth.uid(),member_updated,integration.approval_ref);
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_campaign_link',p_id::text,p_action,auth.uid()::text,jsonb_build_object('sequence',generation,'campaign_id',p_campaign,'integration_id',integration.id,'execution_authorized',false),p_workspace);
 RETURN jsonb_build_object('review_id',p_id,'sequence',generation,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_campaign_link_state(p_workspace uuid,p_intake uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_campaign_link_state(p_workspace,p_intake) $$;
CREATE FUNCTION public.review_acquisition_campaign_link(p_id uuid,p_workspace uuid,p_intake uuid,p_expected_sequence integer,p_preparation_hash text,p_action text,p_campaign uuid,p_ad_account text,p_evidence_ref text,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.review_acquisition_campaign_link(p_id,p_workspace,p_intake,p_expected_sequence,p_preparation_hash,p_action,p_campaign,p_ad_account,p_evidence_ref,p_note) $$;
REVOKE ALL ON FUNCTION private.acquisition_campaign_link_state(uuid,uuid),public.acquisition_campaign_link_state(uuid,uuid),
 private.review_acquisition_campaign_link(uuid,uuid,uuid,integer,text,text,uuid,text,text,text),public.review_acquisition_campaign_link(uuid,uuid,uuid,integer,text,text,uuid,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_campaign_link_state(uuid,uuid),public.acquisition_campaign_link_state(uuid,uuid),
 private.review_acquisition_campaign_link(uuid,uuid,uuid,integer,text,text,uuid,text,text,text),public.review_acquisition_campaign_link(uuid,uuid,uuid,integer,text,text,uuid,text,text,text) TO authenticated;
COMMIT;
