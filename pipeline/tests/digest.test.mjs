import test from 'node:test';
import assert from 'node:assert/strict';
import {database} from './helpers.mjs';
async function seed(db){
 const day=(await db.query("select ((now() at time zone 'America/Chicago')::date)::text as day")).rows[0].day;
 await db.query("insert into wholesale_ingest.daily_digests(day,status,summary) values($1,'generated',$2)",[day,JSON.stringify({day,new_leads:7,sources:[]})]);
 return day;
}
const email='controlled@example.test';
async function reserve(db,day,id,recipient=email){return (await db.query('select public.reserve_list_digest($1,$2,$3) as result',[day,recipient,id])).rows[0].result;}
async function reconcile(db){return (await db.query('select public.reconcile_list_digests() as result')).rows[0].result;}

test('digest reservation freezes recipient, message identity and content; lost ACK is replayable before email claim',async()=>{
 const db=await database();try{
 const day=await seed(db), id=crypto.randomUUID();
 const first=await reserve(db,day,id);assert.equal(first.send_allowed,true);
 await db.query("update wholesale_ingest.daily_digests set summary='{\"new_leads\":999}'");
 const retry=await reserve(db,day,id);assert.equal(retry.summary.new_leads,7);
 assert.equal(retry.message_id,id);assert.equal(retry.send_allowed,true);
 await assert.rejects(()=>reserve(db,day,crypto.randomUUID()),/immutable/);
 await assert.rejects(()=>reserve(db,day,id,'changed@example.test'),/immutable/);
 await assert.rejects(()=>reserve(db,'2000-01-01',id),/current-day/);
 await db.query("insert into public.email_messages(id,recipient,provider,status) values($1,$2,'sendgrid','attempting')",[id,email]);
 assert.equal((await reserve(db,day,id)).send_allowed,false);
 const result=await reconcile(db);assert.equal(result.digests[0].status,'review');
 assert.equal(result.digests[0].delivered_at,null);
 }finally{await db.close();}
});

test('only matching delivered events confirm delivery; suppression cannot be erased by late delivered events',async()=>{
 const db=await database();try{
 const day=await seed(db), id=crypto.randomUUID();await reserve(db,day,id);
 await db.query("insert into public.email_messages(id,recipient,provider,status) values($1,$2,'sendgrid','accepted')",[id,email]);
 let result=await reconcile(db);assert.equal(result.digests[0].delivered_at,null);
 await db.query("insert into public.email_delivery_events values('wrong',$1,'wrong@example.test','delivered',now())",[id]);
 result=await reconcile(db);assert.equal(result.digests[0].delivered_at,null);
 await db.query("insert into public.email_delivery_events values('right',$1,$2,'delivered',($3::date+time '07:25') at time zone 'America/Chicago')",[id,email,day]);
 result=await reconcile(db);assert.equal(result.digests[0].status,'delivered');assert.equal(result.digests[0].on_time,true);
 await db.query("insert into public.email_delivery_events values('stop',$1,$2,'unsubscribe',now())",[id,email]);
 result=await reconcile(db);assert.equal(result.digests[0].status,'review');assert.equal(result.digests[0].error_code,'provider_failure_or_suppression');
 assert.equal((await reserve(db,day,id)).send_allowed,false);
 await db.exec('set role authenticated');await assert.rejects(()=>reserve(db,day,id),/permission denied/);await assert.rejects(()=>reconcile(db),/permission denied/);
 }finally{await db.close();}
});

test('missed deadline creates a single assigned task even without an email attempt; late delivery remains late',async()=>{
 const db=await database();try{
 const owner=crypto.randomUUID(), id=crypto.randomUUID();
 await db.query("insert into public.profiles values($1,'admin','approved')",[owner]);
 await db.query("insert into public.app_settings values('lead_owner_user_id',$1)",[owner]);
 const day=(await db.query("select ((now() at time zone 'America/Chicago')::date-1)::text as day")).rows[0].day;
 await db.query("insert into wholesale_ingest.daily_digests(day,status,summary,message_id,recipient) values($1,'generated','{}',$2,$3)",[day,id,email]);
 let result=await reconcile(db);assert.equal(result.digests[0].error_code,'delivery_unconfirmed_by_deadline');
 await reconcile(db);assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 await db.query("insert into public.email_messages(id,recipient,provider,status) values($1,$2,'sendgrid','accepted')",[id,email]);
 await db.query("insert into public.email_delivery_events values('late',$1,$2,'delivered',now())",[id,email]);
 result=await reconcile(db);assert.equal(result.digests[0].status,'delivered');assert.equal(result.digests[0].on_time,false);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 }finally{await db.close();}
});
