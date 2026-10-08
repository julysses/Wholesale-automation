ALTER TABLE public.deals ADD COLUMN created_by uuid REFERENCES public.profiles(id), ADD COLUMN creation_manifest jsonb;
CREATE UNIQUE INDEX deals_one_active_lead ON public.deals(lead_id) WHERE stage NOT IN ('closed','cancelled');
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.deals FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.deals TO service_role;
CREATE FUNCTION public.deal_handoff_valid(d public.deals) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT coalesce(d.stage IN ('offer_made','under_contract','marketing_to_buyers','buyer_found','assigned','closed','cancelled')
 AND length(trim(d.deal_name)) BETWEEN 1 AND 500
 AND EXISTS(SELECT 1 FROM public.profiles WHERE id=d.assigned_to AND status='approved')
 AND (d.buyer_id IS NULL OR EXISTS(SELECT 1 FROM public.buyers WHERE id=d.buyer_id))
 AND (d.contract_price IS NULL OR d.contract_price>=0) AND (d.arv IS NULL OR d.arv>=0)
 AND (d.repair_estimate IS NULL OR d.repair_estimate>=0) AND (d.assignment_fee IS NULL OR d.assignment_fee>=0)
 AND (d.buyer_price IS NULL OR d.buyer_price>=0) AND (d.earnest_money IS NULL OR d.earnest_money>=0)
 AND (d.inspection_deadline IS NULL OR d.contract_date IS NULL OR d.inspection_deadline>=d.contract_date)
 AND (d.closing_date IS NULL OR d.contract_date IS NULL OR d.closing_date>=d.contract_date)
 AND (d.actual_close_date IS NULL OR d.contract_date IS NULL OR d.actual_close_date>=d.contract_date)
 AND (d.stage NOT IN ('under_contract','marketing_to_buyers','buyer_found','assigned','closed') OR
 (d.contract_price>0 AND d.contract_date IS NOT NULL AND d.closing_date IS NOT NULL AND length(trim(d.title_company))>0 AND d.psa_doc_url LIKE 'https://%'))
 AND (d.stage NOT IN ('buyer_found','assigned','closed') OR d.buyer_id IS NOT NULL)
 AND (d.stage NOT IN ('assigned','closed') OR d.assignment_doc_url LIKE 'https://%')
 AND (d.stage<>'closed' OR d.actual_close_date IS NOT NULL),false);
$$;
REVOKE ALL ON FUNCTION public.deal_handoff_valid(public.deals) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.deal_handoff_valid(public.deals) TO service_role;
CREATE FUNCTION public.sync_deal_handoff_tasks(d public.deals) RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE item record; task_id uuid;
BEGIN
 FOR item IN SELECT * FROM (VALUES ('inspection',d.inspection_deadline),('closing',d.closing_date)) AS dates(kind,due) LOOP
  task_id:=md5('deal:'||d.id||':'||item.kind)::uuid;
  IF d.stage IN ('closed','cancelled') OR item.due IS NULL THEN
   UPDATE public.tasks SET status='cancelled' WHERE id=task_id AND status IN ('pending','in_progress');
  ELSE
   INSERT INTO public.tasks(id,title,description,type,priority,status,deal_id,lead_id,assigned_to,due_date)
   VALUES(task_id,'Review '||item.kind||' deadline — '||d.deal_name,'Confirm documents, access and responsible parties before the recorded deadline.','follow_up','high','pending',d.id,d.lead_id,d.assigned_to,
    (item.due::date+time '17:00') AT TIME ZONE 'America/Chicago')
   ON CONFLICT(id) DO UPDATE SET due_date=excluded.due_date,assigned_to=excluded.assigned_to,title=excluded.title,
    status=CASE WHEN public.tasks.status='cancelled' THEN 'pending' ELSE public.tasks.status END;
  END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION public.sync_deal_handoff_tasks(public.deals) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sync_deal_handoff_tasks(public.deals) TO service_role;
CREATE FUNCTION public.create_pipeline_deal(p_id uuid,p_operator uuid,p_payload jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.deals%ROWTYPE; proposed public.deals%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Operator not approved'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('deal-ref:'||p_id,0));
 SELECT * INTO saved FROM public.deals WHERE id=p_id;
 IF FOUND THEN
  IF saved.creation_manifest IS DISTINCT FROM p_payload OR saved.created_by IS DISTINCT FROM p_operator THEN RETURN jsonb_build_object('conflict',true); END IF;
  RETURN jsonb_build_object('deal',to_jsonb(saved),'reused',true);
 END IF;
 proposed:=jsonb_populate_record(NULL::public.deals,p_payload||jsonb_build_object('id',p_id,'created_by',p_operator,'creation_manifest',p_payload,
 'created_at',clock_timestamp(),'updated_at',clock_timestamp(),'assigned_to',coalesce(nullif(p_payload->>'assigned_to','')::uuid,p_operator)));
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=proposed.lead_id) THEN RETURN jsonb_build_object('missing',true); END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('deal-lead:'||proposed.lead_id,0));
 SELECT * INTO saved FROM public.deals WHERE lead_id=proposed.lead_id AND stage NOT IN ('closed','cancelled');
 IF FOUND THEN RETURN jsonb_build_object('existing_id',saved.id); END IF;
 IF NOT public.deal_handoff_valid(proposed) THEN RETURN jsonb_build_object('invalid',true); END IF;
 INSERT INTO public.deals SELECT proposed.* RETURNING * INTO saved;
 PERFORM public.sync_deal_handoff_tasks(saved);
 RETURN jsonb_build_object('deal',to_jsonb(saved),'reused',false);
END $$;
REVOKE ALL ON FUNCTION public.create_pipeline_deal(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.create_pipeline_deal(uuid,uuid,jsonb) TO service_role;
CREATE FUNCTION public.update_pipeline_deal(p_id uuid,p_operator uuid,p_expected timestamptz,p_patch jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.deals%ROWTYPE; proposed public.deals%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Operator not approved'; END IF;
 IF p_patch ?| ARRAY['id','lead_id','created_by','created_at','updated_at','creation_manifest'] THEN RETURN jsonb_build_object('conflict',true); END IF;
 SELECT * INTO saved FROM public.deals WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('missing',true); END IF;
 IF to_jsonb(saved) @> p_patch THEN RETURN jsonb_build_object('deal',to_jsonb(saved),'reused',true); END IF;
 IF saved.updated_at IS DISTINCT FROM p_expected THEN RETURN jsonb_build_object('conflict',true); END IF;
 proposed:=jsonb_populate_record(saved,p_patch);
 IF NOT public.deal_handoff_valid(proposed) THEN RETURN jsonb_build_object('invalid',true); END IF;
 UPDATE public.deals SET
 deal_name=proposed.deal_name,stage=proposed.stage,contract_price=proposed.contract_price,arv=proposed.arv,repair_estimate=proposed.repair_estimate,
 assignment_fee=proposed.assignment_fee,buyer_price=proposed.buyer_price,earnest_money=proposed.earnest_money,
 contract_date=proposed.contract_date,inspection_deadline=proposed.inspection_deadline,closing_date=proposed.closing_date,actual_close_date=proposed.actual_close_date,
 seller_name=proposed.seller_name,buyer_id=proposed.buyer_id,title_company=proposed.title_company,title_contact=proposed.title_contact,title_phone=proposed.title_phone,
 psa_doc_url=proposed.psa_doc_url,assignment_doc_url=proposed.assignment_doc_url,notes=proposed.notes,assigned_to=proposed.assigned_to
 WHERE id=p_id RETURNING * INTO saved;
 PERFORM public.sync_deal_handoff_tasks(saved);
 RETURN jsonb_build_object('deal',to_jsonb(saved),'reused',false);
END $$;
REVOKE ALL ON FUNCTION public.update_pipeline_deal(uuid,uuid,timestamptz,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.update_pipeline_deal(uuid,uuid,timestamptz,jsonb) TO service_role;
