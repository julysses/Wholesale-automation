-- Named trustee auction evidence is status-only; appraisal remains the owner source.
-- Xome property URLs must bind exactly to an already verified CRM situs.
BEGIN;
CREATE FUNCTION wholesale_ingest.foreclosure_status_evidence_allowed(p_lead uuid,p_county text,p_url text)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE l public.leads; expected text; host text;
BEGIN
 IF p_url IS NULL OR length(p_url)>2000 OR p_county NOT IN ('Dallas','Collin') THEN RETURN false; END IF;
 SELECT lead.* INTO l FROM public.leads lead JOIN wholesale_ingest.properties p ON p.lead_id=lead.id
 WHERE lead.id=p_lead AND p.county=p_county;
 IF NOT FOUND THEN RETURN false; END IF;
 host:=substring(lower(p_url) from '^https://([^/:?#]+)(?:[/:?#]|$)');
 IF host=ANY(CASE p_county WHEN 'Dallas' THEN ARRAY['www.dallascounty.org','dallas.tx.publicsearch.us']
 ELSE ARRAY['www.collincountytx.gov','collincountytx.gov','apps.collincountytx.gov','apps2.collincountytx.gov'] END) THEN RETURN true; END IF;
 IF nullif(trim(l.property_address),'') IS NULL OR nullif(trim(l.city),'') IS NULL OR coalesce(l.zip_code,'') !~ '^[0-9]{5}(-[0-9]{4})?$' THEN RETURN false; END IF;
 expected:='https://www.xome.com/auctions/'||lower(btrim(regexp_replace(trim(l.property_address),'[^A-Za-z0-9]+','-','g'),'-'))||'-'||
  lower(btrim(regexp_replace(trim(l.city),'[^A-Za-z0-9]+','-','g'),'-'))||'-tx-'||left(l.zip_code,5)||'-';
 RETURN starts_with(p_url,expected) AND substring(p_url from length(expected)+1) ~ '^[0-9]{6,12}$';
END; $$;
REVOKE ALL ON FUNCTION wholesale_ingest.foreclosure_status_evidence_allowed(uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.foreclosure_status_evidence_allowed(uuid,text,text) TO service_role;

DO $migration$
DECLARE original text; revised text; old_check text; new_check text; owner_loop text; quote_marker text;
BEGIN
 original:=pg_get_functiondef('public.propstream_handoff_action(uuid,uuid,uuid,uuid,text,jsonb)'::regprocedure);
 old_check:=$old$IF coalesce(length(host),0)>2000 OR substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)') IS NULL OR
   substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)')<>ALL(CASE WHEN (SELECT county FROM wholesale_ingest.sources WHERE id=signal.source_id)='Dallas' THEN ARRAY['www.dallascounty.org','dallas.tx.publicsearch.us'] ELSE ARRAY['www.collincountytx.gov','collincountytx.gov','apps.collincountytx.gov','apps2.collincountytx.gov'] END) THEN RAISE EXCEPTION 'Official current-sale evidence required'; END IF;$old$;
 new_check:=$new$IF NOT wholesale_ingest.foreclosure_status_evidence_allowed(p_lead,(SELECT county FROM wholesale_ingest.sources WHERE id=signal.source_id),host) THEN RAISE EXCEPTION 'Property-bound current-sale evidence required'; END IF;$new$;
 owner_loop:=$old$FOREACH host IN ARRAY ARRAY[p_payload->>'owner_evidence_url',p_payload->>'status_evidence_url'] LOOP$old$;
 quote_marker:=$old$END LOOP;
  IF coalesce(p_payload->>'quote_cents'$old$;
 IF position(old_check in original)=0 OR position(owner_loop in original)=0 OR position(quote_marker in original)=0 THEN RAISE EXCEPTION 'Unexpected handoff definition; review before changing evidence rules'; END IF;
 revised:=replace(original,old_check,new_check);
 revised:=replace(revised,owner_loop,$new$FOREACH host IN ARRAY ARRAY[p_payload->>'owner_evidence_url'] LOOP$new$);
 revised:=replace(revised,quote_marker,$new$END LOOP;
  IF NOT wholesale_ingest.foreclosure_status_evidence_allowed(p_lead,(SELECT county FROM wholesale_ingest.sources WHERE id=signal.source_id),p_payload->>'status_evidence_url') THEN RAISE EXCEPTION 'Property-bound current-sale evidence required'; END IF;
  IF coalesce(p_payload->>'quote_cents'$new$);
 EXECUTE revised;
END; $migration$;
COMMIT;
