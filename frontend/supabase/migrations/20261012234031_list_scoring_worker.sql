-- Preserve obsolete attempts as history while permitting current-input work.
DO $$ DECLARE name text; BEGIN
 SELECT c.conname INTO STRICT name FROM pg_constraint c WHERE c.conrelid='wholesale_ingest.scoring_jobs'::regclass AND c.contype='u'
 AND (SELECT array_agg(a.attname::text ORDER BY k.ord) FROM unnest(c.conkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num)
 =ARRAY['lead_id','input_hash','requested_model','prompt_version'];
 EXECUTE format('ALTER TABLE wholesale_ingest.scoring_jobs DROP CONSTRAINT %I',name);
END $$;
CREATE UNIQUE INDEX scoring_jobs_current_identity ON wholesale_ingest.scoring_jobs(lead_id,input_hash,requested_model,prompt_version) WHERE state<>'obsolete';
CREATE OR REPLACE FUNCTION public.prepare_list_score_job(p_id uuid,p_lead uuid,p_model text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs; snapshot jsonb;
BEGIN
 IF p_id IS NULL OR p_lead IS NULL OR coalesce(length(p_model),0) NOT BETWEEN 1 AND 100 THEN RETURN jsonb_build_object('blocked','invalid_identity'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('score-job-id:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('score-job-lead:'||p_lead::text,0));
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=p_id;
 IF FOUND THEN
  IF job.lead_id<>p_lead OR job.requested_model<>p_model THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('job',to_jsonb(job),'replayed',true);
 END IF;
 snapshot:=public.list_scoring_input(p_lead);
 IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE lead_id=p_lead AND state<>'obsolete'
 AND ((input_hash=snapshot->>'input_hash' AND requested_model=p_model AND prompt_version='daily-list-score-v1')
 OR state IN ('queued','submitted','received','review')) ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN RETURN jsonb_build_object('blocked','existing_job','job_id',job.id,'state',job.state); END IF;
 INSERT INTO wholesale_ingest.scoring_jobs(id,lead_id,input_hash,input_snapshot,requested_model,prompt_version)
 VALUES(p_id,p_lead,snapshot->>'input_hash',snapshot->'input',p_model,'daily-list-score-v1') RETURNING * INTO job;
 RETURN jsonb_build_object('job',to_jsonb(job),'replayed',false);
END $$;
CREATE FUNCTION public.next_list_scoring_jobs(p_model text,p_limit integer DEFAULT 5) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs; candidate record; prepared jsonb; jobs jsonb:='[]'; ids uuid[]:='{}';
BEGIN
 IF coalesce(length(p_model),0) NOT BETWEEN 1 AND 100 OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 10 THEN RAISE EXCEPTION 'Invalid worker configuration'; END IF;
 -- Completing received evidence precedes every new paid model request.
 FOR job IN SELECT * FROM wholesale_ingest.scoring_jobs WHERE state='received' OR (state='queued' AND requested_model=p_model)
 ORDER BY CASE WHEN state='received' THEN 0 ELSE 1 END,created_at,id LIMIT p_limit LOOP
  jobs:=jobs||jsonb_build_array(jsonb_build_object('id',job.id,'lead_id',job.lead_id,'requested_model',job.requested_model,'state',job.state));
  ids:=array_append(ids,job.id);
 END LOOP;
 IF jsonb_array_length(jobs)>=p_limit THEN RETURN jsonb_build_object('jobs',jobs); END IF;
 FOR candidate IN
  SELECT p.lead_id,s.snapshot FROM wholesale_ingest.properties p
  CROSS JOIN LATERAL (SELECT public.list_scoring_input(p.lead_id) snapshot) s
  WHERE p.lead_id IS NOT NULL AND NOT (s.snapshot ? 'blocked')
  AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.scoring_jobs j WHERE j.lead_id=p.lead_id AND j.state IN ('queued','submitted','received','review'))
  AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.lead_evaluations e WHERE e.lead_id=p.lead_id AND e.input_hash=s.snapshot->>'input_hash' AND e.prompt_version='daily-list-score-v1' AND e.input_snapshot IS NOT NULL)
  ORDER BY p.created_at,p.id LIMIT (p_limit-jsonb_array_length(jobs)) LOOP
  prepared:=public.prepare_list_score_job(gen_random_uuid(),candidate.lead_id,p_model);
  IF prepared ? 'job' THEN job:=jsonb_populate_record(NULL::wholesale_ingest.scoring_jobs,prepared->'job');
  ELSIF prepared->>'blocked'='existing_job' THEN SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=(prepared->>'job_id')::uuid;
  ELSE CONTINUE;
  END IF;
  IF job.id IS NOT NULL AND NOT(job.id=ANY(ids)) AND (job.state='received' OR (job.state='queued' AND job.requested_model=p_model)) THEN
   jobs:=jobs||jsonb_build_array(jsonb_build_object('id',job.id,'lead_id',job.lead_id,'requested_model',job.requested_model,'state',job.state));
   ids:=array_append(ids,job.id);
  END IF;
 END LOOP;
 RETURN jsonb_build_object('jobs',jobs);
END $$;
REVOKE ALL ON FUNCTION public.next_list_scoring_jobs(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.next_list_scoring_jobs(text,integer) TO service_role;
