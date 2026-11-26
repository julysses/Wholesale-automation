import fs from 'node:fs';
export async function installAutomatic(db){
 // Local SQL stubs capture requests; these do not load network/cron extensions.
 await db.exec(`
 CREATE SCHEMA private;CREATE SCHEMA net;CREATE SCHEMA cron;CREATE SCHEMA vault;
 CREATE TABLE private.retell_sms_scheduler(enabled boolean);INSERT INTO private.retell_sms_scheduler VALUES(false);
 CREATE TABLE vault.decrypted_secrets(name text,decrypted_secret text);
 INSERT INTO vault.decrypted_secrets VALUES('retell_sms_worker_bearer','synthetic-test-only');
 CREATE TABLE net._http_response(id bigint,status_code int,timed_out boolean,content text);
 CREATE TABLE net.test_requests(id bigserial PRIMARY KEY,url text,body jsonb,headers jsonb,timeout_milliseconds int);
 CREATE FUNCTION net.http_post(url text,body jsonb,headers jsonb,timeout_milliseconds int) RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO net.test_requests(url,body,headers,timeout_milliseconds) VALUES($1,$2,$3,$4) RETURNING id $$;
 CREATE TABLE cron.job(jobid bigserial PRIMARY KEY,jobname text,schedule text,command text,active boolean DEFAULT true);
 CREATE FUNCTION cron.schedule(jobname text,schedule text,command text) RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO cron.job(jobname,schedule,command) VALUES($1,$2,$3) RETURNING jobid $$;
 CREATE FUNCTION cron.alter_job(job_id bigint,active boolean) RETURNS void LANGUAGE sql AS $$
  UPDATE cron.job SET active=$2 WHERE jobid=$1 $$;
 `);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261017020821_retell_app_automatic_queue.sql',import.meta.url),'utf8'));
}
