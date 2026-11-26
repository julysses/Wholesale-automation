import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
export async function database() {
 const db=new PGlite();
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
   CREATE TABLE public.profiles(id uuid PRIMARY KEY,role text,status text);
   CREATE TABLE public.leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),property_address text,city text,state text,zip_code text,source text,motivation_tag text,status text,owner_mailing_address text,sms_sequence_active boolean,email_sequence_active boolean);
   CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,status text,priority text,type text,assigned_to uuid,due_date timestamptz);
   CREATE TABLE public.app_settings(key text,value text);
   CREATE TABLE public.email_messages(id uuid PRIMARY KEY,recipient text,provider text,status text,created_at timestamptz DEFAULT now());
   CREATE TABLE public.email_delivery_events(event_id text PRIMARY KEY,message_id uuid,recipient text,event text,occurred_at timestamptz);`);
  const dir = new URL('../../frontend/supabase/migrations/', import.meta.url);
  for (const suffix of ['_daily_list_ingestion.sql','_list_operations.sql','_list_review_batch_guard.sql','_list_monitor_receipts.sql','_list_digest_delivery.sql']) {
   const file = fs.readdirSync(dir).find(x => x.endsWith(suffix));
   await db.exec(fs.readFileSync(new URL(file,dir),'utf8'));
  }
 return db;
}
