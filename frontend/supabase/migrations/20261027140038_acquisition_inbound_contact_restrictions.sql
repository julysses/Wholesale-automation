-- Extend the existing immutable suppression ledger with signed call provenance.
BEGIN;
ALTER TABLE public.acquisition_contact_suppressions
 ALTER COLUMN contact_point_id DROP NOT NULL,
 ALTER COLUMN lead_id DROP NOT NULL,
 ALTER COLUMN actor_id DROP NOT NULL,
 ALTER COLUMN channel DROP NOT NULL,
 ADD COLUMN inbound_integration_id uuid,
 ADD COLUMN inbound_call_id text,
 ADD COLUMN inbound_event_id uuid,
 ADD COLUMN inbound_kind text,
 ADD COLUMN inbound_evidence jsonb,
 ADD COLUMN inbound_request_hash text,
 ADD CONSTRAINT acquisition_suppression_inbound_route_fk FOREIGN KEY(inbound_integration_id,workspace_id)
  REFERENCES private.acquisition_inbound_routes(integration_id,workspace_id),
 ADD CONSTRAINT acquisition_suppression_inbound_event_fk FOREIGN KEY(inbound_event_id,workspace_id)
  REFERENCES public.call_events(id,workspace_id),
 ADD CONSTRAINT acquisition_suppression_origin CHECK (
  (num_nonnulls(inbound_integration_id,inbound_call_id,inbound_event_id,inbound_kind,inbound_evidence,inbound_request_hash)=0
   AND contact_point_id IS NOT NULL AND lead_id IS NOT NULL AND actor_id IS NOT NULL AND channel IS NOT NULL)
  OR (num_nonnulls(inbound_integration_id,inbound_call_id,inbound_event_id,inbound_kind,inbound_evidence,inbound_request_hash)=6
   AND contact_point_id IS NULL AND lead_id IS NULL AND actor_id IS NULL
   AND inbound_call_id ~ '^[A-Za-z0-9_-]{1,200}$' AND inbound_kind IN ('do_not_contact','cancel_callback')
   AND jsonb_typeof(inbound_evidence)='object' AND inbound_request_hash ~ '^[0-9a-f]{64}$'
   AND channel IS NULL AND reason=CASE WHEN inbound_kind='do_not_contact' THEN 'seller_opt_out' ELSE 'contact_preference' END));
CREATE INDEX acquisition_suppression_inbound_call_idx ON public.acquisition_contact_suppressions(inbound_integration_id,inbound_call_id,inbound_kind)
 WHERE inbound_integration_id IS NOT NULL;

CREATE FUNCTION private.record_acquisition_inbound_restriction(p_integration uuid,p_number text,p_agent text,
 p_agent_version integer,p_call text,p_request uuid,p_kind text,p_evidence jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; saved public.acquisition_contact_suppressions%ROWTYPE;
 event_id uuid; fingerprint text;
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND provider='retell' AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number OR route.agent_id IS DISTINCT FROM p_agent
  OR route.agent_version IS DISTINCT FROM p_agent_version THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_request IS NULL OR p_kind IS NULL
  OR p_kind NOT IN ('do_not_contact','cancel_callback') OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'object'
  OR (SELECT count(*) FROM jsonb_object_keys(p_evidence))<>3
  OR NOT p_evidence ?& ARRAY['requested_by_caller','details','channels']
  OR p_evidence->'requested_by_caller' IS DISTINCT FROM 'true'::jsonb
  OR jsonb_typeof(p_evidence->'details') IS DISTINCT FROM 'string'
  OR length(trim(p_evidence->>'details')) NOT BETWEEN 1 AND 1000 THEN
  RAISE EXCEPTION 'Explicit caller restriction required' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_evidence->'channels') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'Explicit restriction channels required' USING ERRCODE='22023'; END IF;
 IF (p_kind='cancel_callback' AND p_evidence->'channels'<>'[]'::jsonb)
  OR (p_kind='do_not_contact' AND (jsonb_array_length(p_evidence->'channels') NOT BETWEEN 1 AND 7
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_evidence->'channels') v WHERE jsonb_typeof(v)<>'string')
   OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(p_evidence->'channels') v WHERE v NOT IN ('all','human_voice','ai_voice','prerecorded','sms','email','direct_mail'))
   OR (SELECT count(DISTINCT v) FROM jsonb_array_elements_text(p_evidence->'channels') v)<>jsonb_array_length(p_evidence->'channels')
   OR (p_evidence->'channels' ? 'all' AND jsonb_array_length(p_evidence->'channels')<>1))) THEN
  RAISE EXCEPTION 'Invalid restriction channel scope' USING ERRCODE='22023'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_object('integration',p_integration,'call',p_call,'kind',p_kind,'evidence',p_evidence)::text,'UTF8')),'hex');
 -- The human suppression RPC uses this same request-identity lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('suppression:'||p_request::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||p_call,0));
 SELECT * INTO saved FROM public.acquisition_contact_suppressions WHERE id=p_request;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.inbound_integration_id,saved.inbound_call_id,saved.inbound_request_hash)
   IS DISTINCT FROM ROW(route.workspace_id,p_integration,p_call,fingerprint) THEN
   RAISE EXCEPTION 'Restriction request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'kind',saved.inbound_kind,'channels',saved.inbound_evidence->'channels','duplicate',true,'execution_authorized',false);
 END IF;
 SELECT id INTO event_id FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
  AND acquisition_event_type='call_started' AND acquisition_projection->>'call_status'='ongoing';
 -- A restriction may arrive after hangup; refusing it would lose a real opt-out.
 -- The HTTP boundary still requires a fresh signature on ongoing call context.
 -- Unlike new callbacks/intakes, this action can only reduce contact authority.
 IF NOT FOUND THEN RAISE EXCEPTION 'Started inbound ledger required' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_contact_suppressions(id,workspace_id,channel,reason,inbound_integration_id,inbound_call_id,
  inbound_event_id,inbound_kind,inbound_evidence,inbound_request_hash)
 VALUES(p_request,route.workspace_id,NULL,CASE WHEN p_kind='do_not_contact' THEN 'seller_opt_out' ELSE 'contact_preference' END,
  p_integration,p_call,event_id,p_kind,p_evidence,fingerprint) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('contact_suppression',saved.id::text,'inbound_recorded','inbound_tools',
  jsonb_build_object('integration_id',p_integration,'call_id',p_call,'kind',p_kind,'channels',p_evidence->'channels','request_hash',fingerprint),route.workspace_id);
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'kind',saved.inbound_kind,'channels',saved.inbound_evidence->'channels','duplicate',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_inbound_restriction(uuid,text,text,integer,text,uuid,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_inbound_restriction(uuid,text,text,integer,text,uuid,text,jsonb) TO service_role;
CREATE FUNCTION public.record_acquisition_inbound_restriction(p_integration uuid,p_number text,p_agent text,
 p_agent_version integer,p_call text,p_request uuid,p_kind text,p_evidence jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_inbound_restriction(p_integration,p_number,p_agent,p_agent_version,p_call,p_request,p_kind,p_evidence)
$$;
REVOKE ALL ON FUNCTION public.record_acquisition_inbound_restriction(uuid,text,text,integer,text,uuid,text,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_acquisition_inbound_restriction(uuid,text,text,integer,text,uuid,text,jsonb) TO service_role;

-- Match explicit saved endpoints from every immutable intake/callback revision,
-- including answers saved after an opt-out. No caller ID or owner merge is used.
CREATE FUNCTION private.acquisition_inbound_endpoint_restricted(p_type text,p_value text,p_channel text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.acquisition_contact_suppressions s WHERE s.inbound_kind='do_not_contact' AND (s.inbound_evidence->'channels' ? 'all' OR s.inbound_evidence->'channels' ? p_channel) AND (
  EXISTS(SELECT 1 FROM public.seller_intakes i WHERE i.workspace_id=s.workspace_id
   AND i.inbound_integration_id=s.inbound_integration_id AND i.inbound_call_id=s.inbound_call_id
   AND private.acquisition_try_normalize(p_type,i.prepared_answers->'answers'->>CASE WHEN p_type='phone' THEN 'phone' ELSE 'email' END)=p_value)
  OR (p_type='phone' AND EXISTS(SELECT 1 FROM public.tasks t WHERE t.workspace_id=s.workspace_id
   AND t.acquisition_integration_id=s.inbound_integration_id AND t.acquisition_call_id=s.inbound_call_id
   AND t.acquisition_request_kind='request_callback' AND t.acquisition_phone=p_value))))
$$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_endpoint_restricted(text,text,text) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.record_acquisition_suppression(p_id uuid,p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_reason text)
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
  IF ROW(saved.workspace_id,saved.lead_id,saved.contact_point_id,saved.channel,saved.reason,saved.actor_id)
   IS DISTINCT FROM ROW(p_workspace,p_lead,p_contact,p_channel,p_reason,auth.uid()) THEN
   RAISE EXCEPTION 'Suppression identity conflict' USING ERRCODE='23505'; END IF;
 ELSE
  INSERT INTO public.acquisition_contact_suppressions(id,workspace_id,contact_point_id,lead_id,channel,reason,actor_id)
  VALUES(p_id,p_workspace,p_contact,p_lead,p_channel,p_reason,auth.uid()) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('contact_suppression',p_id::text,'recorded',auth.uid()::text,to_jsonb(saved),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'channel',saved.channel,'reason',saved.reason,'created_at',saved.created_at);
END $$;

CREATE OR REPLACE FUNCTION private.evaluate_acquisition_eligibility(p_workspace uuid,p_lead uuid,p_contact uuid,p_channel text,p_purpose text,p_actor_type text,p_campaign uuid DEFAULT NULL)
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
  AND s.channel IN ('all',p_channel)) OR private.acquisition_inbound_endpoint_restricted(endpoint.type,endpoint.normalized_value,p_channel) INTO suppressed;
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

CREATE OR REPLACE FUNCTION private.record_acquisition_inbound_request(p_integration uuid,p_number text,p_agent text,p_agent_version integer,
 p_call text,p_request uuid,p_expected_revision integer,p_kind text,p_evidence jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; saved public.tasks%ROWTYPE;
 fingerprint text; revision integer; phone text; k text; max_length integer;
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND enabled AND provider='retell' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number OR route.agent_id IS DISTINCT FROM p_agent
  OR route.agent_version IS DISTINCT FROM p_agent_version THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_request IS NULL OR p_expected_revision IS NULL
  OR p_expected_revision NOT BETWEEN 0 AND 999999999 OR p_kind IS NULL OR p_kind NOT IN ('request_callback','request_human')
  OR p_evidence IS NULL OR jsonb_typeof(p_evidence)<>'object' OR octet_length(p_evidence::text)>8192 THEN
  RAISE EXCEPTION 'Invalid inbound request' USING ERRCODE='22023'; END IF;
 IF p_kind='request_callback' THEN
  IF (SELECT count(*) FROM jsonb_object_keys(p_evidence))<>4 OR NOT p_evidence ?& ARRAY['phone','preferred_time','purpose','requested_by_caller']
   OR p_evidence->'requested_by_caller' IS DISTINCT FROM 'true'::jsonb THEN
   RAISE EXCEPTION 'Invalid callback evidence' USING ERRCODE='22023'; END IF;
  FOREACH k IN ARRAY ARRAY['phone','preferred_time','purpose'] LOOP
   max_length:=CASE WHEN k='phone' THEN 100 ELSE 500 END;
   IF jsonb_typeof(p_evidence->k) IS DISTINCT FROM 'string' OR length(trim(p_evidence->>k))<1 OR length(p_evidence->>k)>max_length THEN
    RAISE EXCEPTION 'Invalid callback text' USING ERRCODE='22023'; END IF;
  END LOOP;
  BEGIN phone:=private.normalize_acquisition_contact('phone',p_evidence->>'phone');
  EXCEPTION WHEN SQLSTATE '22023' THEN phone:=NULL; END;
 ELSE
  IF (SELECT count(*) FROM jsonb_object_keys(p_evidence))<>3 OR NOT p_evidence ?& ARRAY['reason','details','requested_by_caller']
   OR jsonb_typeof(p_evidence->'requested_by_caller') IS DISTINCT FROM 'boolean'
   OR jsonb_typeof(p_evidence->'reason') IS DISTINCT FROM 'string'
   OR p_evidence->>'reason' NOT IN ('caller_requested','unsupported_language','failed_transfer','sensitive_situation','unable_to_complete')
   OR (p_evidence->>'reason'='caller_requested' AND p_evidence->'requested_by_caller'<>'true'::jsonb)
   OR jsonb_typeof(p_evidence->'details') IS DISTINCT FROM 'string' OR length(trim(p_evidence->>'details'))<1 OR length(p_evidence->>'details')>1000 THEN
   RAISE EXCEPTION 'Invalid escalation evidence' USING ERRCODE='22023'; END IF;
 END IF;
 -- Database fingerprint is authoritative; client hashes never grant authority.
 fingerprint:=encode(sha256(convert_to(jsonb_build_object('version','acquisition-inbound-requests-v1',
  'workspace_id',route.workspace_id,'integration_id',p_integration,'agent_id',p_agent,'agent_version',p_agent_version,
  'call_id',p_call,'request_id',p_request,'expected_revision',p_expected_revision,'kind',p_kind,'evidence',p_evidence)::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound-request:'||p_integration::text||':'||p_request::text,0));
 -- Same lock used by lifecycle receipt, serializing new intents with terminal events.
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||p_call,0));
 IF p_kind='request_callback' AND EXISTS(SELECT 1 FROM public.acquisition_contact_suppressions
  WHERE inbound_integration_id=p_integration AND inbound_call_id=p_call AND (inbound_kind='cancel_callback' OR inbound_kind='do_not_contact' AND inbound_evidence->'channels' ?| ARRAY['all','human_voice'])) THEN
  RAISE EXCEPTION 'Callback withdrawn by caller' USING ERRCODE='55000'; END IF;
 SELECT * INTO saved FROM public.tasks WHERE acquisition_integration_id=p_integration AND acquisition_request_id=p_request;
 IF FOUND THEN
  IF saved.acquisition_request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Inbound request conflict' USING ERRCODE='23505'; END IF;
  -- Confirm an existing commit even if the call has since ended. No new work.
  RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'revision',saved.acquisition_revision,'duplicate',true,'execution_authorized',false);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
    AND acquisition_event_type='call_started' AND acquisition_projection->>'call_status'='ongoing')
  OR EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration AND acquisition_call_id=p_call
    AND acquisition_event_type IN ('call_ended','call_analyzed')) THEN
  RAISE EXCEPTION 'Ongoing inbound ledger required' USING ERRCODE='55000'; END IF;
 SELECT coalesce(max(acquisition_revision),0) INTO revision FROM public.tasks WHERE acquisition_integration_id=p_integration
  AND acquisition_call_id=p_call AND acquisition_request_kind=p_kind;
 IF revision<>p_expected_revision THEN RAISE EXCEPTION 'Inbound request revision changed' USING ERRCODE='40001'; END IF;
 INSERT INTO public.tasks(title,priority,status,type,workspace_id,acquisition_integration_id,acquisition_call_id,
  acquisition_request_id,acquisition_revision,acquisition_request_kind,acquisition_evidence,acquisition_request_hash,acquisition_phone)
 VALUES('Inbound acquisition review',NULL,'acquisition_review_required','acquisition_inbound_review',route.workspace_id,p_integration,p_call,
  p_request,revision+1,p_kind,p_evidence,fingerprint,phone) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_inbound_request',saved.id::text,'recorded','inbound_tools',
  jsonb_build_object('integration_id',p_integration,'request_id',p_request,'revision',revision+1,'kind',p_kind,'request_hash',fingerprint,'execution_authorized',false),route.workspace_id);
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'revision',saved.acquisition_revision,'duplicate',false,'execution_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION private.acquisition_inbound_request_state(p_workspace uuid,p_task uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE task public.tasks%ROWTYPE; latest public.acquisition_inbound_request_reviews%ROWTYPE;
 withdrawn boolean; request_current boolean; review_current boolean:=false; active boolean;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Inbound review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO task FROM public.tasks WHERE workspace_id=p_workspace AND id=p_task;
 IF NOT FOUND THEN RAISE EXCEPTION 'Request unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_inbound_request_reviews WHERE workspace_id=p_workspace AND task_id=p_task ORDER BY sequence DESC LIMIT 1;
 withdrawn:=task.acquisition_request_kind='request_callback' AND EXISTS(SELECT 1 FROM public.acquisition_contact_suppressions
  WHERE workspace_id=p_workspace AND inbound_integration_id=task.acquisition_integration_id AND inbound_call_id=task.acquisition_call_id
   AND (inbound_kind='cancel_callback' OR inbound_kind='do_not_contact' AND inbound_evidence->'channels' ?| ARRAY['all','human_voice']));
 request_current:=NOT withdrawn AND NOT EXISTS(SELECT 1 FROM public.tasks newer WHERE newer.workspace_id=p_workspace
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
  'status',CASE WHEN withdrawn THEN 'withdrawn' WHEN NOT request_current THEN 'superseded' WHEN latest.id IS NULL THEN 'pending_review' WHEN NOT review_current THEN 'requires_review' ELSE latest.status END,
  'assigned_user_id',CASE WHEN review_current THEN latest.assigned_user_id ELSE NULL END,
  'execution_authorized',false,'contact_permission_granted',false,'checked_at',statement_timestamp());
END $$;

CREATE OR REPLACE FUNCTION private.acquisition_inbound_request_queue_v2(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20,
 p_status text DEFAULT 'all',p_assignment text DEFAULT 'all')
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE rows jsonb; more boolean; cursor_id uuid;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Inbound queue read denied' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 OR p_status IS NULL
  OR p_status NOT IN ('all','open','pending_review','assigned','on_hold','review_complete','requires_review','unassigned','withdrawn')
  OR p_assignment IS NULL OR p_assignment NOT IN ('all','mine','unassigned') THEN
  RAISE EXCEPTION 'Invalid queue bounds or filters' USING ERRCODE='22023'; END IF;
 WITH candidates AS MATERIALIZED (
  SELECT t.id,t.acquisition_integration_id AS integration_id,t.acquisition_call_id AS call_id,
   t.acquisition_request_kind AS request_kind,t.acquisition_revision AS revision,t.created_at,
   review.value->>'status' AS review_status,(review.value->>'sequence')::integer AS review_sequence,
   (review.value->>'review_current')::boolean AS review_current,(review.value->>'assigned_user_id')::uuid AS assigned_user_id
  FROM public.tasks t
  CROSS JOIN LATERAL (SELECT private.acquisition_inbound_request_state(p_workspace,t.id) AS value OFFSET 0) review
  WHERE t.workspace_id=p_workspace AND (p_after IS NULL OR t.id>p_after)
   AND NOT EXISTS(SELECT 1 FROM public.tasks newer WHERE newer.workspace_id=p_workspace
    AND newer.acquisition_integration_id=t.acquisition_integration_id AND newer.acquisition_call_id=t.acquisition_call_id
    AND newer.acquisition_request_kind=t.acquisition_request_kind AND newer.acquisition_revision>t.acquisition_revision)
   AND (p_status='all' OR p_status='open' AND review.value->>'status' NOT IN ('review_complete','withdrawn') OR review.value->>'status'=p_status)
   AND (p_assignment='all' OR p_assignment='mine' AND (review.value->>'assigned_user_id')::uuid=auth.uid()
    OR p_assignment='unassigned' AND review.value->>'assigned_user_id' IS NULL)
  ORDER BY t.id LIMIT p_limit+1
 ), page AS (SELECT * FROM candidates ORDER BY id LIMIT p_limit)
 SELECT coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY id) FROM page),'[]'::jsonb),
  (SELECT count(*)>p_limit FROM candidates),(SELECT id FROM page ORDER BY id DESC LIMIT 1)
 INTO rows,more,cursor_id;
 RETURN jsonb_build_object('workspace_id',p_workspace,'items',rows,'next_after',CASE WHEN more THEN cursor_id ELSE NULL END,
  'checked_at',statement_timestamp(),'revision_scope','latest_per_call_and_kind_at_read','review_status_available',true,
  'filters',jsonb_build_object('status',p_status,'assignment',p_assignment),'execution_authorized',false);
END $$;
COMMIT;
