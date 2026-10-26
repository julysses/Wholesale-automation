-- Conservative review candidates only: never merge leads/properties or grant permissions.
BEGIN;
CREATE FUNCTION private.acquisition_identity_text(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT nullif(lower(regexp_replace(trim(p_value),'[[:space:]]+',' ','g')),'')
$$;
CREATE FUNCTION private.acquisition_optional_contact(p_type text,p_value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
BEGIN
 RETURN private.normalize_acquisition_contact(p_type,p_value);
EXCEPTION WHEN invalid_parameter_value THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION private.acquisition_identity_text(text),private.acquisition_optional_contact(text,text)
 FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.acquisition_intake_candidates(p_workspace uuid,p_intake uuid,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; answers jsonb; v_street text; v_city text; v_state text;
 phone text; email text; candidates jsonb; total integer;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace intake access required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'Candidate limit must be between 1 and 50' USING ERRCODE='22023'; END IF;
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake AND workspace_id=p_workspace;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace intake unavailable' USING ERRCODE='42501'; END IF;
 answers:=intake.prepared_answers->'answers';
 v_street:=private.acquisition_identity_text(answers->>'property_address');
 v_city:=private.acquisition_identity_text(answers->>'city');
 v_state:=private.acquisition_identity_text(answers->>'state');
 IF v_state='texas' THEN v_state:='tx'; END IF;
 phone:=private.acquisition_optional_contact('phone',answers->>'phone');
 email:=private.acquisition_optional_contact('email',answers->>'email');
 WITH matches AS (
  SELECT b.lead_id,b.property_id,l.property_address,l.city,l.state,l.zip_code,
   l.owner_first_name,l.owner_last_name,p.county,p.parcel_id,p.address_std,p.unit,
   -- No abbreviation, punctuation, unit, geocoding or fuzzy-address inference.
   coalesce(v_street=private.acquisition_identity_text(l.property_address)
    AND v_city=private.acquisition_identity_text(l.city)
    AND v_state=CASE WHEN private.acquisition_identity_text(l.state)='texas' THEN 'tx' ELSE private.acquisition_identity_text(l.state) END,false) AS address_match,
   coalesce(phone=ANY(ARRAY[private.acquisition_optional_contact('phone',l.owner_phone_1),
    private.acquisition_optional_contact('phone',l.owner_phone_2),private.acquisition_optional_contact('phone',l.owner_phone_3)]),false) AS phone_match,
   coalesce(email=private.acquisition_optional_contact('email',l.owner_email),false) AS email_match,
   coalesce(EXISTS(SELECT 1 FROM public.seller_intakes s WHERE s.workspace_id=p_workspace AND s.lead_id=b.lead_id),false) AS previous_intake
  FROM public.workspace_leads b JOIN public.leads l ON l.id=b.lead_id
  LEFT JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
  WHERE b.workspace_id=p_workspace AND b.lead_id<>intake.lead_id
 ), bounded AS (
  SELECT * FROM matches WHERE address_match OR phone_match OR email_match
  ORDER BY address_match DESC,(phone_match OR email_match) DESC,lead_id LIMIT p_limit+1
 ), visible AS (
  SELECT * FROM bounded ORDER BY address_match DESC,(phone_match OR email_match) DESC,lead_id LIMIT p_limit
 ) SELECT (SELECT count(*) FROM bounded),coalesce(jsonb_agg(jsonb_build_object(
  'lead_id',lead_id,'property_id',property_id,'property_address',property_address,'city',city,'state',state,'zip_code',zip_code,
  'owner_name',trim(concat_ws(' ',owner_first_name,owner_last_name)),
  'county',county,'parcel_id',parcel_id,'county_address',address_std,'county_unit',unit,
  'address_match',address_match,'phone_match',phone_match,'email_match',email_match,'previous_intake',previous_intake,
  'match_basis',CASE WHEN address_match THEN 'EXACT_ADDRESS_TEXT' ELSE 'CONTACT_ONLY' END,
  'review_required',true,'merge_authorized',false
 ) ORDER BY address_match DESC,(phone_match OR email_match) DESC,lead_id),'[]'::jsonb)
 INTO total,candidates FROM visible;
 RETURN jsonb_build_object('intake_id',intake.id,'lead_id',intake.lead_id,'workspace_id',p_workspace,
  'preparation_hash',intake.preparation_hash,'classification',intake.classification,
  'submitted_property',jsonb_build_object('address',answers->>'property_address','city',answers->>'city','state',answers->>'state','zip_code',answers->>'zip_code'),
  'items',candidates,'truncated',total>p_limit,'policy_version','intake-candidates-v1',
  'candidate_hash',encode(sha256(convert_to(candidates::text,'UTF8')),'hex'),
  'checked_at',statement_timestamp(),'merge_authorized',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_intake_candidates(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_intake_candidates(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.acquisition_intake_candidates(p_workspace uuid,p_intake uuid,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_intake_candidates(p_workspace,p_intake,p_limit)
$$;
REVOKE ALL ON FUNCTION public.acquisition_intake_candidates(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_intake_candidates(uuid,uuid,integer) TO authenticated;
COMMIT;
