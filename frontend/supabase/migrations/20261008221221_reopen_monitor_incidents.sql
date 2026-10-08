CREATE OR REPLACE FUNCTION public.scan_launch_monitor() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner uuid; finding record; issue uuid; prior_resolved timestamptz; alert_id uuid; task_id uuid;
 created_count int:=0; resolved_count int:=0;
BEGIN
 IF NOT pg_catalog.pg_try_advisory_xact_lock(pg_catalog.hashtextextended('wholesaleos:launch-monitor',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value WHERE a.key='lead_owner_user_id' AND p.status='approved';
 IF owner IS NULL THEN RAISE EXCEPTION 'Approved incident owner unavailable'; END IF;
 UPDATE public.launch_monitor_incidents i SET resolved_at=now() WHERE i.resolved_at IS NULL
 AND NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() f WHERE f.category=i.category AND f.reference=i.reference);
 GET DIAGNOSTICS resolved_count=ROW_COUNT;
 FOR finding IN SELECT f.* FROM public.launch_monitor_findings() f
 LEFT JOIN public.launch_monitor_incidents i ON i.category=f.category AND i.reference=f.reference
 WHERE i.id IS NULL OR i.resolved_at IS NOT NULL ORDER BY f.created_at LIMIT 50
 LOOP
  SELECT id,resolved_at INTO issue,prior_resolved FROM public.launch_monitor_incidents
   WHERE category=finding.category AND reference=finding.reference;
  IF issue IS NULL THEN
   INSERT INTO public.launch_monitor_incidents(category,reference,lead_id)
    VALUES(finding.category,finding.reference,finding.lead_id) RETURNING id INTO issue;
   alert_id:=issue;
   task_id:=CASE WHEN finding.category='intake' THEN finding.reference ELSE issue END;
  ELSE
   UPDATE public.launch_monitor_incidents SET resolved_at=NULL WHERE id=issue;
   alert_id:=gen_random_uuid(); task_id:=alert_id;
  END IF;
  INSERT INTO public.tasks(id,title,description,priority,status,type,lead_id,assigned_to,due_date)
  VALUES(task_id,'Review stalled '||finding.category||' processing',
   'Launch monitor reference: '||finding.reference||'. Reconcile the stored receipt/provider outcome. Do not resend uncertain outreach or replay seller contact.',
   'high','pending','follow_up',finding.lead_id,owner,now()) ON CONFLICT(id) DO NOTHING;
  INSERT INTO public.app_notifications(id,recipient_id,type,title,body,action_url,action_label,lead_id,metadata)
  VALUES(alert_id,owner,'system','Stalled '||finding.category||' needs review',
   'An aged receipt or unfinished outcome needs owner review. Open the assigned task; no outreach was replayed.',
   '/tasks','Review tasks',finding.lead_id,jsonb_build_object('integration_failure',true,'launch_monitor',true,'incident_id',issue,'category',finding.category,'reference',finding.reference))
  ON CONFLICT(id) DO NOTHING;
  created_count:=created_count+1;
 END LOOP;
 RETURN jsonb_build_object('created',created_count,'resolved',resolved_count,'snapshot',public.launch_monitor_snapshot());
END $$;
