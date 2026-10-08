ALTER TABLE public.deal_analyses ADD COLUMN operator_inputs jsonb,
 ADD COLUMN created_by uuid REFERENCES public.profiles(id);
DROP POLICY IF EXISTS approved_write_deal_analyses ON public.deal_analyses;
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.deal_analyses FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.deal_analyses TO service_role;
CREATE FUNCTION public.save_manual_analysis(p_id uuid,p_lead uuid,p_operator uuid,p_inputs jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.deal_analyses%ROWTYPE; arv numeric; repairs numeric; fee numeric; ceiling numeric;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Operator not approved'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('analysis:'||p_id,0));
 SELECT * INTO saved FROM public.deal_analyses WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id IS DISTINCT FROM p_lead OR saved.created_by IS DISTINCT FROM p_operator
   OR saved.operator_inputs IS DISTINCT FROM p_inputs THEN RETURN jsonb_build_object('conflict',true); END IF;
  RETURN jsonb_build_object('analysis',to_jsonb(saved),'reused',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead) THEN RETURN jsonb_build_object('missing',true); END IF;
 arv:=(p_inputs->>'arv')::numeric; repairs:=(p_inputs->>'repairs')::numeric; fee:=(p_inputs->>'assignment_fee')::numeric;
 IF arv IS NULL OR repairs IS NULL OR fee IS NULL OR arv<=0 OR arv>100000000 OR repairs<0 OR repairs>100000000 OR fee<0 OR fee>100000000
  OR coalesce(p_inputs->>'condition','') NOT IN ('cosmetic','moderate','full_renovation')
  OR jsonb_typeof(p_inputs->'comps') IS DISTINCT FROM 'array'
  OR jsonb_typeof(p_inputs->'line_items') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid analysis'; END IF;
 ceiling:=arv*0.70-repairs-fee;
 INSERT INTO public.deal_analyses(id,lead_id,created_by,operator_inputs,arv_low,arv_mid,arv_high,arv_confidence,arv_comp_count,arv_notes,
 repair_tier,repair_cost_low,repair_cost_mid,repair_cost_high,assignment_fee,mao,offer_range_low,offer_range_high,is_viable,summary)
 VALUES(p_id,p_lead,p_operator,p_inputs,arv,arv,arv,'low',
 (SELECT count(*) FROM jsonb_array_elements(p_inputs->'comps') c WHERE (c->>'sale_price')::numeric>0 AND (c->>'sqft')::numeric>0),
 'Operator estimates; comparable and repair inputs retained for review.',
 CASE p_inputs->>'condition' WHEN 'cosmetic' THEN 'light' WHEN 'full_renovation' THEN 'heavy' ELSE 'moderate' END,
 repairs,repairs,repairs,fee,ceiling,greatest(0,ceiling*0.9),greatest(0,ceiling),ceiling>0,
 coalesce(nullif(p_inputs->>'summary',''),'Manual comparable and repair analysis.')) RETURNING * INTO saved;
 UPDATE public.leads SET estimated_repairs=repairs WHERE id=p_lead;
 RETURN jsonb_build_object('analysis',to_jsonb(saved),'reused',false);
END $$;
REVOKE ALL ON FUNCTION public.save_manual_analysis(uuid,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_manual_analysis(uuid,uuid,uuid,jsonb) TO service_role;
