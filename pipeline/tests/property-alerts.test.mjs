import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
async function setup(t,legacy=false){
 const db=await database();t.after(()=>db.close());
 await db.exec(`CREATE TABLE public.app_notifications(id uuid PRIMARY KEY,recipient_id uuid,type text,title text,body text,action_url text,action_label text,metadata jsonb,read boolean DEFAULT false,read_at timestamptz);
 INSERT INTO public.profiles VALUES('${id(1)}','admin','approved');
 INSERT INTO public.app_settings VALUES('lead_owner_user_id','${id(1)}');
 INSERT INTO public.leads(id,property_address) VALUES('${id(2)}','TEST'),('${id(3)}','TEST2');`);
 if(legacy) await add(db,2);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261015022555_county_property_notifications.sql',import.meta.url),'utf8'));
 return db;
}
const add=(db,n)=>db.exec(`INSERT INTO wholesale_ingest.properties(id,state,county,address_std,lead_id) VALUES('${id(n+10)}','TX','Collin','TEST ${n}','${id(n)}')`);
test('new properties share one high-priority task and notification; replay stays read',async t=>{
 const db=await setup(t);await add(db,2);await add(db,3);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 assert.equal((await db.query('select metadata from public.app_notifications')).rows[0].metadata.property_count,2);
 await db.exec(`UPDATE public.app_notifications SET read=true;UPDATE wholesale_ingest.properties SET lead_id=lead_id;`);
 assert.equal((await db.query('select read from public.app_notifications')).rows[0].read,true);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.property_alert_events')).rows[0].n,2);
});
test('unassociated records do not alert; missing owner preserves recoverable events',async t=>{
 const db=await setup(t);await db.exec("DELETE FROM public.app_settings");await add(db,2);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,0);
 await db.exec(`INSERT INTO public.app_settings VALUES('lead_owner_user_id','${id(1)}');SELECT wholesale_ingest.publish_property_alerts();`);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 await db.exec('SET ROLE authenticated');await assert.rejects(db.exec('SELECT wholesale_ingest.publish_property_alerts()'),/permission denied/);
});

test('legacy associations do not become new alerts; first association does',async t=>{
 const db=await setup(t,true);
 await db.exec('UPDATE wholesale_ingest.properties SET lead_id=lead_id');
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,0);
 await db.exec(`INSERT INTO wholesale_ingest.properties(id,state,county,address_std) VALUES('${id(13)}','TX','Collin','TEST 3')`);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,0);
 await db.exec(`UPDATE wholesale_ingest.properties SET lead_id='${id(3)}' WHERE id='${id(13)}'`);
 assert.equal((await db.query('select metadata from public.app_notifications')).rows[0].metadata.property_count,1);
});
