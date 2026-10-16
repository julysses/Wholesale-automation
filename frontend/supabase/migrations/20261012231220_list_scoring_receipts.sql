-- Scoring is decision support only. No contact permission or outreach is created.
ALTER TABLE wholesale_ingest.lead_evaluations ADD COLUMN input_snapshot jsonb,
 ADD COLUMN model_receipt text, ADD COLUMN response_hash text;
REVOKE INSERT,UPDATE,DELETE ON wholesale_ingest.lead_evaluations FROM wholesale_worker;
REVOKE UPDATE,DELETE ON wholesale_ingest.lead_evaluations FROM service_role;
CREATE FUNCTION public.list_scoring_input(p_lead uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE property wholesale_ingest.properties; doc jsonb;
BEGIN
 SELECT * INTO property FROM wholesale_ingest.properties WHERE lead_id=p_lead;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','property_unverified'); END IF;
 SELECT jsonb_build_object('schema_version','list-score-input-v1','lead_id',p_lead,
 'as_of',(statement_timestamp() AT TIME ZONE 'America/Chicago')::date,
 'property',jsonb_build_object('id',property.id,'state',property.state,'county',property.county,
 'parcel_id',property.parcel_id,'address',property.address_std,'unit',property.unit,'is_vacant_lot',property.is_vacant_lot),
 'signals',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'list_type',s.list_type,'filed_date',s.filed_date,
 'auction_date',s.auction_date,'source_url',s.source_url,'last_run_id',s.last_run_id,'last_seen_at',s.last_seen_at) ORDER BY s.id),'[]')
 FROM wholesale_ingest.distress_signals s WHERE s.property_id=property.id AND s.active),
 'contacts',(SELECT coalesce(jsonb_agg(c.value ORDER BY c.value->>'id'),'[]') FROM (
 SELECT jsonb_build_object('id',c.id,'phone_available',c.phone IS NOT NULL,'email_available',c.email IS NOT NULL,
 'phone_type',c.phone_type,'expires_at',c.expires_at,
 'destination_hash',encode(sha256(convert_to(coalesce(c.phone,'')||':'||coalesce(c.email,''),'UTF8')),'hex')) AS value
 FROM wholesale_ingest.contacts c WHERE c.lead_id=p_lead AND c.expires_at>statement_timestamp()
 UNION ALL
 SELECT jsonb_build_object('id','crm:'||p_lead::text,'phone_available',phone<>'','email_available',email<>'','phone_type','unknown',
 'destination_hash',encode(sha256(convert_to(phone||':'||email,'UTF8')),'hex')) FROM (
 SELECT concat_ws('|',nullif(trim(to_jsonb(l)->>'owner_phone_1'),''),nullif(trim(to_jsonb(l)->>'owner_phone_2'),''),nullif(trim(to_jsonb(l)->>'owner_phone_3'),'')) phone,
 coalesce(nullif(trim(to_jsonb(l)->>'owner_email'),''),'') email FROM public.leads l WHERE l.id=p_lead
 ) crm WHERE phone<>'' OR email<>''
 ) c),
 'equity',jsonb_build_object('status','unknown','reason','Verified property value and complete secured debt evidence are unavailable'),
 'off_market','unknown','direct_to_seller','unknown',
 'score_threshold',(SELECT score_threshold FROM wholesale_ingest.settings WHERE singleton)) INTO doc;
 IF doc->>'score_threshold' IS NULL THEN RETURN jsonb_build_object('blocked','scoring_settings_missing'); END IF;
 IF jsonb_array_length(doc->'signals')=0 THEN RETURN jsonb_build_object('blocked','no_active_signals'); END IF;
 RETURN jsonb_build_object('input',doc,'input_hash',encode(sha256(convert_to(doc::text,'UTF8')),'hex'));
END $$;
CREATE FUNCTION public.save_list_score(p_id uuid,p_lead uuid,p_input_hash text,p_model text,p_prompt text,p_receipt text,p_result jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE snapshot jsonb; old wholesale_ingest.lead_evaluations; item jsonb; category text; points int;
 total int:=0; stack int; expected int; ids jsonb; ref jsonb; fingerprint text; flags jsonb; route text;
BEGIN
 IF p_id IS NULL OR p_lead IS NULL OR coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$'
 OR coalesce(length(p_model),0) NOT BETWEEN 1 AND 100 OR p_prompt IS DISTINCT FROM 'daily-list-score-v1'
 OR coalesce(length(p_receipt),0) NOT BETWEEN 1 AND 255 THEN RETURN jsonb_build_object('blocked','invalid_identity'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('list-score:'||p_lead::text,0));
 fingerprint:=encode(sha256(convert_to(p_result::text,'UTF8')),'hex');
 SELECT * INTO old FROM wholesale_ingest.lead_evaluations WHERE id=p_id OR (lead_id=p_lead AND input_hash=p_input_hash AND prompt_version=p_prompt) ORDER BY id LIMIT 1;
 IF FOUND THEN
  IF old.id IS DISTINCT FROM p_id OR old.lead_id IS DISTINCT FROM p_lead OR old.input_hash IS DISTINCT FROM p_input_hash
  OR old.model_version IS DISTINCT FROM p_model OR old.prompt_version IS DISTINCT FROM p_prompt OR old.model_receipt IS DISTINCT FROM p_receipt
  OR old.response_hash IS DISTINCT FROM fingerprint THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('evaluation',to_jsonb(old),'replayed',true,'current',public.list_scoring_input(p_lead)->>'input_hash'=p_input_hash,'outreach_authorized',false);
 END IF;
 snapshot:=public.list_scoring_input(p_lead);
 IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
 IF snapshot->>'input_hash' IS DISTINCT FROM p_input_hash THEN RETURN jsonb_build_object('blocked','stale_input'); END IF;
 snapshot:=snapshot->'input';
 SELECT count(DISTINCT value->>'list_type') INTO stack FROM jsonb_array_elements(snapshot->'signals');
 IF jsonb_typeof(p_result) IS DISTINCT FROM 'object' OR p_result-ARRAY['components','needs_to_sell']<>'{}'::jsonb
 OR jsonb_typeof(p_result->'components') IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('blocked','invalid_result'); END IF;
 IF (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_result->'components') key)
 IS DISTINCT FROM ARRAY['contactability','distress_stack','equity','need_to_sell','recency'] THEN RETURN jsonb_build_object('blocked','invalid_components'); END IF;
 FOR category,item IN SELECT key,value FROM jsonb_each(p_result->'components') LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR item-ARRAY['points','reason','evidence_ids']<>'{}'::jsonb
  OR coalesce(item->>'points','') !~ '^[0-9]{1,2}$' OR jsonb_typeof(item->'points') IS DISTINCT FROM 'number'
  OR jsonb_typeof(item->'reason') IS DISTINCT FROM 'string' OR length(trim(item->>'reason')) NOT BETWEEN 1 AND 1000
  OR jsonb_typeof(item->'evidence_ids') IS DISTINCT FROM 'array' THEN RETURN jsonb_build_object('blocked','invalid_component'); END IF;
  points:=(item->>'points')::int;
  expected:=CASE category WHEN 'distress_stack' THEN 30 WHEN 'need_to_sell' THEN 25 WHEN 'equity' THEN 20 WHEN 'contactability' THEN 15 ELSE 10 END;
  IF points>expected OR jsonb_array_length(item->'evidence_ids')>100 THEN RETURN jsonb_build_object('blocked','invalid_points'); END IF;
  IF category='equity' AND (points<>0 OR jsonb_array_length(item->'evidence_ids')<>0) THEN RETURN jsonb_build_object('blocked','equity_unknown'); END IF;
  IF category='distress_stack' AND points<>stack*30/4 THEN RETURN jsonb_build_object('blocked','stack_mismatch'); END IF;
  ids:=CASE WHEN category='contactability' THEN snapshot->'contacts' ELSE snapshot->'signals' END;
  IF category='recency' THEN
   SELECT coalesce(jsonb_agg(e),'[]') INTO ids FROM jsonb_array_elements(ids) e
   WHERE (e->>'filed_date')::date BETWEEN (snapshot->>'as_of')::date-29 AND (snapshot->>'as_of')::date;
  END IF;
  FOR ref IN SELECT value FROM jsonb_array_elements(item->'evidence_ids') LOOP
   IF jsonb_typeof(ref) IS DISTINCT FROM 'string' OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(ids) e WHERE e->'id'=ref)
   THEN RETURN jsonb_build_object('blocked','unknown_evidence'); END IF;
  END LOOP;
  IF points>0 AND jsonb_array_length(item->'evidence_ids')=0 THEN RETURN jsonb_build_object('blocked','missing_evidence'); END IF;
  total:=total+points;
 END LOOP;
 IF p_result->>'needs_to_sell' NOT IN ('unknown','inferred') OR p_result->>'needs_to_sell' IS NULL
 OR (p_result->>'needs_to_sell'='inferred' AND jsonb_array_length(p_result#>'{components,need_to_sell,evidence_ids}')=0)
 OR (p_result->>'needs_to_sell'='unknown' AND (p_result#>>'{components,need_to_sell,points}')::int<>0)
 THEN RETURN jsonb_build_object('blocked','invalid_need_assessment'); END IF;
 flags:=jsonb_build_array('equity_unknown','off_market_unknown','direct_to_seller_unknown','outreach_requires_compliance',
 CASE WHEN p_result->>'needs_to_sell'='inferred' THEN 'need_to_sell_inferred_not_confirmed' ELSE 'need_to_sell_unknown' END);
 route:=CASE WHEN total>=(snapshot->>'score_threshold')::int AND snapshot#>>'{property,is_vacant_lot}'='true' THEN 'underwrite_lot'
 WHEN total>=(snapshot->>'score_threshold')::int THEN 'review' ELSE 'nurture' END;
 INSERT INTO wholesale_ingest.lead_evaluations(id,lead_id,input_hash,model_version,prompt_version,score,reasons,flags,route,stack_count,input_snapshot,model_receipt,response_hash)
 VALUES(p_id,p_lead,p_input_hash,p_model,p_prompt,total,p_result,flags,route,stack,snapshot,p_receipt,fingerprint) RETURNING * INTO old;
 RETURN jsonb_build_object('evaluation',to_jsonb(old),'replayed',false,'current',true,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.list_scoring_input(uuid),public.save_list_score(uuid,uuid,text,text,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_scoring_input(uuid),public.save_list_score(uuid,uuid,text,text,text,text,jsonb) TO service_role;
-- The scheduled/public scan includes only evaluations matching current evidence.
CREATE OR REPLACE FUNCTION public.scan_list_pipeline() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_summary jsonb; ranked jsonb;
BEGIN
 v_summary:=wholesale_ingest.scan_at(now());
 IF v_summary->>'busy'='true' THEN RETURN v_summary; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.score DESC,t.created_at DESC,t.lead_id),'[]') INTO ranked FROM (
  SELECT latest.lead_id,latest.score,latest.reasons,latest.flags,latest.route,latest.created_at
  FROM (SELECT DISTINCT ON (lead_id) * FROM wholesale_ingest.lead_evaluations ORDER BY lead_id,created_at DESC,id DESC) latest
  WHERE latest.input_snapshot IS NOT NULL AND latest.prompt_version='daily-list-score-v1'
  AND latest.input_hash=public.list_scoring_input(latest.lead_id)->>'input_hash'
  ORDER BY latest.score DESC,latest.created_at DESC,latest.lead_id LIMIT 10
 ) t;
 v_summary:=jsonb_set(v_summary,'{top_ten}',ranked);
 UPDATE wholesale_ingest.daily_digests SET summary=v_summary WHERE day=(v_summary->>'day')::date;
 RETURN v_summary;
END $$;
