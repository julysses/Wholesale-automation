-- Administrator evidence inspection is read-only and never grants dispatch.
CREATE FUNCTION public.inspect_list_scoring_job(p_operator uuid,p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs; current_input jsonb; changes jsonb; evaluation jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=p_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','job_missing'); END IF;
 current_input:=public.list_scoring_input(job.lead_id);
 SELECT coalesce(jsonb_agg(key ORDER BY key),'[]') INTO changes FROM (
  SELECT key FROM jsonb_object_keys(job.input_snapshot) key
  UNION SELECT key FROM jsonb_object_keys(coalesce(current_input->'input','{}')) key
 ) keys WHERE job.input_snapshot->key IS DISTINCT FROM current_input#>ARRAY['input',key];
 SELECT jsonb_build_object('id',e.id,'score',e.score,'route',e.route,'flags',e.flags,'created_at',e.created_at) INTO evaluation
 FROM wholesale_ingest.lead_evaluations e WHERE e.id=job.id;
 RETURN jsonb_build_object('job',jsonb_build_object('id',job.id,'lead_id',job.lead_id,'state',job.state,
 'requested_model',job.requested_model,'model_version',job.model_version,'prompt_version',job.prompt_version,
 'model_receipt',job.model_receipt,'input_hash',job.input_hash,'input_snapshot',job.input_snapshot,'assessment',job.assessment,
 'error_code',job.error_code,'created_at',job.created_at,'claimed_at',job.claimed_at,'received_at',job.received_at,'completed_at',job.completed_at),
 'freshness',jsonb_build_object('current',coalesce(current_input->>'input_hash'=job.input_hash,false),
 'blocked',current_input->>'blocked','input_hash',current_input->>'input_hash','changed_sections',changes),
 'evaluation',evaluation,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.inspect_list_scoring_job(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.inspect_list_scoring_job(uuid,uuid) TO service_role;
