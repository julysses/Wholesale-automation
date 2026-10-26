-- Installing schema does not authorize enrollment or production ownership changes.
BEGIN;
CREATE TABLE private.acquisition_activation (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 approval_ref text,
 application_revision text,
 verified_at timestamptz,
 CHECK(NOT enabled OR (length(trim(approval_ref))>0 AND approval_ref IS NOT NULL
  AND application_revision ~ '^[0-9a-f]{40}$' AND application_revision IS NOT NULL
  AND verified_at IS NOT NULL))
);
ALTER TABLE private.acquisition_activation ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_activation FROM PUBLIC,anon,authenticated,service_role;
INSERT INTO private.acquisition_activation(singleton) VALUES(true);

CREATE TABLE private.acquisition_activation_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 database_actor text NOT NULL,
 previous_state jsonb NOT NULL,
 new_state jsonb NOT NULL
);
ALTER TABLE private.acquisition_activation_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_activation_events FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.audit_acquisition_activation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Disable activation instead of deleting its state'; END IF;
 INSERT INTO private.acquisition_activation_events(database_actor,previous_state,new_state)
 VALUES(session_user,to_jsonb(OLD),to_jsonb(NEW));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_acquisition_activation() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_activation_audit BEFORE UPDATE OR DELETE ON private.acquisition_activation
 FOR EACH ROW EXECUTE FUNCTION private.audit_acquisition_activation();
CREATE FUNCTION private.preserve_acquisition_activation_events() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Activation evidence is append only'; END $$;
REVOKE ALL ON FUNCTION private.preserve_acquisition_activation_events() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_activation_events_immutable BEFORE UPDATE OR DELETE ON private.acquisition_activation_events
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_activation_events();

CREATE FUNCTION private.require_acquisition_activation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE active boolean;
BEGIN
 -- Revocation remains available while activation is disabled.
 IF TG_TABLE_NAME='workspace_memberships' AND to_jsonb(NEW)->>'status'='revoked' THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='workspaces' AND TG_OP='UPDATE' AND to_jsonb(NEW)->>'status'='suspended' THEN RETURN NEW; END IF;
 -- Hold the row lock through the transaction so disabling waits for in-flight
 -- enrollment/binding commits and subsequent operations observe disabled state.
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Acquisition activation approval required' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.require_acquisition_activation() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_activation_required BEFORE INSERT OR UPDATE ON public.workspaces
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT OR UPDATE ON public.workspace_memberships
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();
CREATE TRIGGER acquisition_activation_required BEFORE INSERT OR UPDATE ON public.workspace_leads
 FOR EACH ROW EXECUTE FUNCTION private.require_acquisition_activation();
COMMIT;
