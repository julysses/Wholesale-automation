-- Dedicated Edge ingress identity. Secret provisioning enables LOGIN separately.
-- No password or collector bearer token belongs in migration history or Git.
CREATE ROLE wholesale_ingest_edge NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
 INHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4;
GRANT wholesale_ingestor TO wholesale_ingest_edge;
GRANT CONNECT ON DATABASE postgres TO wholesale_ingest_edge;
ALTER ROLE wholesale_ingest_edge SET statement_timeout='15s';
ALTER ROLE wholesale_ingest_edge SET idle_in_transaction_session_timeout='15s';
