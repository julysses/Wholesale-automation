-- Proof for 20261126000000_facebook_attribution_reconciliation.sql.
-- Runs on a DISPOSABLE database with minimal stub tables (loopback only); all work rolls back.
-- psql -v ON_ERROR_STOP=1 -f <migration> then this file. Never run against production.
BEGIN;
CREATE ROLE service_role NOLOGIN; CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
CREATE TABLE public.ad_campaigns(id uuid PRIMARY KEY, platform text);
CREATE TABLE public.ad_creatives(id uuid PRIMARY KEY, campaign_id uuid REFERENCES public.ad_campaigns(id));
CREATE TABLE public.leads(id uuid PRIMARY KEY, source text, ad_campaign_id uuid, ad_creative_id uuid);
CREATE TABLE public.facebook_lead_submissions(id uuid PRIMARY KEY, lead_id uuid, leadgen_id text);
CREATE TABLE public.audit_logs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), entity_type text, entity_id text,
  action text, actor text, old_value jsonb, new_value jsonb, metadata jsonb, occurred_at timestamptz DEFAULT now());
\ir ../../frontend/supabase/migrations/20261126000000_facebook_attribution_reconciliation.sql

INSERT INTO ad_campaigns VALUES('00000000-0000-0000-0000-0000000000c1','facebook'),
  ('00000000-0000-0000-0000-0000000000c2','facebook'),('00000000-0000-0000-0000-0000000000c3','google');
INSERT INTO ad_creatives VALUES('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-0000000000c1');
INSERT INTO leads VALUES('00000000-0000-0000-0000-000000000001','facebook_lead_ad',NULL,NULL),
  ('00000000-0000-0000-0000-000000000002','website',NULL,NULL),
  ('00000000-0000-0000-0000-000000000003','facebook_lead_ad','00000000-0000-0000-0000-0000000000c2',NULL);
INSERT INTO facebook_lead_submissions VALUES(gen_random_uuid(),'00000000-0000-0000-0000-000000000001','meta1'),
  (gen_random_uuid(),'00000000-0000-0000-0000-000000000002','meta2'),
  (gen_random_uuid(),'00000000-0000-0000-0000-000000000003','meta3');

DO $$
DECLARE r jsonb; n int;
  L1 uuid:='00000000-0000-0000-0000-000000000001'; C1 uuid:='00000000-0000-0000-0000-0000000000c1';
  K1 uuid:='00000000-0000-0000-0000-0000000000a1';
BEGIN
  r:=public.reconcile_facebook_lead_attribution(L1,'meta1',C1,K1,'julio','ad launch');
  ASSERT (r->>'applied')::boolean, 'first apply';
  ASSERT (SELECT ad_campaign_id=C1 AND ad_creative_id=K1 FROM leads WHERE id=L1), 'columns set';
  ASSERT (SELECT count(*) FROM audit_logs WHERE entity_id=L1::text)=1, 'one audit row';
  r:=public.reconcile_facebook_lead_attribution(L1,'meta1',C1,K1,'julio','ad launch');
  ASSERT NOT (r->>'applied')::boolean, 'replay is a no-op';
  ASSERT (SELECT count(*) FROM audit_logs WHERE entity_id=L1::text)=1, 'replay writes no audit row';
  BEGIN PERFORM public.reconcile_facebook_lead_attribution(L1,'meta1','00000000-0000-0000-0000-0000000000c2',NULL,'a','r');
    RAISE EXCEPTION 'should conflict'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM='Existing attribution conflicts', SQLERRM; END;
  BEGIN PERFORM public.reconcile_facebook_lead_attribution('00000000-0000-0000-0000-000000000002','meta2',C1,NULL,'a','r');
    RAISE EXCEPTION 'x'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM='Not a Facebook inquiry', SQLERRM; END;
  BEGIN PERFORM public.reconcile_facebook_lead_attribution(L1,'wrong',C1,NULL,'a','r');
    RAISE EXCEPTION 'x'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM='Meta lead identity does not match this lead', SQLERRM; END;
  BEGIN PERFORM public.reconcile_facebook_lead_attribution('00000000-0000-0000-0000-000000000003','meta3','00000000-0000-0000-0000-0000000000c3',NULL,'a','r');
    RAISE EXCEPTION 'x'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM='Campaign is not a registered Facebook campaign', SQLERRM; END;
  BEGIN PERFORM public.reconcile_facebook_lead_attribution('00000000-0000-0000-0000-000000000003','meta3','00000000-0000-0000-0000-0000000000c2',K1,'a','r');
    RAISE EXCEPTION 'x'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM='Creative does not belong to campaign', SQLERRM; END;
  BEGIN PERFORM public.reconcile_facebook_lead_attribution(L1,'meta1',C1,NULL,'','r');
    RAISE EXCEPTION 'x'; EXCEPTION WHEN raise_exception THEN ASSERT SQLERRM LIKE '%required%', SQLERRM; END;
  ASSERT NOT has_function_privilege('public','public.reconcile_facebook_lead_attribution(uuid,text,uuid,uuid,text,text)','EXECUTE'), 'PUBLIC denied';
  ASSERT has_function_privilege('service_role','public.reconcile_facebook_lead_attribution(uuid,text,uuid,uuid,text,text)','EXECUTE'), 'service_role allowed';
END $$;
SELECT 'facebook attribution reconciliation proof passed' AS result;
ROLLBACK;
