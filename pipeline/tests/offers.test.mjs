import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const admin=uid(1),user=uid(2),lead=uid(3);
const terms={price:'123456.78',closing_date:'2099-12-31',expires_at:'2099-10-01T00:00:00Z',recipient:'owner@example.invalid',channel:'email',conditions:'Subject to human-reviewed written agreement'};
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
 CREATE TABLE public.profiles(id uuid PRIMARY KEY,status text,role text);CREATE TABLE public.leads(id uuid PRIMARY KEY);
 INSERT INTO public.profiles VALUES('${admin}','approved','admin'),('${user}','approved','user');
 INSERT INTO public.leads VALUES('${lead}');GRANT SELECT ON public.profiles,public.leads TO service_role;`);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012213446_human_offer_review.sql',import.meta.url),'utf8'));
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012222753_offer_review_history.sql',import.meta.url),'utf8'));
 return db;
}
const record=async(db,id,version,action,revision,body=null,operator=admin)=>(await db.query('SELECT public.record_offer_review($1,$2,$3,$4,$5,$6,$7::jsonb) AS result',[uid(id),lead,operator,version,action,uid(revision),body===null?null:JSON.stringify(body)])).rows[0].result;
test('exact retries preserve audit identity and changed terms invalidate prior approval',async t=>{
 const db=await setup(t);
 const draft=await record(db,10,0,'draft',10,terms);assert.equal(draft.current.version,1);assert.equal(draft.current.approved,false);
 const approved=await record(db,11,1,'approve',10);assert.equal(approved.current.approved,true);assert.equal(approved.current.outbound_enabled,false);
 assert.equal((await record(db,11,1,'approve',10)).replayed,true);
 assert.equal((await record(db,12,2,'draft',12,{...terms,price:'130000'})).current.approved,false);
 assert.equal((await record(db,13,1,'approve',10)).conflict,true);
 assert.equal((await record(db,11,1,'approve',10)).current.approved,false);
 assert.equal((await record(db,10,0,'draft',10,{...terms,price:'1'})).conflict,true);
 assert.equal((await db.query('select count(*)::int AS n from offer_review.events')).rows[0].n,3);
});
test('revocation and lost-ACK replay cannot restore approval',async t=>{
 const db=await setup(t);await record(db,10,0,'draft',10,terms);await record(db,11,1,'approve',10);
 assert.equal((await record(db,12,2,'revoke',10)).current.approved,false);
 assert.equal((await record(db,11,1,'approve',10)).current.approved,false);
 assert.equal((await record(db,13,2,'approve',10)).conflict,true);
});
test('invalid and expired terms are rejected without events',async t=>{
 const db=await setup(t);
 for(const patch of [{price:'0'},{price:'NaN'},{price:'Infinity'},{price:'1.001'},{expires_at:'2020-01-01'},{closing_date:'2020-01-01'},{recipient:'wrong',channel:'sms'},{recipient:'wrong',channel:'email'},{conditions:''},{approved:true}]){
  assert.equal((await record(db,10,0,'draft',10,{...terms,...patch})).invalid,true);
 }
 assert.equal((await db.query('select count(*)::int AS n from offer_review.events')).rows[0].n,0);
});
test('browser roles and non-admin actors cannot create approvals or mutate audit events',async t=>{
 const db=await setup(t);
 await assert.rejects(record(db,10,0,'draft',10,terms,user),/administrator/);
 for(const role of ['anon','authenticated']){
  await db.exec(`SET ROLE ${role}`);
  await assert.rejects(record(db,10,0,'draft',10,terms),/permission denied/);
  await assert.rejects(db.query('select * from offer_review.events'),/permission denied/);
  await db.exec('RESET ROLE');
 }
 await db.exec('SET ROLE service_role');
 assert.equal((await record(db,10,0,'draft',10,terms)).current.version,1);
 await assert.rejects(db.query("update offer_review.events set action='approve'"),/permission denied/);
 await assert.rejects(db.query('delete from offer_review.events'),/permission denied/);
});

test('history preserves revoked actors and stable pages as new events arrive',async t=>{
 const db=await setup(t);
 for(let i=0;i<53;i++)await record(db,100+i,i,'draft',100+i,terms);
 const history=async(before=null,operator=admin)=>(await db.query('select public.offer_review_history($1,$2,$3) AS value',[lead,operator,before])).rows[0].value;
 const first=await history();assert.equal(first.events.length,50);assert.equal(first.next_before,3);
 await record(db,200,53,'approve',152);await record(db,201,54,'revoke',152);
 const second=await history(first.next_before);assert.deepEqual(second.events.map(e=>e.expected_version),[2,1,0]);assert.equal(second.next_before,null);
 const newest=await history();assert.equal(newest.events[0].action,'revoke');assert.equal(newest.events[0].operator_id,admin);
 await assert.rejects(history(null,user),/administrator/);
 for(const role of ['anon','authenticated']){await db.exec(`SET ROLE ${role}`);await assert.rejects(history(),/permission denied/);await db.exec('RESET ROLE');}
});
