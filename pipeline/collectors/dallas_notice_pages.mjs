/** Capture original scans through a CUA tab's documented pageAssets capability. */
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const prefix = 'https://dallas.tx.publicsearch.us/doc/';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const png = Buffer.from([137,80,78,71,13,10,26,10]);
export function pageState(snapshot) {
  const matches = [...snapshot.matchAll(/spinbutton "Page (\d+) of (\d+)"/g)];
  if (matches.length !== 1) throw Error('Missing unique Dallas page counter');
  const page = Number(matches[0][1]), total = Number(matches[0][2]);
  if (page < 1 || total < page || total > 100) throw Error('Invalid Dallas page counter');
  return {page,total};
}
export function validateScan(bytes) {
  if (bytes.length < 24 || bytes.length > 30_000_000 || !bytes.subarray(0,8).equals(png)) throw Error('Invalid Dallas PNG');
  const width=bytes.readUInt32BE(16),height=bytes.readUInt32BE(20);
  if(width<1000 || height<1000 || width>15000 || height>15000) throw Error('Dallas scan resolution out of bounds');
  return {width,height};
}
async function saveJson(path,value) {
  await writeFile(path+'.tmp',JSON.stringify(value,null,2),{mode:0o600}); await rename(path+'.tmp',path);
}
async function preserveFile(path,bytes) {
  try { if(hash(await readFile(path))!==hash(bytes)) throw Error('Saved Dallas evidence changed'); }
  catch(error) { if(error.code!=='ENOENT') throw error; await writeFile(path,bytes,{mode:0o600,flag:'wx'}); }
}

export async function captureDallasNotice(tab,assets,root,document) {
  const {document_id:id,document_number:number,document_url:url}=document;
  if(!/^\d{1,30}$/.test(id) || !/^\d{1,30}$/.test(number) || url!==prefix+id) throw Error('Invalid Dallas document identity');
  const folder=join(root,id); await mkdir(folder,{recursive:true,mode:0o700});
  let completed;
  try { completed=await readFile(join(folder,'all-pages-capture.json'),'utf8'); }
  catch(error) { if(error.code!=='ENOENT') throw error; }
  if(completed!==undefined) {
    const saved=JSON.parse(completed);
    const receipt=JSON.parse(await readFile(join(folder,'receipt.json'),'utf8'));
    if(saved.document_id!==id || saved.source_url!==url || receipt.document_id!==id || receipt.source_url!==url || receipt.document_number!==number
      || saved.all_pages_reviewed!==false || saved.trace_eligible!==false || receipt.trace_eligible!==false
      || !Number.isInteger(saved.expected_pages) || saved.expected_pages<1 || saved.expected_pages>100
      || saved.expected_pages!==receipt.notice_pages_expected || saved.pages.length!==saved.expected_pages
      || hash(await readFile(join(folder,'detail.html')))!==receipt.html_sha256) throw Error('Saved Dallas capture mismatch');
    const seen=new Set();
    for(const [i,p] of saved.pages.entries()) {
      const bytes=await readFile(join(folder,`page-${i+1}.png`)); validateScan(bytes);
      if(p.page!==i+1 || hash(bytes)!==p.sha256 || seen.has(p.sha256)) throw Error('Saved Dallas page hash mismatch');
      seen.add(p.sha256);
    }
    if(saved.pages[0].sha256!==receipt.page_1_sha256) throw Error('Saved Dallas first page mismatch');
    return {document_id:id,pages:saved.pages.length,resumed:true};
  }

  if(await tab.url()!==url) await tab.goto(url);
  await tab.playwright.getByRole('spinbutton',{name:/^Page \d+ of \d+$/}).waitFor({state:'visible',timeoutMs:20000});
  if(pageState(await tab.playwright.domSnapshot()).page!==1) {
    await tab.playwright.getByRole('button',{name:'Go To First Page',exact:true}).click({});
    await tab.playwright.getByRole('spinbutton',{name:/^Page 1 of \d+$/}).waitFor({state:'visible',timeoutMs:15000});
  }
  const initial=pageState(await tab.playwright.domSnapshot());
  if(initial.page!==1) throw Error('Dallas viewer must start at page one');
  const summary=tab.playwright.locator('#tabpanel-summary');
  const text=(await summary.innerText({})).replace(/\s+/g,' ');
  if(!text.includes(`Document Number: ${number}`) || !text.includes(`Number of Pages: ${initial.total}`)) throw Error('Dallas summary identity mismatch');
  const html=await summary.evaluate(el=>el.outerHTML);
  await preserveFile(join(folder,'detail.html'),Buffer.from(html));
  const pages=[];
  for(let n=1;n<=initial.total;n++) {
    const state=pageState(await tab.playwright.domSnapshot());
    if(state.page!==n || state.total!==initial.total) throw Error('Dallas pagination changed');
    await tab.playwright.locator(`svg[aria-label="Document preview image"] image[*|href*="_${n}.png"]`).waitFor({state:'attached',timeoutMs:15000});
    const shown=await tab.playwright.getByRole('img',{name:'Document preview image',exact:true})
      .evaluate(el=>el.querySelector('image')?.getAttribute('xlink:href'));
    const inventory=await assets.list();
    const matching=inventory.assets.filter(a=>a.kind==='image' && a.url===shown);
    if(!shown || matching.length!==1 || !new URL(shown).pathname.endsWith(`_${n}.png`)) throw Error('Displayed Dallas scan is not uniquely bound to page');
    const bundle=await assets.bundle({inventoryId:inventory.id,assetIds:[matching[0].id]});
    if(bundle.summary.downloadedCount!==1 || bundle.summary.failedCount!==0 || bundle.assets.length!==1
      || bundle.assets[0].id!==matching[0].id || bundle.assets[0].contentType!=='image/png') throw Error('Dallas original scan download not confirmed');
    const bytes=await readFile(bundle.assets[0].path); const dimensions=validateScan(bytes),sha256=hash(bytes);
    if(pages.some(p=>p.sha256===sha256)) throw Error('Duplicate Dallas page image');
    const after=pageState(await tab.playwright.domSnapshot());
    if(after.page!==n || after.total!==initial.total) throw Error('Dallas page changed during download');
    await preserveFile(join(folder,`page-${n}.png`),bytes);
    pages.push({page:n,sha256,...dimensions});
    if(n===1) await saveJson(join(folder,'receipt.json'),{
      document_id:id,document_number:number,source_url:url,captured_at:new Date().toISOString(),
      html_sha256:hash(html),page_1_sha256:sha256,notice_pages_expected:initial.total,image_extension:'png',
      filed_date:document.filed_date,auction_date:document.auction_date,
      all_notice_pages_reviewed:false,identity_verified:false,current_status_verified:false,trace_eligible:false,
    });
    await saveJson(join(folder,'capture-progress.json'),{document_id:id,source_url:url,expected_pages:initial.total,pages});
    if(n<initial.total) {
      await tab.playwright.getByRole('button',{name:'Go To Next Page',exact:true}).click({});
      await tab.playwright.getByRole('spinbutton',{name:`Page ${n+1} of ${initial.total}`,exact:true}).waitFor({state:'visible',timeoutMs:15000});
    }
  }
  if(await tab.playwright.getByRole('button',{name:'Go To Next Page',exact:true}).isEnabled()) throw Error('Dallas viewer still has pages');
  await saveJson(join(folder,'all-pages-capture.json'),{document_id:id,source_url:url,captured_at:new Date().toISOString(),expected_pages:initial.total,pages,all_pages_reviewed:false,trace_eligible:false});
  return {document_id:id,pages:pages.length,resumed:false};
}
