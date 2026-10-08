-- Client reference identifies one inquiry, never an email address or person.
ALTER TABLE public.lead_form_submissions ADD COLUMN request_manifest jsonb;
COMMENT ON COLUMN public.lead_form_submissions.request_manifest IS 'Server-validated immutable request inputs for replay comparison. Null on legacy receipts; IP, user agent and server consent timestamp are excluded.';
CREATE FUNCTION public.reserve_form_submission(p_request_id uuid,p_submission jsonb,p_manifest jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE receipt public.lead_form_submissions%ROWTYPE; inserted integer;
BEGIN
 IF p_request_id IS NULL OR jsonb_typeof(p_manifest) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_submission->'raw_answers') IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Validated inquiry reference and manifest are required';
 END IF;
 INSERT INTO public.lead_form_submissions(
   id,form_id,ip_address,user_agent,utm_source,utm_medium,utm_campaign,raw_answers,
   computed_motivation_tag,computed_timeline,computed_condition,processing_status,request_manifest
 ) VALUES(
   p_request_id,(p_submission->>'form_id')::uuid,p_submission->>'ip_address',
   p_submission->>'user_agent',p_submission->>'utm_source',p_submission->>'utm_medium',
   p_submission->>'utm_campaign',p_submission->'raw_answers',
   p_submission->>'computed_motivation_tag',p_submission->>'computed_timeline',
   p_submission->>'computed_condition','pending',p_manifest
 ) ON CONFLICT(id) DO NOTHING;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 SELECT * INTO STRICT receipt FROM public.lead_form_submissions WHERE id=p_request_id;
 IF receipt.form_id IS DISTINCT FROM (p_submission->>'form_id')::uuid
    OR receipt.request_manifest IS DISTINCT FROM p_manifest THEN
   RETURN jsonb_build_object('status','conflict');
 END IF;
 RETURN jsonb_build_object('status',CASE WHEN inserted=1 THEN 'created' ELSE 'replayed' END,
    'submission_id',receipt.id,'processing_status',receipt.processing_status);
END;
$$;
REVOKE ALL ON FUNCTION public.reserve_form_submission(uuid,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_form_submission(uuid,jsonb,jsonb) TO service_role;
