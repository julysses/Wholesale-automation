/** Run with a CUA tab in the approved browser session. No credential/API access. */
import { readFile, writeFile, rename } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
const prefix = 'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
export function pageState(snapshot) {
  const matches = [...snapshot.matchAll(/Page\s*:\s*(\d+) of (\d+)/g)];
  if (matches.length !== 1) throw Error('Missing unique page counter');
  const page = Number(matches[0][1]), total = Number(matches[0][2]);
  if (page < 1 || total < page || total > 100) throw Error('Invalid page counter');
  return { page, total };
}
export async function captureNotice(tab, root, documentId) {
  if (!/^\d{1,30}$/.test(documentId)) throw Error('Invalid document ID');
  const folder = join(root, documentId), receipt = JSON.parse(await readFile(join(folder, 'receipt.json'), 'utf8'));
  if (receipt.document_id !== documentId || receipt.source_url !== prefix + documentId) throw Error('Receipt identity mismatch');
  if (!Number.isInteger(receipt.notice_pages_expected) || receipt.notice_pages_expected < 1 || receipt.notice_pages_expected > 100) throw Error('Invalid expected page count');
  const target = join(folder, 'all-pages-capture.json');
  try {
    const saved = JSON.parse(await readFile(target, 'utf8'));
    if (saved.document_id !== documentId || saved.source_url !== receipt.source_url || saved.expected_pages !== receipt.notice_pages_expected || saved.pages.length !== saved.expected_pages) throw Error('Saved capture mismatch');
    for (const [index, page] of saved.pages.entries()) {
      if (page.page !== index + 1 || hash(await readFile(join(folder, `page-${page.page}.jpg`))) !== page.sha256) throw Error('Saved page hash mismatch');
    }
    if (saved.pages[0].sha256 !== receipt.page_1_sha256) throw Error('First-page evidence changed');
    return { document_id: documentId, pages: saved.pages.length, resumed: true };
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await tab.goto(receipt.source_url);
  const pages = [];
  for (let number = 1; number <= receipt.notice_pages_expected; number++) {
    const state = pageState(await tab.playwright.domSnapshot());
    if (state.page !== number || state.total !== receipt.notice_pages_expected) throw Error('County pagination changed');
    const src = await tab.playwright.getByRole('img', { name: 'Scan of Foreclosure Notice', exact: true }).getAttribute('src');
    if (!src?.startsWith('data:image/jpeg;base64,') || src.length > 10000000) throw Error('Invalid county scan');
    const bytes = Buffer.from(src.split(',')[1], 'base64'), sha256 = hash(bytes);
    if (bytes[0] !== 255 || bytes[1] !== 216 || bytes[2] !== 255) throw Error('Invalid JPEG');
    if (number === 1 && sha256 !== receipt.page_1_sha256) throw Error('County first-page evidence changed; refresh detail before capture');
    if (pages.some(page => page.sha256 === sha256)) throw Error('Duplicate page image; hold notice for review');
    await writeFile(join(folder, `page-${number}.jpg`), bytes, { mode: 0o600 });
    pages.push({ page: number, sha256 });
    if (number < state.total) {
      await tab.playwright.getByRole('button', { name: 'Next Page', exact: true }).click();
      try {
        await tab.playwright.getByText(`Page : ${number + 1} of ${state.total}`, { exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 });
      } catch (error) {
        // The server-rendered viewer can show controls before Blazor attaches them.
        // Retry only after observing that the page has not changed at all.
        const unchanged = pageState(await tab.playwright.domSnapshot());
        if (unchanged.total !== state.total || ![number, number + 1].includes(unchanged.page)) throw error;
        if (unchanged.page === number) {
        const current = await tab.playwright.getByRole('img', { name: 'Scan of Foreclosure Notice', exact: true }).getAttribute('src');
        if (current !== src) throw error;
        await tab.playwright.getByRole('button', { name: 'Next Page', exact: true }).click();
        await tab.playwright.getByText(`Page : ${number + 1} of ${state.total}`, { exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 });
        }
      }
    }
  }
  if (await tab.playwright.getByRole('button', { name: 'Next Page', exact: true }).isEnabled()) throw Error('County viewer has more pages');
  const saved = { document_id: documentId, source_url: receipt.source_url, captured_at: new Date().toISOString(), expected_pages: receipt.notice_pages_expected, pages, all_pages_reviewed: false, trace_eligible: false };
  await writeFile(target + '.tmp', JSON.stringify(saved, null, 2), { mode: 0o600 });
  await rename(target + '.tmp', target);
  return { document_id: documentId, pages: pages.length, resumed: false };
}
