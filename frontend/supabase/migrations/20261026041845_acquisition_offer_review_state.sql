-- Dashboard projections are fresh reads, never reusable execution permission.
BEGIN;
CREATE INDEX acquisition_offer_workspace_id_idx ON public.offer_recommendations(workspace_id,id) WHERE workspace_id IS NOT NULL;

CREATE FUNCTION private.acquisition_offer_review_state(p_workspace uuid,p_offer uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE offer public.offer_recommendations%ROWTYPE; event public.acquisition_offer_events%ROWTYPE;
 analysis public.deal_analyses%ROWTYPE; current_revision integer; caller_role text; active boolean;
 blockers text[]:=ARRAY[]::text[]; actions text[]:=ARRAY[]::text[]; current_analysis boolean;
BEGIN
 caller_role:=private.acquisition_role(p_workspace);
 IF coalesce(caller_role,'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 SELECT * INTO offer FROM public.offer_recommendations WHERE id=p_offer AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Offer unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO event FROM public.acquisition_offer_events WHERE offer_id=p_offer ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO analysis FROM public.deal_analyses WHERE id=offer.deal_analysis_id AND workspace_id=p_workspace AND lead_id=offer.lead_id;
 SELECT max(acquisition_revision) INTO current_revision FROM public.deal_analyses WHERE workspace_id=p_workspace AND lead_id=offer.lead_id;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 current_analysis:=coalesce(analysis.acquisition_status='calculated' AND analysis.acquisition_revision=current_revision AND analysis.property_id IS NOT NULL,false);
 IF NOT current_analysis THEN blockers:=array_append(blockers,'UNDERWRITING_CHANGED_OR_UNAVAILABLE'); END IF;
 IF active IS DISTINCT FROM true THEN blockers:=array_append(blockers,'ACQUISITION_ACTIVATION_DISABLED'); END IF;
 IF event.status IS DISTINCT FROM 'amount_approved' THEN blockers:=array_append(blockers,'AMOUNT_NOT_APPROVED');
 ELSE
  IF NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
    WHERE m.workspace_id=p_workspace AND m.user_id=event.actor_id AND m.status='active' AND m.role IN ('owner','admin')
     AND p.status='approved' AND m.updated_at<=event.created_at) THEN
   blockers:=array_append(blockers,'APPROVER_AUTHORITY_CHANGED');
  END IF;
 END IF;
 IF event.status='proposed' THEN
  actions:=array_append(actions,'withdrawn');
  IF caller_role IN ('owner','admin') THEN
   actions:=array_append(actions,'rejected');
   IF active AND current_analysis THEN actions:=array_append(actions,'amount_approved'); END IF;
  END IF;
 ELSIF event.status='amount_approved' AND caller_role IN ('owner','admin') THEN actions:=array_append(actions,'approval_revoked');
 END IF;
 RETURN jsonb_build_object('offer_id',offer.id,'workspace_id',p_workspace,'lead_id',offer.lead_id,'property_id',analysis.property_id,
  'analysis_id',offer.deal_analysis_id,'analysis_revision',analysis.acquisition_revision,'latest_analysis_revision',current_revision,
  'case',offer.acquisition_case,'amount',offer.target_offer,'ceiling',offer.ceiling_offer,'proposal_note',offer.proposal_note,
  'proposed_at',offer.generated_at,'latest_event_id',event.id,'sequence',event.sequence,'historical_status',event.status,
  'reviewed_by',CASE WHEN event.status='amount_approved' THEN event.actor_id ELSE NULL END,
  'reviewed_at',CASE WHEN event.status='amount_approved' THEN event.created_at ELSE NULL END,
  'amount_approval_current',cardinality(blockers)=0,'amount_review_blockers',to_jsonb(blockers),'available_review_actions',to_jsonb(actions),
  'binding_offer',false,'transmission_authorized',false,'execution_authorization',NULL,
  'transmission_blockers',jsonb_build_array('FINAL_DOCUMENT_APPROVAL_REQUIRED','APPROVAL_FRESHNESS_POLICY_REQUIRED','FRESH_OUTREACH_AUTHORIZATION_REQUIRED'),
  'checked_at',statement_timestamp());
END $$;

CREATE FUNCTION private.acquisition_offer_review_queue(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace offer access required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Invalid review page size' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(private.acquisition_offer_review_state(p_workspace,page.id) ORDER BY page.id),'[]'::jsonb) INTO result
 FROM (SELECT id FROM public.offer_recommendations WHERE workspace_id=p_workspace AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit) page;
 RETURN jsonb_build_object('items',result,'next_after',CASE WHEN jsonb_array_length(result)=p_limit THEN result->-1->>'offer_id' ELSE NULL END,
  'ordering','offer_id','transmission_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_offer_review_state(uuid,uuid),private.acquisition_offer_review_queue(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_offer_review_state(uuid,uuid),private.acquisition_offer_review_queue(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.acquisition_offer_review_state(p_workspace uuid,p_offer uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_offer_review_state(p_workspace,p_offer) $$;
CREATE FUNCTION public.acquisition_offer_review_queue(p_workspace uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_offer_review_queue(p_workspace,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION public.acquisition_offer_review_state(uuid,uuid),public.acquisition_offer_review_queue(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_offer_review_state(uuid,uuid),public.acquisition_offer_review_queue(uuid,uuid,integer) TO authenticated;
COMMIT;
