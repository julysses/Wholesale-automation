/** Offline OCR of saved county scans. Extraction never grants verification or tracing. */
import { readFile, writeFile, rename, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createWorker } from 'tesseract.js';
import eng from '@tesseract.js-data/eng';

const hash = value => createHash('sha256').update(value).digest('hex');
export const engine = 'tesseract.js/7.0.0-eng/1.0.0-lstm-blocks-v1';

export async function validateInputs(root, manifest) {
  if (!Array.isArray(manifest) || !manifest.length || manifest.length > 500) throw Error('Invalid manifest size');
  const seen = new Set(), jobs = [];
  for (const item of manifest) {
    const id = item.document_id;
    if (typeof id !== 'string' || !/^\d{1,30}$/.test(id) || seen.has(id)) throw Error('Invalid document identity');
    seen.add(id);
    const source = item.source_url;
    const extension = source === `https://dallas.tx.publicsearch.us/doc/${id}` ? 'png'
      : source === `https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/${id}` ? 'jpg' : null;
    if (!extension) throw Error('Invalid county URL');
    if (!Number.isInteger(item.expected_pages) || item.expected_pages < 1 || item.expected_pages > 100
      || !Array.isArray(item.pages) || item.pages.length !== item.expected_pages) throw Error('Incomplete notice');
    if (hash(await readFile(join(root, id, 'detail.html'))) !== item.html_sha256) throw Error('Summary hash mismatch');
    const hashes = new Set();
    for (const [index, page] of item.pages.entries()) {
      if (page.page !== index + 1 || !/^[a-f0-9]{64}$/.test(page.sha256) || hashes.has(page.sha256)) throw Error('Invalid page sequence');
      hashes.add(page.sha256);
      const path = join(root, id, `page-${page.page}.${extension}`), bytes = await readFile(path);
      const signature = extension === 'png' ? '89504e470d0a1a0a' : 'ffd8ff';
      if (!bytes.toString('hex', 0, signature.length / 2).startsWith(signature) || hash(bytes) !== page.sha256) throw Error('Page hash mismatch');
      jobs.push({ document_id: id, source_url: source, page: page.page, image_sha256: page.sha256, path });
    }
  }
  return jobs;
}

export async function extractPage(worker, job, output) {
  const folder = join(output, job.document_id), target = join(folder, `page-${job.page}.json`);
  try {
    const saved = JSON.parse(await readFile(target, 'utf8'));
    if (saved.engine !== engine || saved.document_id !== job.document_id || saved.page !== job.page
      || saved.source_url !== job.source_url || saved.image_sha256 !== job.image_sha256
      || saved.verified !== false || saved.trace_eligible !== false || typeof saved.text !== 'string'
      || saved.text_sha256 !== hash(saved.text) || !Number.isFinite(saved.confidence)
      || saved.confidence < 0 || saved.confidence > 100
      || saved.review_required !== (!saved.text.trim() || saved.confidence < 85)) throw Error('Saved OCR mismatch');
    return { resumed: true, review_required: saved.review_required };
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const bytes = await readFile(job.path);
  if (hash(bytes) !== job.image_sha256) throw Error('Image changed before OCR');
  const { data } = await worker.recognize(bytes, {}, { text: true, blocks: true });
  if (typeof data.text !== 'string' || !Number.isFinite(data.confidence) || data.confidence < 0 || data.confidence > 100) throw Error('Invalid OCR response');
  const receipt = {
    engine, document_id: job.document_id, source_url: job.source_url, page: job.page,
    image_sha256: job.image_sha256, extracted_at: new Date().toISOString(),
    text: data.text, text_sha256: hash(data.text), confidence: data.confidence,
    blocks: data.blocks ?? [], review_required: !data.text.trim() || data.confidence < 85,
    verified: false, trace_eligible: false,
  };
  await mkdir(folder, { recursive: true, mode: 0o700 });
  await writeFile(target + '.tmp', JSON.stringify(receipt), { mode: 0o600 });
  await rename(target + '.tmp', target);
  return { resumed: false, review_required: receipt.review_required };
}

export async function run(root, manifestPath, output, concurrency = 2) {
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 4) throw Error('Concurrency must be 1–4');
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const jobs = await validateInputs(root, manifest);
  await mkdir(output, { recursive: true, mode: 0o700 });
  // All code and English language data come from pinned, local npm packages.
  // Images are passed as bytes, never URLs; no remote OCR or model API is used.
  let cursor = 0, completed = 0, resumed = 0, reviewRequired = 0;
  const errors = [];
  await Promise.all(Array.from({ length: concurrency }, async () => {
    const worker = await createWorker('eng', 1, { langPath: eng.langPath, gzip: true, cacheMethod: 'none' });
    try {
      while (cursor < jobs.length) {
        const job = jobs[cursor++];
        try {
          const result = await extractPage(worker, job, output);
          completed++; resumed += Number(result.resumed); reviewRequired += Number(result.review_required);
        } catch (error) { errors.push({ document_id: job.document_id, page: job.page, error: error.message }); }
        if ((completed + errors.length) % 10 === 0) console.log(JSON.stringify({ completed, total: jobs.length, failed: errors.length }));
      }
    } finally { await worker.terminate(); }
  }));
  const result = { engine, completed, expected_pages: jobs.length, resumed, review_required_pages: reviewRequired,
    errors, verified: false, trace_eligible: false, finished_at: new Date().toISOString() };
  await writeFile(join(output, 'summary.json.tmp'), JSON.stringify(result, null, 2), { mode: 0o600 });
  await rename(join(output, 'summary.json.tmp'), join(output, 'summary.json'));
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [, , root, manifest, output, concurrency = '2'] = process.argv;
  if (!root || !manifest || !output) throw Error('Usage: notice_ocr.mjs root manifest.json output [concurrency 1–4]');
  const result = await run(root, manifest, output, Number(concurrency));
  console.log(JSON.stringify(result));
  if (result.errors.length) process.exitCode = 1;
}
