CREATE OR REPLACE FUNCTION public.deal_handoff_valid(d public.deals) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
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
 (d.contract_price>0 AND d.contract_date IS NOT NULL AND d.contract_date<=(now() AT TIME ZONE 'America/Chicago')::date AND d.closing_date IS NOT NULL AND length(trim(d.title_company))>0 AND d.psa_doc_url LIKE 'https://%'))
 AND (d.stage NOT IN ('buyer_found','assigned','closed') OR d.buyer_id IS NOT NULL)
 AND (d.stage NOT IN ('assigned','closed') OR d.assignment_doc_url LIKE 'https://%')
 AND (d.stage<>'closed' OR d.actual_close_date IS NOT NULL AND d.actual_close_date<=(now() AT TIME ZONE 'America/Chicago')::date),false);
$$;

CREATE OR REPLACE FUNCTION public.update_pipeline_deal(p_id uuid,p_operator uuid,p_expected timestamptz,p_patch jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.deals%ROWTYPE; proposed public.deals%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Operator not approved'; END IF;
 IF p_patch ?| ARRAY['id','lead_id','created_by','created_at','updated_at','creation_manifest'] THEN RETURN jsonb_build_object('conflict',true); END IF;
 SELECT * INTO saved FROM public.deals WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('missing',true); END IF;
 IF to_jsonb(saved) @> p_patch THEN RETURN jsonb_build_object('deal',to_jsonb(saved),'reused',true); END IF;
 IF saved.updated_at IS DISTINCT FROM p_expected THEN RETURN jsonb_build_object('conflict',true); END IF;
 proposed:=jsonb_populate_record(saved,p_patch);
 IF proposed.stage NOT IN ('closed','cancelled') AND EXISTS(SELECT 1 FROM public.deals WHERE lead_id=proposed.lead_id AND id<>p_id AND stage NOT IN ('closed','cancelled')) THEN
  RETURN jsonb_build_object('existing_id',(SELECT id FROM public.deals WHERE lead_id=proposed.lead_id AND id<>p_id AND stage NOT IN ('closed','cancelled') LIMIT 1)); END IF;
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

CREATE OR REPLACE FUNCTION public.sync_deal_handoff_tasks(d public.deals) RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
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
    status=CASE WHEN public.tasks.status='cancelled' OR public.tasks.due_date IS DISTINCT FROM excluded.due_date THEN 'pending' ELSE public.tasks.status END,
    description=CASE WHEN public.tasks.due_date IS DISTINCT FROM excluded.due_date THEN public.tasks.description||E'\nDeadline revised from '||coalesce(public.tasks.due_date::text,'unset')||'; prior completion: '||coalesce(public.tasks.completed_at::text,'not completed') ELSE public.tasks.description END,
    completed_at=CASE WHEN public.tasks.status='cancelled' OR public.tasks.due_date IS DISTINCT FROM excluded.due_date THEN NULL ELSE public.tasks.completed_at END;
  END IF;
 END LOOP;
END $$;
