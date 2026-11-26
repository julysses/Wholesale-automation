import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { PGlite } from '@electric-sql/pglite';

const migrations = new URL('../../frontend/supabase/migrations/', import.meta.url);
const original = fs.readFileSync(new URL('20260929060000_lead_retention.sql', migrations), 'utf8');
const fix = fs.readFileSync(new URL('20261016230511_protect_website_inquiry_retention.sql', migrations), 'utf8');

test('website inquiry receipts survive duplicate and age-based list cleanup', async t => {
  const db = new PGlite(); t.after(() => db.close());
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE TABLE public.leads (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz DEFAULT now()-interval '2 years',
      updated_at timestamptz DEFAULT now(), source text, status text DEFAULT 'new', dnc boolean DEFAULT false,
      contact_attempts int DEFAULT 0, last_contact_date date, property_type text,
      property_address text DEFAULT '123 Main St', city text DEFAULT 'Dallas', total_score int DEFAULT 0,
      form_submission_id uuid, inbound_channel text, internal_notes text DEFAULT 'Preserve inquiry');
    CREATE FUNCTION public.lead_street_key(text) RETURNS text LANGUAGE sql IMMUTABLE AS 'SELECT lower($1)';`);
  await db.exec(original.slice(0, original.indexOf('-- Daily refresh')));
  const add = async row => (await db.query(`INSERT INTO public.leads
    SELECT * FROM jsonb_populate_record(NULL::public.leads,
      jsonb_build_object('id',gen_random_uuid(),'created_at',now()-interval '2 years',
      'updated_at',now(),'status','new','property_address','123 Main St','city','Dallas',
      'total_score',0,'internal_notes','Preserve inquiry') || $1::jsonb) RETURNING id`,[JSON.stringify(row)])).rows[0].id;
  const imported = await add({source:'County export',total_score:15});
  const inquiry = await add({source:'web_form',form_submission_id:crypto.randomUUID(),inbound_channel:'web_form'});
  const oldCold = await add({source:'web_form',status:'qualified_cold',property_address:'456 Main St'});
  await db.query('SELECT public.refresh_lead_retention()');
  assert.equal((await db.query('SELECT retention_rule FROM public.leads WHERE id=$1',[inquiry])).rows[0].retention_rule,'duplicates');
  const importedBefore=(await db.query('SELECT * FROM public.leads WHERE id=$1',[imported])).rows[0];
  const contentsBefore=(await db.query(`SELECT id,form_submission_id,internal_notes FROM public.leads ORDER BY id`)).rows;
  await db.exec(fix);
  for(const id of [inquiry,oldCold]){
    const row=(await db.query('SELECT retention_rule,retention_deletable,retention_due_at FROM public.leads WHERE id=$1',[id])).rows[0];
    assert.deepEqual(row,{retention_rule:'website_inquiry',retention_deletable:false,retention_due_at:null});
  }
  assert.deepEqual((await db.query('SELECT * FROM public.leads WHERE id=$1',[imported])).rows[0],importedBefore);
  assert.deepEqual((await db.query('SELECT id,form_submission_id,internal_notes FROM public.leads ORDER BY id')).rows,contentsBefore);
  for(const rule of ['duplicates','stale_prefor','stale_cold','stale_warm','stale_tax_roll','not_real_estate']){
    const ids=(await db.query('SELECT public.lead_cleanup_ids($1) AS id',[rule])).rows.map(r=>r.id);
    assert.ok(!ids.includes(inquiry) && !ids.includes(oldCold));
  }
  // Each marker independently protects a future inquiry, even when imported fields are misleading.
  for(const marker of [{source:'web_form'},{source:'web-form'},{inbound_channel:'web_form'},
    {inbound_channel:'web-form'},{form_submission_id:crypto.randomUUID()}]){
    const id=await add({source:'tax roll',status:'qualified_cold',property_type:'mineral',...marker});
    assert.equal((await db.query('SELECT retention_deletable FROM public.leads WHERE id=$1',[id])).rows[0].retention_deletable,false);
    const verdict=(await db.query('SELECT r.* FROM public.leads l CROSS JOIN LATERAL public.lead_retention_calc(l,true) r WHERE id=$1',[id])).rows[0];
    assert.equal(verdict.o_rule,'website_inquiry'); assert.equal(verdict.o_deletable,false);
  }
  // Adding a receipt or inbound marker to an existing duplicate must replace the stale verdict immediately.
  for(const field of ['form_submission_id','inbound_channel']){
    const id=await add({source:'County export'});
    await db.query('SELECT public.refresh_lead_retention()');
    assert.equal((await db.query('SELECT retention_rule FROM public.leads WHERE id=$1',[id])).rows[0].retention_rule,'duplicates');
    await db.query(`UPDATE public.leads SET ${field}=$2 WHERE id=$1`,[id,field==='form_submission_id'?crypto.randomUUID():'web_form']);
    assert.equal((await db.query('SELECT retention_rule FROM public.leads WHERE id=$1',[id])).rows[0].retention_rule,'website_inquiry');
  }
  for(const [status,dnc,expected] of [['new',true,'dnc'],['offer_made',false,'transaction']]){
    const id=await add({source:'web_form',status,dnc});
    const row=(await db.query('SELECT retention_rule,retention_deletable FROM public.leads WHERE id=$1',[id])).rows[0];
    assert.deepEqual(row,{retention_rule:expected,retention_deletable:false});
  }
  // Ordinary stale import cleanup remains available, and private cleanup RPC access stays private.
  const stale=await add({source:'County export',status:'qualified_cold',property_address:'789 Other St'});
  assert.ok((await db.query("SELECT public.lead_cleanup_ids('stale_cold') AS id")).rows.some(r=>r.id===stale));
  assert.deepEqual((await db.query("SELECT has_function_privilege('authenticated','public.lead_cleanup_ids(text)','execute') AS browser, has_function_privilege('service_role','public.lead_cleanup_ids(text)','execute') AS server")).rows,[{browser:false,server:true}]);
});
