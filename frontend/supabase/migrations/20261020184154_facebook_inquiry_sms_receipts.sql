-- Native Meta receipts remain distinct from website consent. No backfill,
-- dispatch, schedule installation, or modification of held/attempted work.
CREATE TABLE public.facebook_lead_submissions (
 id uuid PRIMARY KEY,
 lead_id uuid NOT NULL UNIQUE REFERENCES public.leads(id),
 leadgen_id text NOT NULL UNIQUE CHECK (length(leadgen_id)>0),
 form_id text NOT NULL,
 submitted_at text, -- retain invalid/missing provider input for review; Python validates before queueing
 phone_number text CHECK (phone_number ~ '^\+1[2-9][0-9]{9}$'),
 raw_answers jsonb NOT NULL CHECK (jsonb_typeof(raw_answers)='object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,lead_id,phone_number)
);
ALTER TABLE public.facebook_lead_submissions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.facebook_lead_submissions FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.facebook_lead_submissions TO service_role;

CREATE FUNCTION public.protect_facebook_submission() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 RAISE EXCEPTION 'Native inquiry evidence is immutable';
END $$;
REVOKE ALL ON FUNCTION public.protect_facebook_submission() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_facebook_submission BEFORE UPDATE OR DELETE ON public.facebook_lead_submissions
 FOR EACH ROW EXECUTE FUNCTION public.protect_facebook_submission();

ALTER TABLE public.retell_form_sms_jobs
 ALTER COLUMN submission_id DROP NOT NULL,
 ADD COLUMN facebook_submission_id uuid UNIQUE,
 ADD CONSTRAINT retell_inquiry_exact_source CHECK (
   (submission_id IS NOT NULL)::integer + (facebook_submission_id IS NOT NULL)::integer = 1),
 ADD CONSTRAINT retell_facebook_inquiry_identity
   FOREIGN KEY(facebook_submission_id,lead_id,phone_number)
   REFERENCES public.facebook_lead_submissions(id,lead_id,phone_number);

CREATE OR REPLACE FUNCTION public.protect_retell_form_transport() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.delivery_transport,NEW.delivery_body,NEW.delivery_sender,NEW.lead_id,
        NEW.submission_id,NEW.facebook_submission_id,NEW.phone_number)
   IS DISTINCT FROM ROW(OLD.delivery_transport,OLD.delivery_body,OLD.delivery_sender,OLD.lead_id,
        OLD.submission_id,OLD.facebook_submission_id,OLD.phone_number) THEN
  RAISE EXCEPTION 'Inquiry transport identity and content are immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_form_transport() FROM PUBLIC,anon,authenticated;
