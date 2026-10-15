BEGIN;
-- The official Collin CAD homepage links its current property search to this
-- exact subdomain. Keep host matching exact, with no wildcard expansion.
DO $$
DECLARE signature text; definition text; revised text;
BEGIN
 FOREACH signature IN ARRAY ARRAY['public.resolve_reviewed_list_record(uuid,integer,integer,uuid,text,text,uuid,boolean,jsonb)','public.propstream_handoff_action(uuid,uuid,uuid,uuid,text,jsonb)'] LOOP
  definition:=pg_get_functiondef(signature::regprocedure);
  revised:=replace(definition,'''www.collincad.org'',''collincad.org''','''www.collincad.org'',''collincad.org'',''esearch.collincad.org''');
  IF revised=definition THEN RAISE EXCEPTION 'Expected Collin evidence allowlist missing: %',signature; END IF;
  -- Existing county foreclosure receipt URLs use apps2 (not apps).
  IF signature LIKE 'public.propstream_handoff_action%' THEN
   revised:=replace(revised,'''apps.collincountytx.gov''','''apps.collincountytx.gov'',''apps2.collincountytx.gov''');
  END IF;
  EXECUTE revised;
 END LOOP;
END; $$;
COMMIT;
