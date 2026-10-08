CREATE TABLE public.launch_monitor_incidents(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),category text NOT NULL,reference uuid NOT NULL,
 lead_id uuid REFERENCES public.leads(id),first_seen timestamptz NOT NULL DEFAULT now(),
 resolved_at timestamptz,UNIQUE(category,reference));
ALTER TABLE public.launch_monitor_incidents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.launch_monitor_incidents FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.launch_monitor_incidents TO service_role;
CREATE INDEX launch_monitor_open ON public.launch_monitor_incidents(first_seen) WHERE resolved_at IS NULL;
CREATE INDEX intake_monitor_pending ON public.lead_form_submissions(created_at) WHERE processing_status<>'processed';

CREATE FUNCTION public.launch_monitor_findings()
RETURNS TABLE(category text,reference uuid,lead_id uuid,created_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT 'intake',s.id,s.lead_id,s.created_at FROM public.lead_form_submissions s
 WHERE s.processing_status<>'processed' AND s.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'webhook',j.id,NULL::uuid,j.created_at FROM public.webhook_jobs j
 WHERE j.status IN ('pending','processing','failed') AND j.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'sms',s.id,s.lead_id,s.created_at FROM public.sms_events s
 WHERE s.direction='outbound' AND s.provider='twilio' AND NOT (coalesce(s.raw_payload,'{}') ? 'MessageSid')
 AND ((s.status IN ('submitting','unknown','failed','undelivered') AND s.created_at<now()-interval '15 minutes')
 OR (s.status IN ('accepted','sent','queued') AND s.created_at<now()-interval '24 hours'))
 UNION ALL SELECT 'call',c.id,c.lead_id,c.created_at FROM public.retell_call_requests c
 WHERE c.status<>'completed' AND c.created_at<now()-interval '15 minutes'
 UNION ALL SELECT 'nurture',j.id,j.lead_id,j.created_at FROM public.sms_nurture_jobs j
 WHERE j.status='review' OR (j.status='processing' AND j.claimed_at<now()-interval '15 minutes')
 OR (j.status='queued' AND j.due_at<now()-interval '1 day')
 UNION ALL SELECT 'email',m.id,NULL::uuid,m.created_at FROM public.email_messages m
 WHERE (m.status IN ('submitting','unknown','failed') AND m.created_at<now()-interval '15 minutes')
 OR (m.status='accepted' AND m.created_at<now()-interval '24 hours')
 UNION ALL SELECT 'appointment',a.id,a.lead_id,a.scheduled_at FROM public.appointments a
 WHERE a.status IN ('scheduled','confirmed') AND a.scheduled_at<now()-interval '1 day';
$$;
REVOKE ALL ON FUNCTION public.launch_monitor_findings() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.launch_monitor_findings() TO service_role;

CREATE FUNCTION public.launch_monitor_snapshot() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
 'database',true,'intake', (SELECT count(*)=2 FROM public.lead_form_configs WHERE slug IN ('hilltop-home-co','the-jays-dallas') AND active),
 'owner',EXISTS(SELECT 1 FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value WHERE a.key='lead_owner_user_id' AND p.status='approved'),
 'aged',coalesce((SELECT jsonb_object_agg(category,total) FROM (SELECT category,count(*) AS total FROM public.launch_monitor_findings() GROUP BY category) findings),'{}'::jsonb),
 'open_incidents',(SELECT count(*) FROM public.launch_monitor_incidents WHERE resolved_at IS NULL));
$$;
REVOKE ALL ON FUNCTION public.launch_monitor_snapshot() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.launch_monitor_snapshot() TO service_role;

CREATE FUNCTION public.scan_launch_monitor() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner uuid; issue record; created_count int:=0; resolved_count int:=0; task_id uuid;
BEGIN
 IF NOT pg_catalog.pg_try_advisory_xact_lock(pg_catalog.hashtextextended('wholesaleos:launch-monitor',0)) THEN
  RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved';
 IF owner IS NULL THEN RAISE EXCEPTION 'Approved incident owner unavailable'; END IF;
 UPDATE public.launch_monitor_incidents i SET resolved_at=now() WHERE i.resolved_at IS NULL
 AND NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() f WHERE f.category=i.category AND f.reference=i.reference);
 GET DIAGNOSTICS resolved_count=ROW_COUNT;
 FOR issue IN
  INSERT INTO public.launch_monitor_incidents(category,reference,lead_id)
  SELECT f.category,f.reference,f.lead_id FROM public.launch_monitor_findings() f
  LEFT JOIN public.launch_monitor_incidents i ON i.category=f.category AND i.reference=f.reference
  WHERE i.id IS NULL ORDER BY f.created_at LIMIT 50
  ON CONFLICT(category,reference) DO NOTHING RETURNING *
 LOOP
  task_id:=CASE WHEN issue.category='intake' THEN issue.reference ELSE issue.id END;
  INSERT INTO public.tasks(id,title,description,priority,status,type,lead_id,assigned_to,due_date)
  VALUES(task_id,'Review stalled '||issue.category||' processing',
    'Launch monitor reference: '||issue.reference||'. Reconcile the stored receipt/provider outcome. Do not resend uncertain outreach or replay seller contact.',
    'high','pending','follow_up',issue.lead_id,owner,now()) ON CONFLICT(id) DO NOTHING;
  INSERT INTO public.app_notifications(id,recipient_id,type,title,body,action_url,action_label,lead_id,metadata)
  VALUES(issue.id,owner,'system','Stalled '||issue.category||' needs review',
    'An aged receipt or unfinished outcome needs owner review. Open the assigned task; no outreach was replayed.',
    '/tasks','Review tasks',issue.lead_id,jsonb_build_object('integration_failure',true,'launch_monitor',true,'category',issue.category,'reference',issue.reference))
  ON CONFLICT(id) DO NOTHING;
  created_count:=created_count+1;
 END LOOP;
 RETURN jsonb_build_object('created',created_count,'resolved',resolved_count,'snapshot',public.launch_monitor_snapshot());
END $$;
REVOKE ALL ON FUNCTION public.scan_launch_monitor() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.scan_launch_monitor() TO service_role;
