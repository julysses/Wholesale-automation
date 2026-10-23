CREATE TABLE wholesale_ingest.scoring_incidents (
 job_id uuid PRIMARY KEY REFERENCES wholesale_ingest.scoring_jobs(id),kind text NOT NULL,
 first_seen_at timestamptz NOT NULL,last_seen_at timestamptz NOT NULL,resolved_at timestamptz,
 task_id uuid REFERENCES public.tasks(id)
);
ALTER TABLE wholesale_ingest.scoring_incidents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.scoring_incidents FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.scoring_incidents TO service_role;
CREATE FUNCTION wholesale_ingest.scan_scoring_at(p_now timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_id uuid; job wholesale_ingest.scoring_jobs; kind text; incident wholesale_ingest.scoring_incidents;
BEGIN
 IF p_now IS NULL THEN RAISE EXCEPTION 'Scan time required'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:scoring-monitor',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 FOR job IN SELECT * FROM wholesale_ingest.scoring_jobs
 WHERE state='review' OR (state='queued' AND created_at+interval '60 minutes'<=p_now)
 OR (state='submitted' AND claimed_at+interval '15 minutes'<=p_now)
 OR (state='received' AND received_at+interval '15 minutes'<=p_now) LOOP
  kind:=CASE job.state WHEN 'submitted' THEN 'model_outcome_unknown' WHEN 'received' THEN 'receipt_completion_overdue'
   WHEN 'queued' THEN 'scoring_queue_overdue' ELSE 'scoring_evidence_review' END;
  INSERT INTO wholesale_ingest.scoring_incidents(job_id,kind,first_seen_at,last_seen_at)
  VALUES(job.id,kind,p_now,p_now) ON CONFLICT(job_id) DO UPDATE SET kind=excluded.kind,last_seen_at=p_now,resolved_at=NULL
  RETURNING * INTO incident;
  IF incident.task_id IS NULL AND owner_id IS NOT NULL THEN
   incident.task_id:=gen_random_uuid();
   INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
   VALUES(incident.task_id,'List scoring needs review',kind||'. Scoring job '||job.id::text||'; lead '||job.lead_id::text||'. Inspect saved model evidence. Do not repeat an uncertain model call.','pending','high','follow_up',owner_id,p_now);
   UPDATE wholesale_ingest.scoring_incidents SET task_id=incident.task_id WHERE job_id=job.id;
  ELSIF incident.task_id IS NOT NULL THEN
   UPDATE public.tasks SET status='pending',description=kind||'. Scoring job '||job.id::text||'; lead '||job.lead_id::text||'. Inspect saved model evidence. Do not repeat an uncertain model call.' WHERE id=incident.task_id;
  END IF;
 END LOOP;
 UPDATE wholesale_ingest.scoring_incidents i SET resolved_at=coalesce(i.resolved_at,p_now),last_seen_at=p_now
 FROM wholesale_ingest.scoring_jobs j WHERE j.id=i.job_id AND j.state IN ('completed','obsolete') AND i.resolved_at IS NULL;
 RETURN jsonb_build_object('owner_configured',owner_id IS NOT NULL,
 'open_incidents',(SELECT coalesce(jsonb_agg(to_jsonb(i) ORDER BY first_seen_at,job_id),'[]') FROM wholesale_ingest.scoring_incidents i WHERE resolved_at IS NULL));
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.scan_scoring_at(timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.scan_scoring_at(timestamptz) TO service_role;

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
 v_summary:=v_summary||jsonb_build_object('scoring_monitor',wholesale_ingest.scan_scoring_at(now()));
 UPDATE wholesale_ingest.daily_digests SET summary=v_summary WHERE day=(v_summary->>'day')::date;
 RETURN v_summary;
END $$;
