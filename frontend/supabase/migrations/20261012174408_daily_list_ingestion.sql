-- Additive list intake. All sources start disabled; no outreach is enabled.
-- Additive private intake layer; existing public leads/buyers/deals/outreach remain authoritative.
BEGIN;
CREATE SCHEMA wholesale_ingest;
REVOKE ALL ON SCHEMA wholesale_ingest FROM PUBLIC, anon, authenticated;
CREATE ROLE wholesale_ingestor NOLOGIN NOBYPASSRLS;
CREATE ROLE wholesale_worker NOLOGIN NOBYPASSRLS;
GRANT USAGE ON SCHEMA wholesale_ingest TO wholesale_ingestor, wholesale_worker;

CREATE TABLE wholesale_ingest.sources (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_key text NOT NULL UNIQUE,
 state text NOT NULL CHECK (state='TX'), county text NOT NULL CHECK(county IN ('Dallas','Collin')),
 jurisdiction text NOT NULL, list_type text NOT NULL CHECK(list_type IN ('pre_foreclosure','tax_delinquent','code_violation','probate')),
 method text NOT NULL CHECK(method IN ('api','export','browser','records_request')),
 source_url text NOT NULL CHECK(source_url LIKE 'https://%'), allowed_hosts text[] NOT NULL,
 lookback_days integer NOT NULL CHECK(lookback_days BETWEEN 1 AND 365),
 backfill_days integer NOT NULL CHECK(backfill_days BETWEEN 1 AND 365),
 schedule_cron text NOT NULL, timezone text NOT NULL DEFAULT 'America/Chicago',
 deadline_local time NOT NULL DEFAULT '06:00', enabled boolean NOT NULL DEFAULT false,
 procedure_version text, procedure_approved_at timestamptz, expected_publication text,
 CHECK(list_type<>'pre_foreclosure' OR (lookback_days<=30 AND backfill_days<=30))
);
CREATE TABLE wholesale_ingest.ingest_runs (
 id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES wholesale_ingest.sources,
 scheduled_for date NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), pulled_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('success','partial','blocked','failed')), status_reason text NOT NULL,
 manifest_hash text NOT NULL CHECK(manifest_hash ~ '^[a-f0-9]{64}$'),
 expected_batches integer NOT NULL CHECK(expected_batches BETWEEN 1 AND 1000),
 processing_status text NOT NULL DEFAULT 'received' CHECK(processing_status IN ('received','processing','completed','review','failed')),
 completed_at timestamptz, records_new integer NOT NULL DEFAULT 0, records_stacked integer NOT NULL DEFAULT 0,
 UNIQUE(id,source_id)
);
CREATE INDEX ingest_runs_source_day ON wholesale_ingest.ingest_runs(source_id,scheduled_for);
-- Multiple attempts are retained; day reporting selects the latest complete attempt, not a unique day row.
CREATE TABLE wholesale_ingest.raw_payloads (
 run_id uuid NOT NULL REFERENCES wholesale_ingest.ingest_runs, batch_index integer NOT NULL CHECK(batch_index>=0),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[a-f0-9]{64}$'), records_hash text NOT NULL,
 payload jsonb NOT NULL, records_in integer NOT NULL CHECK(records_in>=0), received_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '90 days', PRIMARY KEY(run_id,batch_index)
);
CREATE INDEX raw_payloads_expiry ON wholesale_ingest.raw_payloads(expires_at);
CREATE TABLE wholesale_ingest.records (
 run_id uuid NOT NULL, batch_index integer NOT NULL, ordinal integer NOT NULL,
 source_record_id text, record jsonb NOT NULL,
 review_reason text, property_id uuid, resolved_at timestamptz,
 PRIMARY KEY(run_id,batch_index,ordinal),
 FOREIGN KEY(run_id,batch_index) REFERENCES wholesale_ingest.raw_payloads ON DELETE CASCADE
);
CREATE TABLE wholesale_ingest.properties (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), state text NOT NULL CHECK(state='TX'),
 county text NOT NULL CHECK(county IN ('Dallas','Collin')), parcel_id text,
 address_std text, unit text, city text, zip text, lat numeric, lng numeric,
 is_vacant_lot boolean, lead_id uuid UNIQUE REFERENCES public.leads(id),
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(parcel_id IS NOT NULL OR address_std IS NOT NULL)
);
CREATE UNIQUE INDEX properties_parcel_unique ON wholesale_ingest.properties(state,county,parcel_id) WHERE parcel_id IS NOT NULL;
CREATE TABLE wholesale_ingest.property_aliases (
 alias_key text PRIMARY KEY, property_id uuid NOT NULL REFERENCES wholesale_ingest.properties,
 evidence_url text, verified_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE wholesale_ingest.records ADD FOREIGN KEY(property_id) REFERENCES wholesale_ingest.properties;
CREATE TABLE wholesale_ingest.distress_signals (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES wholesale_ingest.properties,
 source_id uuid NOT NULL REFERENCES wholesale_ingest.sources, source_record_id text NOT NULL,
 list_type text NOT NULL CHECK(list_type IN ('pre_foreclosure','tax_delinquent','code_violation','probate')),
 case_number text, filed_date date, auction_date date, amount numeric CHECK(amount>=0), amount_type text,
 source_url text NOT NULL, first_run_id uuid NOT NULL REFERENCES wholesale_ingest.ingest_runs,
 last_run_id uuid NOT NULL REFERENCES wholesale_ingest.ingest_runs,
 first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
 active boolean NOT NULL DEFAULT true, UNIQUE(property_id,source_id,source_record_id)
);
CREATE INDEX distress_by_property ON wholesale_ingest.distress_signals(property_id,active,list_type);
CREATE TABLE wholesale_ingest.signal_observations (
 signal_id uuid NOT NULL REFERENCES wholesale_ingest.distress_signals,
 run_id uuid NOT NULL REFERENCES wholesale_ingest.ingest_runs, source_url text NOT NULL, pulled_at timestamptz NOT NULL,
 PRIMARY KEY(signal_id,run_id)
);
CREATE TABLE wholesale_ingest.jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES wholesale_ingest.ingest_runs,
 batch_index integer NOT NULL, kind text NOT NULL CHECK(kind IN ('normalize','source_review')),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','processing','done','review','failed')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz, claim_token uuid, error_code text, UNIQUE(run_id,batch_index,kind)
);
CREATE INDEX jobs_due ON wholesale_ingest.jobs(available_at) WHERE state='pending';
CREATE TABLE wholesale_ingest.lead_evaluations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), lead_id uuid NOT NULL REFERENCES public.leads(id),
 input_hash text NOT NULL, model_version text NOT NULL, prompt_version text NOT NULL,
 score integer CHECK(score BETWEEN 0 AND 100), reasons jsonb NOT NULL, flags jsonb NOT NULL,
 route text NOT NULL CHECK(route IN ('call_sms','underwrite_lot','nurture','review')),
 stack_count integer NOT NULL CHECK(stack_count BETWEEN 0 AND 4),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(lead_id,input_hash,prompt_version)
);
CREATE TABLE wholesale_ingest.skip_trace_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), lead_id uuid NOT NULL REFERENCES public.leads(id),
 provider text NOT NULL, request_key text NOT NULL UNIQUE, spend_day date NOT NULL,
 reserved_cents integer NOT NULL CHECK(reserved_cents>=0), actual_cents integer CHECK(actual_cents>=0),
 state text NOT NULL CHECK(state IN ('reserved','submitted','completed','failed','unknown')), provider_job_id text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE wholesale_ingest.contacts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), lead_id uuid NOT NULL REFERENCES public.leads(id),
 provider text NOT NULL, traced_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 name text, phone text CHECK(phone ~ '^\+[1-9][0-9]{7,14}$'), email text,
 phone_type text, dnc_status text NOT NULL DEFAULT 'unknown', dnc_checked_at timestamptz,
 CHECK(phone IS NOT NULL OR email IS NOT NULL)
);
CREATE TABLE wholesale_ingest.daily_budgets (
 spend_day date PRIMARY KEY, cap_cents integer NOT NULL CHECK(cap_cents>=0),
 reserved_cents integer NOT NULL DEFAULT 0 CHECK(reserved_cents>=0),
 actual_cents integer NOT NULL DEFAULT 0 CHECK(actual_cents>=0),
 CHECK(reserved_cents+actual_cents<=cap_cents)
);
CREATE TABLE wholesale_ingest.daily_digests (
 day date PRIMARY KEY, generated_at timestamptz, accepted_at timestamptz, delivered_at timestamptz,
 status text NOT NULL DEFAULT 'pending', summary jsonb, error_code text
);
CREATE TABLE wholesale_ingest.expected_runs (
 source_id uuid NOT NULL REFERENCES wholesale_ingest.sources, day date NOT NULL,
 due_at timestamptz NOT NULL, alert_task_id uuid REFERENCES public.tasks(id),
 PRIMARY KEY(source_id,day)
);
-- Private layer: API access must go through the existing approved-operator backend.
-- Worker has no newly granted privileges on public leads/tasks/outreach. CRM adapter review is required.
DO $$ DECLARE t text; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='wholesale_ingest' LOOP
  EXECUTE format('ALTER TABLE wholesale_ingest.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON wholesale_ingest.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON wholesale_ingest.%I TO wholesale_worker',t);
  EXECUTE format('CREATE POLICY worker_access ON wholesale_ingest.%I TO wholesale_worker USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT ON wholesale_ingest.sources TO wholesale_ingestor;
CREATE POLICY ingest_source_read ON wholesale_ingest.sources FOR SELECT TO wholesale_ingestor USING(true);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ingest_runs','raw_payloads','records','jobs'] LOOP
  EXECUTE format('GRANT SELECT,INSERT ON wholesale_ingest.%I TO wholesale_ingestor',t);
  EXECUTE format('CREATE POLICY ingest_read ON wholesale_ingest.%I FOR SELECT TO wholesale_ingestor USING(true)',t);
  EXECUTE format('CREATE POLICY ingest_insert ON wholesale_ingest.%I FOR INSERT TO wholesale_ingestor WITH CHECK(true)',t);
 END LOOP;
END $$;
-- Default deny: seed verified sources separately; do not enable live ingestion or outbound on migration.
COMMIT;
