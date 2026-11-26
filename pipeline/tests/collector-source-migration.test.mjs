import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const sql = fs.readFileSync(new URL('../../frontend/supabase/migrations/20261013154257_dallas_foreclosure_public_search.sql', import.meta.url), 'utf8');
test('source correction preserves disabled state and other sources and replays safely', async () => {
  const db = await database();
  try {
    const before = (await db.query('SELECT * FROM wholesale_ingest.sources ORDER BY source_key')).rows;
    await db.exec(sql); await db.exec(sql);
    const after = (await db.query('SELECT * FROM wholesale_ingest.sources ORDER BY source_key')).rows;
    for (let i = 0; i < before.length; i++) {
      if (before[i].source_key !== 'tx-dallas-pre_foreclosure') assert.deepEqual(after[i], before[i]);
      else {
        assert.equal(after[i].source_url, 'https://dallas.tx.publicsearch.us/');
        assert.equal(after[i].enabled, false);
        assert.deepEqual(after[i].allowed_hosts, ['dallas.tx.publicsearch.us', 'www.dallascounty.org']);
        assert.deepEqual({...after[i], source_url: before[i].source_url, allowed_hosts: before[i].allowed_hosts}, before[i]);
      }
    }
  } finally { await db.close(); }
});
test('source correction does not overwrite an operator customized endpoint', async () => {
  const db = await database();
  try {
    await db.exec("UPDATE wholesale_ingest.sources SET source_url='https://www.dallascounty.org/operator-custom' WHERE source_key='tx-dallas-pre_foreclosure'");
    const before = (await db.query('SELECT * FROM wholesale_ingest.sources ORDER BY source_key')).rows;
    await db.exec(sql);
    assert.deepEqual((await db.query('SELECT * FROM wholesale_ingest.sources ORDER BY source_key')).rows, before);
  } finally { await db.close(); }
});
