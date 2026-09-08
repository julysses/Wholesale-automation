import { expect, it } from 'vitest';
import * as XLSX from 'xlsx';
import { parseSpreadsheet } from '@/lib/parseFile';

it.each(['xlsx', 'xls'] as const)('imports a real %s workbook with the patched parser', async bookType => {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([
    ['Address', 'Price'], ['Test Property', 150000], [],
  ]), 'Leads');
  const bytes = XLSX.write(workbook, { bookType, type: 'array' });
  const file = new File([bytes], `leads.${bookType}`);
  Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes });
  expect(await parseSpreadsheet(file)).toEqual([['Address', 'Price'], ['Test Property', '150000']]);
});
