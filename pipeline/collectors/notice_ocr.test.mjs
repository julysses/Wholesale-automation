import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { validateInputs, extractPage } from './notice_ocr.mjs';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

test('OCR binds complete county evidence to private resumable outputs and never certifies', async () => {
  const root = await mkdtemp(join(tmpdir(), 'notice-ocr-test-'));
  try {
    await mkdir(join(root, '123'));
    const html = '<p>synthetic</p>', image = Buffer.from('ffd8ff0001', 'hex');
    await writeFile(join(root, '123', 'detail.html'), html);
    await writeFile(join(root, '123', 'page-1.jpg'), image);
    const manifest = [{ document_id: '123', source_url: 'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/123',
      html_sha256: hash(html), expected_pages: 1, pages: [{ page: 1, sha256: hash(image) }] }];
    const [job] = await validateInputs(root, manifest);
    let calls = 0;
    const worker = { recognize: async bytes => { calls++; assert.deepEqual(bytes, image); return { data: { text: 'Synthetic address', confidence: 94, blocks: [] } }; } };
    const out = join(root, 'out');
    assert.equal((await extractPage(worker, job, out)).resumed, false);
    assert.equal((await extractPage(worker, job, out)).resumed, true);
    assert.equal(calls, 1);
    const file = join(out, '123', 'page-1.json'), saved = JSON.parse(await readFile(file));
    assert.equal(saved.verified, false); assert.equal(saved.trace_eligible, false);
    saved.text = 'altered'; await writeFile(file, JSON.stringify(saved));
    await assert.rejects(extractPage(worker, job, out), /Saved OCR mismatch/);
    await writeFile(join(root, '123', 'page-1.jpg'), Buffer.from('ffd8ff9999', 'hex'));
    await assert.rejects(validateInputs(root, manifest), /hash mismatch/);
    manifest[0].expected_pages = 2;
    await assert.rejects(validateInputs(root, manifest), /Incomplete notice/);
    manifest[0].document_id = '../123';
    await assert.rejects(validateInputs(root, manifest), /Invalid document identity/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('empty and low-confidence OCR are explicit review items', async () => {
  const root = await mkdtemp(join(tmpdir(), 'notice-ocr-review-'));
  try {
    const image = Buffer.from('image'), path = join(root, 'input'); await writeFile(path, image);
    const job = { document_id: '42', source_url: 'https://dallas.tx.publicsearch.us/doc/42', page: 1, image_sha256: hash(image), path };
    const worker = { recognize: async () => ({ data: { text: '', confidence: 0 } }) };
    const result = await extractPage(worker, job, join(root, 'out'));
    assert.equal(result.review_required, true);
    assert.equal((await extractPage(worker, job, join(root, 'out'))).review_required, true);
  } finally { await rm(root, { recursive: true, force: true }); }
});
