CREATE OR REPLACE FUNCTION public.launch_monitor_findings()
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
 WHERE ((m.status IN ('attempting','submitting','unknown','failed') AND m.created_at<now()-interval '15 minutes')
 OR (m.status='accepted' AND m.created_at<now()-interval '24 hours'))
 AND NOT EXISTS(SELECT 1 FROM public.email_delivery_events e WHERE e.message_id=m.id AND e.recipient=m.recipient
 AND e.event IN ('delivered','unsubscribe','group_unsubscribe'))
 OR (m.created_at<now()-interval '15 minutes' AND EXISTS(SELECT 1 FROM public.email_delivery_events e
 WHERE e.message_id=m.id AND e.recipient=m.recipient AND e.event IN ('bounce','dropped','spamreport')))
 UNION ALL SELECT 'appointment',a.id,a.lead_id,a.scheduled_at FROM public.appointments a
 WHERE a.status IN ('scheduled','confirmed') AND a.scheduled_at<now()-interval '1 day';
$$;
