-- Apply only to the authorized rehearsal project tbhwxgfzbiaqjurghntj after
-- migration 20261014200149 and two successful supervise_bulk_pipeline checks.
-- This is receipt monitoring, NOT an unattended county/PropStream worker.
SELECT cron.schedule('wholesaleos-bulk-supervision','*/5 * * * *',
 'select wholesale_ingest.supervise_bulk_pipeline();');
SELECT jobid,jobname,schedule,active FROM cron.job WHERE jobname='wholesaleos-bulk-supervision';
-- Pause without deleting evidence:
-- SELECT cron.alter_job(jobid,active:=false) FROM cron.job WHERE jobname='wholesaleos-bulk-supervision';
