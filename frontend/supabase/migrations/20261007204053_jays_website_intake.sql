-- Service-only transaction: receipt -> lead -> assigned follow-up task.
-- Locking the receipt makes concurrent recovery idempotent without rewriting leads.
CREATE OR REPLACE FUNCTION public.finalize_form_submission(p_submission_id uuid, p_lead jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  receipt public.lead_form_submissions%ROWTYPE;
  candidate public.leads%ROWTYPE;
  saved_id uuid;
  owner_id uuid;
  created boolean := false;
BEGIN
  SELECT * INTO STRICT receipt FROM public.lead_form_submissions
    WHERE id = p_submission_id FOR UPDATE;
  SELECT value::uuid INTO owner_id FROM public.app_settings WHERE key = 'lead_owner_user_id';
  IF owner_id IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.profiles WHERE id=owner_id AND status='approved'
  ) THEN RAISE EXCEPTION 'An approved intake owner is required'; END IF;

  saved_id := receipt.lead_id;
  IF saved_id IS NULL THEN
    SELECT id INTO saved_id FROM public.leads WHERE form_submission_id=p_submission_id
      ORDER BY created_at LIMIT 1;
  END IF;
  IF saved_id IS NULL THEN
    candidate := jsonb_populate_record(NULL::public.leads, p_lead);
    INSERT INTO public.leads (
      property_address,city,state,zip_code,owner_first_name,owner_last_name,owner_phone_1,owner_email,
      source,inbound_channel,status,precision_tier,ai_qualification_summary,
      score_motivation,score_timeline,score_equity,score_condition,score_flexibility,
      priority_tier,motivation_tag,asking_price,form_submission_id,ad_campaign_id,assigned_to,internal_notes,ai_calling_paused
    ) VALUES (
      candidate.property_address,candidate.city,candidate.state,candidate.zip_code,
      candidate.owner_first_name,candidate.owner_last_name,candidate.owner_phone_1,candidate.owner_email,
      candidate.source,candidate.inbound_channel,candidate.status,candidate.precision_tier,
      candidate.ai_qualification_summary,candidate.score_motivation,candidate.score_timeline,
      candidate.score_equity,candidate.score_condition,candidate.score_flexibility,
      candidate.priority_tier,candidate.motivation_tag,candidate.asking_price,p_submission_id,
      candidate.ad_campaign_id,owner_id,candidate.internal_notes,coalesce(candidate.ai_calling_paused,true)
    ) RETURNING id INTO saved_id;
    created := true;
  END IF;
  -- Same task id on every recovery; completed tasks and operator changes survive.
  INSERT INTO public.tasks(id,title,description,priority,status,type,lead_id,assigned_to,due_date)
    VALUES (p_submission_id,'Follow up on new website inquiry',
      'Review the saved inquiry and consent before contacting the inquirer.',
      'high','pending','follow_up',saved_id,owner_id,now())
    ON CONFLICT(id) DO NOTHING;
  UPDATE public.lead_form_submissions SET lead_id=saved_id,processing_status='processed'
    WHERE id=p_submission_id;
  RETURN jsonb_build_object('lead_id',saved_id,'created',created);
END;
$$;
REVOKE ALL ON FUNCTION public.finalize_form_submission(uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finalize_form_submission(uuid,jsonb) TO service_role;

-- Server-owned field validation; no browser database credentials.
INSERT INTO public.lead_form_configs (name,slug,headline,subheadline,thank_you_message,questions,active,send_confirmation_sms,send_confirmation_email)
VALUES ('The Jays Dallas — Website inquiries','the-jays-dallas','Contact The Jays Dallas','Tell us how we can help.',
'Thank you — your inquiry has been received. Our team will follow up within one business day.',
'[{"id": "first_name", "step": 1, "field_name": "first_name", "label": "Name", "type": "text", "required": true}, {"id": "last_name", "step": 1, "field_name": "last_name", "label": "Last name", "type": "text", "required": false}, {"id": "email", "step": 1, "field_name": "email", "label": "Email", "type": "email", "required": true}, {"id": "phone", "step": 1, "field_name": "phone", "label": "Phone", "type": "tel", "required": false}, {"id": "property_address", "step": 1, "field_name": "property_address", "label": "Property Address", "type": "text", "required": false}, {"id": "inquiry_type", "step": 1, "field_name": "inquiry_type", "label": "Inquiry Type", "type": "radio", "required": true, "options": [{"label": "Sell", "value": "sell"}, {"label": "Buyer", "value": "buyer"}, {"label": "Financing", "value": "financing"}, {"label": "Contact", "value": "contact"}]}, {"id": "message", "step": 1, "field_name": "message", "label": "Inquiry Details", "type": "textarea", "required": true}, {"id": "sms_opt_in", "step": 1, "field_name": "sms_opt_in", "label": "By checking this optional box, I agree to receive recurring automated text messages from Hilltop Home Co., a DBA of The Jays Dallas, LLC, about my property inquiry, offer updates, appointment reminders and closing updates. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase or receiving an offer.", "type": "checkbox", "required": false}]'::jsonb,true,true,false)
ON CONFLICT (slug) DO UPDATE SET questions=excluded.questions,active=true,thank_you_message=excluded.thank_you_message;
