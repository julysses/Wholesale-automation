ALTER TABLE wholesale_ingest.settings ADD COLUMN score_settings_version integer NOT NULL DEFAULT 1 CHECK(score_settings_version>0);
CREATE TABLE wholesale_ingest.scoring_operator_events (
 id uuid PRIMARY KEY,operator_id uuid NOT NULL REFERENCES public.profiles(id),
 action text NOT NULL CHECK(action IN ('threshold','complete_received')),payload jsonb NOT NULL,result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE wholesale_ingest.scoring_operator_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.scoring_operator_events FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT ON wholesale_ingest.scoring_operator_events TO service_role;
CREATE FUNCTION public.list_scoring_operations(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('settings',(SELECT jsonb_build_object('score_threshold',score_threshold,'version',score_settings_version) FROM wholesale_ingest.settings WHERE singleton),
 'open_count',(SELECT count(*) FROM wholesale_ingest.scoring_jobs WHERE state IN ('queued','submitted','received','review')),
 'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(j) ORDER BY j.created_at,j.id),'[]') FROM (
 SELECT j.id,j.lead_id,j.state,j.requested_model,j.created_at,j.claimed_at,j.received_at,j.error_code,i.kind AS incident,i.task_id
 FROM wholesale_ingest.scoring_jobs j LEFT JOIN wholesale_ingest.scoring_incidents i ON i.job_id=j.id AND i.resolved_at IS NULL
 WHERE j.state IN ('queued','submitted','received','review') ORDER BY j.created_at,j.id LIMIT 50 OFFSET p_offset) j),
 'recent_actions',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.created_at DESC,e.id DESC),'[]') FROM (
 SELECT id,operator_id,action,payload,result,created_at FROM wholesale_ingest.scoring_operator_events ORDER BY created_at DESC,id DESC LIMIT 20) e));
END $$;
CREATE FUNCTION public.apply_list_scoring_operation(p_id uuid,p_operator uuid,p_action text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE event wholesale_ingest.scoring_operator_events; config wholesale_ingest.settings; job wholesale_ingest.scoring_jobs; response jsonb; result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_action NOT IN ('threshold','complete_received') OR p_action IS NULL OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('blocked','invalid_action'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('scoring-operator:'||p_id::text,0));
 SELECT * INTO event FROM wholesale_ingest.scoring_operator_events WHERE id=p_id;
 IF FOUND THEN
  IF event.operator_id IS DISTINCT FROM p_operator OR event.action IS DISTINCT FROM p_action OR event.payload IS DISTINCT FROM p_payload THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('event',to_jsonb(event),'replayed',true);
 END IF;
 IF p_action='threshold' THEN
  IF p_payload-ARRAY['expected_version','score_threshold']<>'{}'::jsonb
  OR jsonb_typeof(p_payload->'expected_version') IS DISTINCT FROM 'number' OR coalesce(p_payload->>'expected_version','') !~ '^[1-9][0-9]{0,8}$'
  OR jsonb_typeof(p_payload->'score_threshold') IS DISTINCT FROM 'number' OR coalesce(p_payload->>'score_threshold','') !~ '^[0-9]{1,3}$'
  OR (p_payload->>'score_threshold')::int>100 THEN RETURN jsonb_build_object('blocked','invalid_threshold'); END IF;
  SELECT * INTO config FROM wholesale_ingest.settings WHERE singleton FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('blocked','settings_missing'); END IF;
  IF config.score_settings_version<>(p_payload->>'expected_version')::int THEN RETURN jsonb_build_object('blocked','version_conflict'); END IF;
  UPDATE wholesale_ingest.settings SET score_threshold=(p_payload->>'score_threshold')::int,score_settings_version=score_settings_version+1 WHERE singleton RETURNING * INTO config;
  result:=jsonb_build_object('score_threshold',config.score_threshold,'version',config.score_settings_version);
 ELSE
  IF p_payload-ARRAY['job_id']<>'{}'::jsonb OR coalesce(p_payload->>'job_id','') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN RETURN jsonb_build_object('blocked','invalid_job'); END IF;
  SELECT * INTO job FROM wholesale_ingest.scoring_jobs WHERE id=(p_payload->>'job_id')::uuid FOR UPDATE;
  IF NOT FOUND OR job.state NOT IN ('received','completed') THEN RETURN jsonb_build_object('blocked','saved_response_required'); END IF;
  response:=public.complete_list_score_job(job.id);
  result:=jsonb_build_object('job_id',job.id,'state',response#>>'{job,state}','evaluation_id',response#>>'{evaluation,id}','blocked',response->>'blocked');
 END IF;
 INSERT INTO wholesale_ingest.scoring_operator_events(id,operator_id,action,payload,result) VALUES(p_id,p_operator,p_action,p_payload,result) RETURNING * INTO event;
 RETURN jsonb_build_object('event',to_jsonb(event),'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.list_scoring_operations(uuid,integer),public.apply_list_scoring_operation(uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_scoring_operations(uuid,integer),public.apply_list_scoring_operation(uuid,uuid,text,jsonb) TO service_role;
