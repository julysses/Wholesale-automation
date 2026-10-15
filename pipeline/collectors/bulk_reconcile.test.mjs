import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {runReconciliation} from './bulk_reconcile.mjs';
test('single batch entrypoint replays deterministically and keeps exclusions and holds',async()=>{
 const root=await mkdtemp(join(tmpdir(),'bulk-reconcile-'));
 try{
  const fixtures={queue:{properties:[{identity:{property_address:'1 TEST LN',city:'ANNA',state:'TX',zip:'75409',parcel_id:'R-1'},owner_name:'EXAMPLE OWNER',notices:[{document_id:'1',auction_date:'2026-11-03'}]}]},
   provider:{job:'A123',status:'complete',rows:[{url:'https://app.propstream.com/contact/A123/123',cells:['EXAMPLE OWNER','(214)-555-0100 DNC','','','','1 TEST LN ANNA TX 75409','','Owner','Group']}]},
   inventory:{url:'https://www.auction.com/residential/tx/collin-county',captured_at:'2026-10-14T18:00:00Z',rows:[]}};
  for(const [key,value]of Object.entries(fixtures))await writeFile(join(root,key+'.json'),JSON.stringify(value));
  await writeFile(join(root,'config.json'),JSON.stringify({queue:'queue.json',provider:'provider.json',inventory:'inventory.json',day:'2026-10-14',output:'out'}));
  const a=await runReconciliation(join(root,'config.json')),b=await runReconciliation(join(root,'config.json'));
  assert.equal(a.batch_id,b.batch_id);assert.equal(a.dnc_exclusions,1);assert.equal(a.outreach_ready,0);
  const packet=JSON.parse(await readFile(join(a.output,'reconciliation.json')));
  assert.equal(packet.items[0].trace_again,false);assert.ok(packet.items[0].exceptions.includes('current_listing_not_found'));
  fixtures.provider.status='processing';await writeFile(join(root,'provider.json'),JSON.stringify(fixtures.provider));
  await assert.rejects(runReconciliation(join(root,'config.json')),/Complete/);
 }finally{await rm(root,{recursive:true,force:true});}
});
