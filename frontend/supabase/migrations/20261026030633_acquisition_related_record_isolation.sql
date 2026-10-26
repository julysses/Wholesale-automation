-- Derived workspace isolation for existing canonical records and their children.
-- No row duplication, backfill, grants expansion, workers or external calls.
BEGIN;
CREATE FUNCTION private.acquisition_record_access(p_lead uuid,p_deal uuid,p_property uuid,p_write boolean DEFAULT false)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE scopes uuid[];
BEGIN
 SELECT array_agg(DISTINCT b.workspace_id) INTO scopes FROM public.workspace_leads b
 WHERE b.lead_id IN (
  p_lead,
  (SELECT d.lead_id FROM public.deals d WHERE d.id=p_deal),
  (SELECT p.lead_id FROM wholesale_ingest.properties p WHERE p.id=p_property)
 ) OR b.property_id=p_property;
 IF coalesce(cardinality(scopes),0)=0 THEN RETURN private.acquisition_legacy_access(); END IF;
 -- A row that mixes parents from different workspaces is not readable by either.
 IF cardinality(scopes)<>1 OR p_write THEN RETURN false; END IF;
 RETURN coalesce(private.acquisition_role(scopes[1]) IN ('owner','admin','operator'),false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_record_access(uuid,uuid,uuid,boolean) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_record_access(uuid,uuid,uuid,boolean) TO authenticated;

DO $$ DECLARE t record; lead_expr text; deal_expr text; property_expr text; read_expr text; write_expr text;
BEGIN
 FOR t IN SELECT n.nspname,c.relname,
  bool_or(a.attname='lead_id') AS has_lead,
  bool_or(a.attname='deal_id') AS has_deal,
  bool_or(a.attname='property_id') AS has_property
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
  WHERE n.nspname IN ('public','wholesale_ingest') AND c.relkind IN ('r','p')
   AND a.attnum>0 AND NOT a.attisdropped AND a.atttypid='uuid'::regtype
   AND a.attname IN ('lead_id','deal_id','property_id')
   AND NOT (n.nspname='public' AND c.relname='workspace_leads')
  GROUP BY n.nspname,c.relname
 LOOP
  lead_expr:=CASE WHEN t.has_lead THEN 'lead_id' ELSE 'NULL::uuid' END;
  deal_expr:=CASE WHEN t.has_deal THEN 'deal_id' ELSE 'NULL::uuid' END;
  property_expr:=CASE WHEN t.nspname='wholesale_ingest' AND t.relname='properties' THEN 'id'
   WHEN t.has_property THEN 'property_id' ELSE 'NULL::uuid' END;
  read_expr:=format('private.acquisition_record_access(%s,%s,%s,false)',lead_expr,deal_expr,property_expr);
  write_expr:=format('private.acquisition_record_access(%s,%s,%s,true)',lead_expr,deal_expr,property_expr);
  EXECUTE format('DROP POLICY IF EXISTS acquisition_legacy_boundary ON %I.%I',t.nspname,t.relname);
  EXECUTE format('CREATE POLICY acquisition_related_read ON %I.%I AS RESTRICTIVE FOR SELECT TO authenticated USING (%s)',t.nspname,t.relname,read_expr);
  EXECUTE format('CREATE POLICY acquisition_related_insert ON %I.%I AS RESTRICTIVE FOR INSERT TO authenticated WITH CHECK (%s)',t.nspname,t.relname,write_expr);
  EXECUTE format('CREATE POLICY acquisition_related_update ON %I.%I AS RESTRICTIVE FOR UPDATE TO authenticated USING (%s) WITH CHECK (%s)',t.nspname,t.relname,write_expr,write_expr);
  EXECUTE format('CREATE POLICY acquisition_related_delete ON %I.%I AS RESTRICTIVE FOR DELETE TO authenticated USING (%s)',t.nspname,t.relname,write_expr);
 END LOOP;
END $$;

CREATE FUNCTION private.protect_bound_property_identity() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND EXISTS(
  SELECT 1 FROM public.workspace_leads WHERE property_id=OLD.id OR lead_id=OLD.lead_id
 ) THEN RAISE EXCEPTION 'Bound property identity cannot be reassigned' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_bound_property_identity() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_bound_property_identity BEFORE UPDATE ON wholesale_ingest.properties
 FOR EACH ROW EXECUTE FUNCTION private.protect_bound_property_identity();
COMMIT;
