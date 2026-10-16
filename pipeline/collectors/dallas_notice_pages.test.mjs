import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {captureDallasNotice,pageState,validateScan} from './dallas_notice_pages.mjs';
const doc={document_id:'123',document_number:'202600001',document_url:'https://dallas.tx.publicsearch.us/doc/123'};
function scan(n){const b=Buffer.alloc(25);Buffer.from([137,80,78,71,13,10,26,10]).copy(b);b.writeUInt32BE(2552,16);b.writeUInt32BE(3344,20);b[24]=n;return b;}
async function fixture(t,{stale=false,duplicate=false,wrong=false,fail=false}={}){
 const root=await mkdtemp(join(tmpdir(),'dallas-capture-'));t.after(()=>rm(root,{recursive:true,force:true}));
 let page=1,calls=0;const url=()=>`https://scan.example/100_${stale?1:page}.png`;
 const tab={url:async()=>doc.document_url,goto:async()=>{throw Error('unexpected navigation');},playwright:{
  domSnapshot:async()=>`- spinbutton "Page ${page} of 2": "${page}"`,
  locator:()=>({waitFor:async()=>{},innerText:async()=>`Document Number: ${wrong?'999':doc.document_number} Number of Pages: 2`,evaluate:async()=>'<div>summary</div>'}),
  getByRole:(role)=>({waitFor:async()=>{},evaluate:async()=>url(),click:async()=>{page++;},isEnabled:async()=>page<2})
 }};
 const assets={list:async()=>({id:'inventory',assets:[{id:'asset',kind:'image',url:url()}]}),bundle:async()=>{
  calls++;if(fail&&page===2)throw Error('download interrupted');const path=join(root,'download.png');await writeFile(path,scan(duplicate?1:page));
  return {summary:{downloadedCount:1,failedCount:0},assets:[{id:'asset',path,contentType:'image/png'}]};
 }};
 return {root,tab,assets,calls:()=>calls};
}
test('requires a unique bounded viewer counter and full resolution PNG',()=>{
 assert.deepEqual(pageState('- spinbutton "Page 2 of 4"'),{page:2,total:4});
 for(const s of ['', 'spinbutton "Page 0 of 4"','spinbutton "Page 1 of 101"','spinbutton "Page 1 of 2" spinbutton "Page 2 of 2"'])assert.throws(()=>pageState(s));
 assert.deepEqual(validateScan(scan(1)),{width:2552,height:3344});assert.throws(()=>validateScan(Buffer.from('not a scan')));
 const small=scan(1);small.writeUInt32BE(20,16);assert.throws(()=>validateScan(small));
});
test('captures every original page, hashes evidence, resumes without browser access',async t=>{
 const f=await fixture(t);assert.deepEqual(await captureDallasNotice(f.tab,f.assets,f.root,doc),{document_id:'123',pages:2,resumed:false});
 assert.equal(f.calls(),2);const saved=JSON.parse(await readFile(join(f.root,'123/all-pages-capture.json')));assert.equal(saved.trace_eligible,false);
 assert.deepEqual(await captureDallasNotice({},null,f.root,doc),{document_id:'123',pages:2,resumed:true});
 await rm(join(f.root,'123/page-2.png'));await assert.rejects(captureDallasNotice({},null,f.root,doc),{code:'ENOENT'});
});
test('rejects corrupt completed evidence without silently recapturing',async t=>{
 const f=await fixture(t);await captureDallasNotice(f.tab,f.assets,f.root,doc);await writeFile(join(f.root,'123/page-2.png'),scan(9));
 await assert.rejects(captureDallasNotice({},null,f.root,doc),/hash mismatch/);
});
for(const [name,opts,reason] of [['stale image',{stale:true},/bound to page/],['duplicate scan',{duplicate:true},/Duplicate Dallas/],['interruption',{fail:true},/interrupted/]])
 test(`${name} preserves partial evidence and cannot claim completion`,async t=>{
  const f=await fixture(t,opts);await assert.rejects(captureDallasNotice(f.tab,f.assets,f.root,doc),reason);
  const progress=JSON.parse(await readFile(join(f.root,'123/capture-progress.json')));assert.equal(progress.pages.length,1);
  await assert.rejects(readFile(join(f.root,'123/all-pages-capture.json')),{code:'ENOENT'});
 });
test('rejects document identity mismatch before downloading',async t=>{
 const f=await fixture(t,{wrong:true});await assert.rejects(captureDallasNotice(f.tab,f.assets,f.root,doc),/identity mismatch/);assert.equal(f.calls(),0);
 await assert.rejects(captureDallasNotice(f.tab,f.assets,f.root,{...doc,document_url:'https://example.com'}),/Invalid Dallas/);
});
