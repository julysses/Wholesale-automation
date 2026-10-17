import fs from 'node:fs';
const read=name=>fs.readFileSync(new URL('../../frontend/supabase/migrations/'+name,import.meta.url),'utf8');
export async function installRecovery(db){
 await db.exec(`
 ALTER TABLE public.lead_form_submissions ADD COLUMN lead_id uuid, ADD COLUMN created_at timestamptz DEFAULT now(), ADD COLUMN processing_status text DEFAULT 'processed';
 ALTER TABLE public.retell_call_requests ADD COLUMN lead_id uuid;
 CREATE TABLE public.webhook_jobs(id uuid,created_at timestamptz,status text);
 CREATE TABLE public.sms_nurture_jobs(id uuid,lead_id uuid,created_at timestamptz,claimed_at timestamptz,due_at timestamptz,status text);
 CREATE TABLE public.email_messages(id uuid,created_at timestamptz,status text,recipient text);
 CREATE TABLE public.email_delivery_events(message_id uuid,recipient text,event text);
 CREATE TABLE public.appointments(id uuid,lead_id uuid,scheduled_at timestamptz,status text);
 CREATE TABLE public.app_notifications(id uuid PRIMARY KEY,recipient_id uuid,type text,title text,body text,action_url text,action_label text,lead_id uuid,metadata jsonb,created_at timestamptz DEFAULT now());
 CREATE TABLE public.launch_monitor_incidents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),category text,reference uuid,lead_id uuid,first_seen timestamptz DEFAULT now(),resolved_at timestamptz,UNIQUE(category,reference));
 CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,priority text,status text,type text,lead_id uuid,assigned_to uuid,due_date timestamptz);
 CREATE TABLE public.app_settings(key text,value text);
 CREATE TABLE public.profiles(id uuid,status text);
 INSERT INTO public.profiles VALUES('00000000-0000-4000-8000-000000000777','approved');
 INSERT INTO public.app_settings VALUES('lead_owner_user_id','00000000-0000-4000-8000-000000000777');
 CREATE FUNCTION public.launch_monitor_snapshot() RETURNS jsonb LANGUAGE sql AS $$ SELECT '{}'::jsonb $$;
 `);
 await db.exec(read('20261017015318_retell_app_recovery_monitoring.sql'));
 const scan=read('20261008220647_launch_monitoring.sql').split('CREATE FUNCTION public.scan_launch_monitor()')[1];
 await db.exec('CREATE FUNCTION public.scan_launch_monitor()'+scan);
 await db.exec(read('20261008221221_reopen_monitor_incidents.sql'));
}
