CREATE TABLE wholesale_ingest.scoring_jobs (
 id uuid PRIMARY KEY,lead_id uuid NOT NULL REFERENCES public.leads(id),
 input_hash text NOT NULL,input_snapshot jsonb NOT NULL,requested_model text NOT NULL,prompt_version text NOT NULL,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','submitted','received','completed','review','obsolete')),
 claim_token uuid,model_version text,model_receipt text,assessment jsonb,error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),claimed_at timestamptz,received_at timestamptz,completed_at timestamptz,
 UNIQUE(lead_id,input_hash,requested_model,prompt_version)
);
CREATE UNIQUE INDEX scoring_jobs_unresolved_lead ON wholesale_ingest.scoring_jobs(lead_id)
 WHERE state IN ('queued','submitted','received','review');
ALTER TABLE wholesale_ingest.scoring_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.scoring_jobs FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.scoring_jobs TO service_role;
CREATE FUNCTION public.prepare_list_score_job(p_id uuid,p_lead uuid,p_model text) RETURNS jsonb
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
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE lead_id=p_lead
 AND ((input_hash=snapshot->>'input_hash' AND requested_model=p_model AND prompt_version='daily-list-score-v1')
 OR state IN ('queued','submitted','received','review')) ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN RETURN jsonb_build_object('blocked','existing_job','job_id',job.id,'state',job.state); END IF;
 INSERT INTO wholesale_ingest.scoring_jobs(id,lead_id,input_hash,input_snapshot,requested_model,prompt_version)
 VALUES(p_id,p_lead,snapshot->>'input_hash',snapshot->'input',p_model,'daily-list-score-v1') RETURNING * INTO job;
 RETURN jsonb_build_object('job',to_jsonb(job),'replayed',false);
END $$;
CREATE FUNCTION public.claim_list_score_job(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs; snapshot jsonb;
BEGIN
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','job_missing'); END IF;
 IF job.state<>'queued' THEN RETURN jsonb_build_object('job',to_jsonb(job),'dispatch',false); END IF;
 snapshot:=public.list_scoring_input(job.lead_id);
 IF snapshot->>'input_hash' IS DISTINCT FROM job.input_hash THEN
  UPDATE wholesale_ingest.scoring_jobs SET state='obsolete',error_code='stale_before_call' WHERE id=p_id RETURNING * INTO job;
  RETURN jsonb_build_object('job',to_jsonb(job),'dispatch',false);
 END IF;
 UPDATE wholesale_ingest.scoring_jobs SET state='submitted',claimed_at=clock_timestamp(),claim_token=gen_random_uuid()
 WHERE id=p_id RETURNING * INTO job;
 RETURN jsonb_build_object('job',to_jsonb(job),'dispatch',true);
END $$;
CREATE FUNCTION public.receive_list_score_job(p_id uuid,p_token uuid,p_model text,p_receipt text,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs;
BEGIN
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','job_missing'); END IF;
 IF p_token IS NULL OR job.claim_token IS DISTINCT FROM p_token OR job.requested_model IS DISTINCT FROM p_model
 OR coalesce(length(p_receipt),0) NOT BETWEEN 1 AND 255 OR jsonb_typeof(p_result) IS DISTINCT FROM 'object'
 OR octet_length(p_result::text)>65536 THEN RETURN jsonb_build_object('blocked','receipt_identity_mismatch'); END IF;
 IF job.assessment IS NOT NULL THEN
  IF job.model_version IS DISTINCT FROM p_model OR job.model_receipt IS DISTINCT FROM p_receipt OR job.assessment IS DISTINCT FROM p_result
  THEN RETURN jsonb_build_object('blocked','receipt_conflict'); END IF;
  RETURN jsonb_build_object('job',to_jsonb(job),'replayed',true);
 END IF;
 IF job.state<>'submitted' THEN RETURN jsonb_build_object('blocked','not_submitted'); END IF;
 UPDATE wholesale_ingest.scoring_jobs SET state='received',model_version=p_model,model_receipt=p_receipt,assessment=p_result,received_at=clock_timestamp()
 WHERE id=p_id RETURNING * INTO job;
 RETURN jsonb_build_object('job',to_jsonb(job),'replayed',false);
END $$;
CREATE FUNCTION public.complete_list_score_job(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE job wholesale_ingest.scoring_jobs; result jsonb;
BEGIN
 SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','job_missing'); END IF;
 IF job.state NOT IN ('received','completed') THEN RETURN jsonb_build_object('job',to_jsonb(job),'dispatch',false); END IF;
 result:=public.save_list_score(job.id,job.lead_id,job.input_hash,job.model_version,job.prompt_version,job.model_receipt,job.assessment);
 IF result ? 'blocked' THEN
  UPDATE wholesale_ingest.scoring_jobs SET state=CASE WHEN result->>'blocked' IN ('stale_input','no_active_signals','property_unverified') THEN 'obsolete' ELSE 'review' END,error_code=result->>'blocked'
  WHERE id=p_id RETURNING * INTO job;
  RETURN jsonb_build_object('job',to_jsonb(job),'blocked',result->>'blocked','dispatch',false);
 END IF;
 UPDATE wholesale_ingest.scoring_jobs SET state='completed',completed_at=coalesce(completed_at,clock_timestamp()) WHERE id=p_id RETURNING * INTO job;
 RETURN result||jsonb_build_object('job',to_jsonb(job),'dispatch',false);
END $$;
-- Submitted jobs never become queued again: timeouts/crashes need reconciliation.
REVOKE ALL ON FUNCTION public.prepare_list_score_job(uuid,uuid,text),public.claim_list_score_job(uuid),
 public.receive_list_score_job(uuid,uuid,text,text,jsonb),public.complete_list_score_job(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.prepare_list_score_job(uuid,uuid,text),public.claim_list_score_job(uuid),
 public.receive_list_score_job(uuid,uuid,text,text,jsonb),public.complete_list_score_job(uuid) TO service_role;
CREATE FUNCTION wholesale_ingest.protect_score_job() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.lead_id,NEW.input_hash,NEW.input_snapshot,NEW.requested_model,NEW.prompt_version,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.lead_id,OLD.input_hash,OLD.input_snapshot,OLD.requested_model,OLD.prompt_version,OLD.created_at)
 OR (OLD.claim_token IS NOT NULL AND NEW.claim_token IS DISTINCT FROM OLD.claim_token)
 OR (OLD.assessment IS NOT NULL AND ROW(NEW.assessment,NEW.model_version,NEW.model_receipt) IS DISTINCT FROM ROW(OLD.assessment,OLD.model_version,OLD.model_receipt))
 THEN RAISE EXCEPTION 'Scoring job identity and receipt are immutable'; END IF;
 IF NEW.state<>OLD.state AND NOT (
 (OLD.state='queued' AND NEW.state IN ('submitted','obsolete')) OR (OLD.state='submitted' AND NEW.state='received')
 OR (OLD.state='received' AND NEW.state IN ('completed','review','obsolete')))
 THEN RAISE EXCEPTION 'Invalid scoring job transition'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER protect_score_job BEFORE UPDATE ON wholesale_ingest.scoring_jobs FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.protect_score_job();
REVOKE ALL ON FUNCTION wholesale_ingest.protect_score_job() FROM PUBLIC,anon,authenticated;
