import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
import {fixture, job} from './retell-app-transport-fixture.mjs';
const migration = fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020184154_facebook_inquiry_sms_receipts.sql', import.meta.url), 'utf8');

test('native inquiry FK, exact source, immutability and private grants preserve website jobs', async t => {
 const db = new PGlite(); t.after(() => db.close());
 const {q} = await fixture(db);
 const before = await q('select to_jsonb(j) row from public.retell_form_sms_jobs j order by id');
 await db.exec(migration);
 const after = await q("select to_jsonb(j)-'facebook_submission_id' row from public.retell_form_sms_jobs j order by id");
 assert.deepEqual(after, before);
 const receipt=crypto.randomUUID(), lead=crypto.randomUUID(), next=crypto.randomUUID(), phone='+12145550125';
 await db.query('insert into public.leads(id) values($1)',[lead]);
 assert.equal((await db.query("select relrowsecurity enabled from pg_class where oid='public.facebook_lead_submissions'::regclass")).rows[0].enabled,true);
 await db.exec('SET ROLE service_role');
 await db.query(`insert into public.facebook_lead_submissions(id,lead_id,leadgen_id,form_id,submitted_at,phone_number,raw_answers)
  values($1,$2,'meta-1','form-1','2026-10-20T17:00:00Z',$3,'{}')`,[receipt,lead,phone]);
 assert.equal((await db.query('select id from public.facebook_lead_submissions where id=$1',[receipt])).rows.length,1);
 await db.exec('RESET ROLE');
 const insert = (id, source, owner=lead, recipient=phone) => db.query(`insert into public.retell_form_sms_jobs
  (id,lead_id,submission_id,facebook_submission_id,phone_number,due_at,expires_at)
  values($1,$2,$3,$4,$5,now(),now()+interval '15 minutes')`,[id,owner,source,receipt,recipient]);
 await assert.rejects(insert(next,job)); // Both source identities prohibited.
 await assert.rejects(insert(next,null,job)); // Wrong lead prohibited.
 await assert.rejects(insert(next,null,lead,'+12145550126'));
 await insert(next,null);
 await assert.rejects(db.query('update public.retell_form_sms_jobs set facebook_submission_id=null,submission_id=$1 where id=$2',[job,next]));
 await assert.rejects(db.query('update public.facebook_lead_submissions set submitted_at=now()::text where id=$1',[receipt]));
 await assert.rejects(db.query('delete from public.facebook_lead_submissions where id=$1',[receipt]));
 for(const role of ['anon','authenticated']) {
  const [rights] = await db.query(`select has_table_privilege($1,'public.facebook_lead_submissions','select') s,
   has_table_privilege($1,'public.facebook_lead_submissions','insert') i,
   has_table_privilege($1,'public.facebook_lead_submissions','update') u,
   has_table_privilege($1,'public.facebook_lead_submissions','delete') d`,[role]).then(r=>r.rows);
  assert.deepEqual(rights,{s:false,i:false,u:false,d:false});
 }
 const [server] = (await db.query(`select has_table_privilege('service_role','public.facebook_lead_submissions','update') u,
  has_table_privilege('service_role','public.facebook_lead_submissions','delete') d`)).rows;
 assert.deepEqual(server,{u:false,d:false});
});
