import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pageState } from './collin_notice_pages.mjs';
test('parses the observed county page counter', () => assert.deepEqual(pageState('- paragraph: "Page : 1 of 5"'), {page:1,total:5}));
test('rejects missing, ambiguous and unbounded pagination', () => {
 for (const value of ['', 'Page : 1 of 5 Page : 1 of 5', 'Page : 0 of 2', 'Page : 3 of 2', 'Page : 1 of 101']) assert.throws(() => pageState(value));
});
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { captureNotice } from './collin_notice_pages.mjs';

test('captures all pages, tolerates one inert click, resumes without browser use and rejects tampered files', async () => {
 const root=await mkdtemp(join(tmpdir(),'collin-pages-'));
 try {
  await mkdir(join(root,'123'));
  const images=[Buffer.from([255,216,255,1]),Buffer.from([255,216,255,2])];
  const receipt={document_id:'123',source_url:'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/123',notice_pages_expected:2,page_1_sha256:createHash('sha256').update(images[0]).digest('hex')};
  await writeFile(join(root,'123','receipt.json'),JSON.stringify(receipt));
  let page=1, clicks=0, navigations=0;
  const tab={goto:async()=>{navigations++;page=1;},playwright:{
   domSnapshot:async()=>`Page : ${page} of 2`,
   getByRole:role=>role==='img'?{getAttribute:async()=>`data:image/jpeg;base64,${images[page-1].toString('base64')}`}:{click:async()=>{if(++clicks>1)page++;},isEnabled:async()=>page<2},
   getByText:text=>({waitFor:async()=>{if(text!==`Page : ${page} of 2`)throw Error('not advanced');}}),
  }};
  assert.equal((await captureNotice(tab,root,'123')).pages,2);
  const saved=JSON.parse(await readFile(join(root,'123','all-pages-capture.json')));
  assert.equal(saved.trace_eligible,false);assert.equal(saved.all_pages_reviewed,false);
  assert.equal((await captureNotice(tab,root,'123')).resumed,true);assert.equal(navigations,1);
  await writeFile(join(root,'123','page-2.jpg'),'tampered');
  await assert.rejects(captureNotice(tab,root,'123'),/hash mismatch/);
 }finally{await rm(root,{recursive:true,force:true});}
});
