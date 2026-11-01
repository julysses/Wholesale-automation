-- Reuse canonical buyers. Historical rows remain unassigned and unchanged.
-- Scoped discovery/writes must use reviewed private functions; no public writer
-- or assignment authority is introduced by this storage migration.
BEGIN;
ALTER TABLE public.buyers ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_revision integer,
 ADD CONSTRAINT acquisition_buyer_workspace_identity UNIQUE(id,workspace_id),
 ADD CONSTRAINT acquisition_buyer_workspace_shape CHECK (
  (workspace_id IS NULL AND acquisition_revision IS NULL) OR
  (workspace_id IS NOT NULL AND acquisition_revision IS NOT NULL AND acquisition_revision>=1
   AND import_log_id IS NULL AND sms_opt_in IS FALSE AND email_opt_in IS FALSE AND pof_verified IS FALSE));
CREATE INDEX acquisition_buyers_workspace_index ON public.buyers(workspace_id,id) WHERE workspace_id IS NOT NULL;
CREATE POLICY acquisition_buyer_storage_boundary ON public.buyers AS RESTRICTIVE FOR ALL TO anon,authenticated
 USING(workspace_id IS NULL) WITH CHECK(workspace_id IS NULL);
REVOKE TRUNCATE,TRIGGER,REFERENCES ON public.buyers FROM anon,authenticated,service_role;

CREATE FUNCTION private.protect_acquisition_buyer() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_name text; scoped boolean;
BEGIN
 scoped:=CASE WHEN TG_OP='INSERT' THEN NEW.workspace_id IS NOT NULL
  WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL
  ELSE OLD.workspace_id IS NOT NULL OR NEW.workspace_id IS NOT NULL END;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP='UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id) THEN
  RAISE EXCEPTION 'Buyer identity and workspace are immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Archive scoped buyers without deleting history' USING ERRCODE='42501'; END IF;
 -- Trusted provider opt-outs remain a one-way operation. This cannot alter
 -- identity, permissions to true, price preferences, or verification evidence.
 IF TG_OP='UPDATE' AND current_user='service_role' AND NEW.email_opt_in IS FALSE
  AND (to_jsonb(NEW)-'email_opt_in'-'updated_at')=(to_jsonb(OLD)-'email_opt_in'-'updated_at') THEN RETURN NEW; END IF;
 SELECT pg_get_userbyid(proowner) INTO owner_name FROM pg_proc WHERE oid='private.protect_acquisition_buyer()'::regprocedure;
 IF current_user<>owner_name THEN RAISE EXCEPTION 'Use scoped buyer functions' USING ERRCODE='42501'; END IF;
 IF (TG_OP='INSERT' AND NEW.acquisition_revision<>1) OR
  (TG_OP='UPDATE' AND NEW.acquisition_revision<>OLD.acquisition_revision+1) THEN
  RAISE EXCEPTION 'Buyer revision must advance exactly once' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_buyer() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_buyer_protected BEFORE INSERT OR UPDATE OR DELETE ON public.buyers
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_buyer();

CREATE FUNCTION private.audit_acquisition_buyer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.workspace_id IS NOT NULL THEN
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
   VALUES('acquisition_buyer',NEW.id::text,lower(TG_OP),coalesce(auth.uid()::text,session_user),NEW.workspace_id,
    jsonb_build_object('revision',NEW.acquisition_revision,'active',NEW.active,'email_opt_in',NEW.email_opt_in));
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_acquisition_buyer() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_buyer_audit AFTER INSERT OR UPDATE ON public.buyers
 FOR EACH ROW EXECUTE FUNCTION private.audit_acquisition_buyer();

-- Existing child records have no buyer workspace boundary yet. A scoped buyer
-- cannot be attached through legacy preferences, imports, deals, tasks or blast
-- records. Their later scoped writers must establish matching parent scopes.
CREATE FUNCTION private.protect_legacy_buyer_reference() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.buyer_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.buyers WHERE id=NEW.buyer_id AND workspace_id IS NOT NULL) THEN
  RAISE EXCEPTION 'Scoped buyers require a reviewed acquisition relationship' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_legacy_buyer_reference() FROM PUBLIC,anon,authenticated,service_role;
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['buyer_preferences','buyer_transactions','deal_matches','buyer_outreach_log','deals','tasks'] LOOP
  EXECUTE format('CREATE TRIGGER acquisition_buyer_reference BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.protect_legacy_buyer_reference()',name);
 END LOOP;
END $$;

-- Service-role queries bypass RLS: legacy aggregates explicitly exclude scoped
-- records while retaining their existing columns, invoker mode and legacy data.
CREATE OR REPLACE VIEW public.buyer_leaderboard WITH(security_invoker=true) AS  SELECT b.id,
    b.first_name,
    b.last_name,
    b.company,
    b.entity_name,
    b.email,
    b.phone,
    b.market,
    b.buyer_type_ibie,
    b.ibie_score,
    b.ibie_tier,
    b.cash_buyer,
    b.repeat_buyer,
    b.total_purchases_12mo,
    b.properties_owned,
    b.avg_purchase_price,
    b.last_purchase_date,
    b.tags,
    b.deals_closed,
    b.pof_verified,
    b.pof_amount,
    b.target_zips,
    b.min_price,
    b.max_price,
    b.tier AS crm_tier,
    b.active,
    b.sms_opt_in,
    b.email_opt_in,
    b.outreach_ignore_count,
    b.last_scored_at,
    b.created_at,
    (count(DISTINCT bt.id))::integer AS transaction_count,
    max(bt.purchase_date) AS most_recent_purchase
   FROM (buyers b
     LEFT JOIN buyer_transactions bt ON ((bt.buyer_id = b.id)))
  WHERE (b.active = true) AND b.workspace_id IS NULL
  GROUP BY b.id
  ORDER BY b.ibie_score DESC NULLS LAST;
CREATE OR REPLACE VIEW public.ibie_segment_summary WITH(security_invoker=true) AS  SELECT ibie_tier,
    buyer_type_ibie,
    (count(*))::integer AS buyer_count,
    round(avg(ibie_score), 1) AS avg_score,
    (count(*) FILTER (WHERE cash_buyer))::integer AS cash_buyer_count,
    (count(*) FILTER (WHERE repeat_buyer))::integer AS repeat_buyer_count,
    round(avg(total_purchases_12mo), 1) AS avg_purchases_12mo,
    round(avg(avg_purchase_price)) AS avg_buy_price
   FROM buyers
  WHERE (active = true) AND workspace_id IS NULL
  GROUP BY ibie_tier, buyer_type_ibie;
COMMIT;
