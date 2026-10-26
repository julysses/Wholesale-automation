-- Fail-closed eligibility foundation. No approved policy or ALLOW path exists.
BEGIN;
CREATE TABLE public.acquisition_contact_suppressions (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 contact_point_id uuid NOT NULL,
 lead_id uuid NOT NULL,
 channel text NOT NULL CHECK(channel IN ('all','human_voice','ai_voice','prerecorded','sms','email','direct_mail')),
 reason text NOT NULL CHECK(reason IN ('seller_opt_out','wrong_number','legal_restriction','deceased','contact_preference')),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,contact_point_id) REFERENCES public.acquisition_contact_points(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id)
);
CREATE INDEX acquisition_suppression_point_idx ON public.acquisition_contact_suppressions(contact_point_id,channel);
CREATE INDEX acquisition_suppression_workspace_idx ON public.acquisition_contact_suppressions(workspace_id,created_at);
CREATE TABLE public.acquisition_eligibility_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL,
 lead_id uuid NOT NULL,
 contact_point_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 channel text NOT NULL CHECK(channel IN ('human_voice','ai_voice','prerecorded','sms','email','direct_mail')),
 decision text NOT NULL CHECK(decision IN ('BLOCK','REVIEW')),
 reason_codes text[] NOT NULL CHECK(cardinality(reason_codes)>0),
 policy_version text NOT NULL CHECK(policy_version='pending-v1'),
 checked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz CHECK(expires_at IS NULL),
 permitted_actions jsonb NOT NULL DEFAULT '[]' CHECK(permitted_actions='[]'::jsonb),
 inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),
 evaluated_state jsonb NOT NULL CHECK(jsonb_typeof(evaluated_state)='object'),
 FOREIGN KEY(workspace_id,contact_point_id) REFERENCES public.acquisition_contact_points(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id)
);
CREATE INDEX acquisition_eligibility_workspace_idx ON public.acquisition_eligibility_decisions(workspace_id,lead_id,checked_at DESC);
ALTER TABLE public.acquisition_contact_suppressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.acquisition_eligibility_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_contact_suppressions,public.acquisition_eligibility_decisions FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_contact_suppressions,public.acquisition_eligibility_decisions TO authenticated;
CREATE POLICY acquisition_suppression_read ON public.acquisition_contact_suppressions FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE POLICY acquisition_eligibility_read ON public.acquisition_eligibility_decisions FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_suppression_immutable BEFORE UPDATE OR DELETE ON public.acquisition_contact_suppressions
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE TRIGGER acquisition_eligibility_immutable BEFORE UPDATE OR DELETE ON public.acquisition_eligibility_decisions
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_can_evaluate(p_workspace uuid,p_lead uuid,p_contact uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.workspace_leads b
  JOIN public.acquisition_contact_observations o ON o.workspace_id=b.workspace_id AND o.lead_id=b.lead_id
  WHERE b.workspace_id=p_workspace AND b.lead_id=p_lead AND o.contact_point_id=p_contact
  AND (private.acquisition_role(p_workspace) IN ('owner','admin','operator') OR
    (private.acquisition_role(p_workspace) IN ('acquisition_caller','agency_manager') AND b.assigned_user_id=auth.uid())));
$$;
REVOKE ALL ON FUNCTION private.acquisition_can_evaluate(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

-- Compatibility comparison only; invalid/ambiguous legacy endpoints cannot confer permission.
CREATE FUNCTION private.acquisition_try_normalize(p_type text,p_value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
BEGIN RETURN private.normalize_acquisition_contact(p_type,p_value);
EXCEPTION WHEN SQLSTATE '22023' THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_try_normalize(text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.record_acquisition_suppression(p_id uuid,p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_contact_suppressions%ROWTYPE;
BEGIN
 IF NOT private.acquisition_can_evaluate(p_workspace,p_lead,p_contact) THEN
  RAISE EXCEPTION 'Assigned workspace contact required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_channel IS NULL OR p_channel NOT IN ('all','human_voice','ai_voice','prerecorded','sms','email','direct_mail')
 OR p_reason IS NULL OR p_reason NOT IN ('seller_opt_out','wrong_number','legal_restriction','deceased','contact_preference') THEN
  RAISE EXCEPTION 'Invalid suppression' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('suppression:'||p_id::text,0));
 SELECT * INTO saved FROM public.acquisition_contact_suppressions WHERE id=p_id;
 IF FOUND THEN
  IF saved.workspace_id<>p_workspace OR saved.lead_id<>p_lead OR saved.contact_point_id<>p_contact
   OR saved.channel<>p_channel OR saved.reason<>p_reason OR saved.actor_id<>auth.uid() THEN
   RAISE EXCEPTION 'Suppression identity conflict' USING ERRCODE='23505'; END IF;
 ELSE
  INSERT INTO public.acquisition_contact_suppressions(id,workspace_id,contact_point_id,lead_id,channel,reason,actor_id)
  VALUES(p_id,p_workspace,p_contact,p_lead,p_channel,p_reason,auth.uid()) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('contact_suppression',p_id::text,'recorded',auth.uid()::text,to_jsonb(saved),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'channel',saved.channel,'reason',saved.reason,'created_at',saved.created_at);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_suppression(uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_suppression(uuid,uuid,uuid,uuid,text,text) TO authenticated;
CREATE FUNCTION public.record_acquisition_suppression(p_id uuid,p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_reason text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.record_acquisition_suppression(p_id,p_workspace,p_lead,p_contact,p_channel,p_reason) $$;
REVOKE ALL ON FUNCTION public.record_acquisition_suppression(uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_acquisition_suppression(uuid,uuid,uuid,uuid,text,text) TO authenticated;

CREATE FUNCTION private.evaluate_acquisition_eligibility(p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_purpose text,p_actor_type text,p_campaign uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE endpoint public.acquisition_contact_points%ROWTYPE; saved public.acquisition_eligibility_decisions%ROWTYPE;
 suppressed boolean; legacy_suppressed boolean; reasons text[]:=ARRAY['LEGAL_POLICY_NOT_APPROVED']; state jsonb;
BEGIN
 IF NOT private.acquisition_can_evaluate(p_workspace,p_lead,p_contact) THEN
  RAISE EXCEPTION 'Assigned workspace contact required' USING ERRCODE='42501'; END IF;
 IF p_channel IS NULL OR p_channel NOT IN ('human_voice','ai_voice','prerecorded','sms','email','direct_mail')
 OR p_purpose IS DISTINCT FROM 'principal_property_acquisition'
 OR p_actor_type IS NULL OR p_actor_type NOT IN ('human','ai','prerecorded','system')
 OR (p_channel='human_voice' AND p_actor_type<>'human') OR (p_channel='ai_voice' AND p_actor_type<>'ai')
 OR (p_channel='prerecorded' AND p_actor_type<>'prerecorded') THEN
  RAISE EXCEPTION 'Invalid channel, purpose or actor type' USING ERRCODE='22023'; END IF;
 SELECT * INTO endpoint FROM public.acquisition_contact_points WHERE workspace_id=p_workspace AND id=p_contact;
 -- Matching endpoints across workspaces are checked privately. Only a generic
 -- restriction result is returned, never other tenants' records or identities.
 SELECT EXISTS(SELECT 1 FROM public.acquisition_contact_suppressions s
  JOIN public.acquisition_contact_points c ON c.id=s.contact_point_id
  WHERE c.type=endpoint.type AND c.normalized_value=endpoint.normalized_value
  AND s.channel IN ('all',p_channel)) INTO suppressed;
 SELECT EXISTS(SELECT 1 FROM public.leads l WHERE l.dnc IS TRUE AND (l.id=p_lead OR
  (endpoint.type='phone' AND EXISTS(SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(value)
   WHERE private.acquisition_try_normalize('phone',n.value)=endpoint.normalized_value)) OR
  (endpoint.type='email' AND private.acquisition_try_normalize('email',l.owner_email)=endpoint.normalized_value)))
 OR EXISTS(SELECT 1 FROM public.dnc_registry d WHERE d.lead_id=p_lead OR
  (endpoint.type='phone' AND private.acquisition_try_normalize('phone',d.phone_number)=endpoint.normalized_value) OR
  (endpoint.type='email' AND private.acquisition_try_normalize('email',d.email)=endpoint.normalized_value))
 OR (endpoint.type='email' AND EXISTS(SELECT 1 FROM public.email_suppressions e WHERE e.email=endpoint.normalized_value))
 OR EXISTS(SELECT 1 FROM wholesale_ingest.contacts c WHERE c.dnc_status='listed' AND
  ((endpoint.type='phone' AND private.acquisition_try_normalize('phone',c.phone)=endpoint.normalized_value) OR
   (endpoint.type='email' AND private.acquisition_try_normalize('email',c.email)=endpoint.normalized_value)))
 OR EXISTS(SELECT 1 FROM public.acquisition_contact_observations o
  JOIN public.acquisition_contact_points c ON c.id=o.contact_point_id
  WHERE c.type=endpoint.type AND c.normalized_value=endpoint.normalized_value AND o.evidence->>'dnc_status'='listed')
 INTO legacy_suppressed;
 IF suppressed OR legacy_suppressed THEN reasons:=ARRAY['CONTACT_RESTRICTED','LEGAL_POLICY_NOT_APPROVED']; END IF;
 IF p_channel='direct_mail' OR (p_channel='email' AND endpoint.type<>'email') OR
  (p_channel IN ('human_voice','ai_voice','prerecorded','sms') AND endpoint.type<>'phone') THEN
  reasons:=array_append(reasons,'CONTACT_CHANNEL_MISMATCH'); END IF;
 IF p_campaign IS NOT NULL THEN reasons:=array_append(reasons,'CAMPAIGN_SCOPE_NOT_VERIFIED'); END IF;
 state:=jsonb_build_object('contact_type',endpoint.type,'verification_status',endpoint.verification_status,
  'internal_suppression',suppressed,'legacy_restriction',legacy_suppressed,
  'observation_ids',(SELECT jsonb_agg(id ORDER BY id) FROM public.acquisition_contact_observations
   WHERE workspace_id=p_workspace AND lead_id=p_lead AND contact_point_id=p_contact),
  'permissions_evaluated',false,'calling_hours_evaluated',false,'policy_approved',false);
 INSERT INTO public.acquisition_eligibility_decisions(workspace_id,lead_id,contact_point_id,actor_id,channel,decision,reason_codes,policy_version,inputs,evaluated_state)
 VALUES(p_workspace,p_lead,p_contact,auth.uid(),p_channel,CASE WHEN suppressed OR legacy_suppressed OR 'CONTACT_CHANNEL_MISMATCH'=ANY(reasons) THEN 'BLOCK' ELSE 'REVIEW' END,
  reasons,'pending-v1',jsonb_build_object('workspace_id',p_workspace,'lead_id',p_lead,'contact_point_id',p_contact,
  'channel',p_channel,'purpose',p_purpose,'actor_type',p_actor_type,'campaign_id',p_campaign),state) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('eligibility_decision',saved.id::text,'evaluated',auth.uid()::text,
  jsonb_build_object('decision',saved.decision,'reason_codes',saved.reason_codes,'policy_version',saved.policy_version),p_workspace);
 RETURN jsonb_build_object('decision',saved.decision,'reason_codes',saved.reason_codes,'policy_version',saved.policy_version,
  'decision_id',saved.id,'expires_at',saved.expires_at,'permitted_actions',saved.permitted_actions);
END $$;
REVOKE ALL ON FUNCTION private.evaluate_acquisition_eligibility(uuid,uuid,uuid,text,text,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.evaluate_acquisition_eligibility(uuid,uuid,uuid,text,text,text,uuid) TO authenticated;
CREATE FUNCTION public.evaluate_acquisition_eligibility(p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_purpose text,p_actor_type text,p_campaign uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.evaluate_acquisition_eligibility(p_workspace,p_lead,p_contact,p_channel,p_purpose,p_actor_type,p_campaign) $$;
REVOKE ALL ON FUNCTION public.evaluate_acquisition_eligibility(uuid,uuid,uuid,text,text,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.evaluate_acquisition_eligibility(uuid,uuid,uuid,text,text,text,uuid) TO authenticated;
COMMIT;
