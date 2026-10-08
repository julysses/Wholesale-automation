ALTER TABLE public.appointments ADD COLUMN calendar_sync text NOT NULL DEFAULT 'not_configured'
 CHECK (calendar_sync IN ('not_configured','not_supported','failed','synced'));
-- Active bookings, including overdue ones, need an explicit recorded outcome.
CREATE UNIQUE INDEX appointments_active_slot ON public.appointments(lead_id,scheduled_at)
 WHERE status IN ('scheduled','confirmed');
DROP POLICY IF EXISTS approved_write_appointments ON public.appointments;
REVOKE ALL ON public.appointments FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.appointments TO authenticated;
GRANT SELECT,INSERT,UPDATE ON public.appointments TO service_role;
REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.appointments FROM service_role;

CREATE FUNCTION public.book_appointment(p_id uuid,p_lead uuid,p_at timestamptz,p_type text,p_notes text,p_operator uuid,p_calendar text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.appointments%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN
  RAISE EXCEPTION 'Operator not approved'; END IF;
 IF p_type NOT IN ('phone','in_person','video') OR p_calendar NOT IN ('not_configured','not_supported') OR length(coalesce(p_notes,''))>4000 THEN
  RAISE EXCEPTION 'Invalid appointment'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('appointment:'||p_lead,0));
 SELECT * INTO saved FROM public.appointments WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id IS DISTINCT FROM p_lead OR saved.scheduled_at IS DISTINCT FROM p_at
   OR saved.appointment_type IS DISTINCT FROM p_type OR coalesce(saved.notes,'')<>coalesce(p_notes,'')
   OR saved.created_by IS DISTINCT FROM p_operator THEN RETURN jsonb_build_object('conflict',true); END IF;
  RETURN jsonb_build_object('appointment',to_jsonb(saved),'reused',true);
 END IF;
 SELECT * INTO saved FROM public.appointments WHERE lead_id=p_lead AND scheduled_at=p_at AND status IN ('scheduled','confirmed');
 IF FOUND THEN
  IF saved.appointment_type<>p_type OR coalesce(saved.notes,'')<>coalesce(p_notes,'') THEN RETURN jsonb_build_object('conflict',true); END IF;
  RETURN jsonb_build_object('appointment',to_jsonb(saved),'reused',true);
 END IF;
 IF p_at<=now() OR NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead) THEN
  RETURN jsonb_build_object('invalid',true); END IF;
 INSERT INTO public.appointments(id,lead_id,scheduled_at,appointment_type,notes,created_by,source,calendar_sync)
 VALUES(p_id,p_lead,p_at,p_type,nullif(p_notes,''),p_operator,'manual',p_calendar) RETURNING * INTO saved;
 RETURN jsonb_build_object('appointment',to_jsonb(saved),'reused',false);
END $$;
REVOKE ALL ON FUNCTION public.book_appointment(uuid,uuid,timestamptz,text,text,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.book_appointment(uuid,uuid,timestamptz,text,text,uuid,text) TO service_role;

CREATE FUNCTION public.transition_appointment(p_id uuid,p_expected text,p_next text,p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved public.appointments%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Operator not approved'; END IF;
 SELECT * INTO saved FROM public.appointments WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('missing',true); END IF;
 IF p_next NOT IN ('confirmed','completed','no_show','cancelled') THEN RETURN jsonb_build_object('conflict',true); END IF;
 IF saved.status=p_next THEN RETURN jsonb_build_object('appointment',to_jsonb(saved),'reused',true); END IF;
 IF saved.status<>p_expected OR saved.status NOT IN ('scheduled','confirmed')
  OR (p_next IN ('completed','no_show') AND saved.scheduled_at>now()) THEN
  RETURN jsonb_build_object('conflict',true); END IF;
 UPDATE public.appointments SET status=p_next WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('appointment',to_jsonb(saved));
END $$;
REVOKE ALL ON FUNCTION public.transition_appointment(uuid,text,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.transition_appointment(uuid,text,text,uuid) TO service_role;
