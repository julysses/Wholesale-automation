-- The API loads saved non-public settings at startup and resolves intake ownership.
-- BYPASSRLS does not replace table privileges.
GRANT SELECT ON TABLE public.app_settings TO service_role;
