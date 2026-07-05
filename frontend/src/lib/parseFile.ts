/**
 * parseSpreadsheet — read a dropped lead list into rows, regardless of format.
 *
 * Handles CSV plus real Excel workbooks (.xlsx / .xls). PropStream, county
 * appraisal-district, and skip-trace exports are frequently Excel, not CSV;
 * feeding those raw bytes to a CSV parser produces binary garbage. This reads
 * the first worksheet of an Excel file into the same string[][] shape a CSV
 * parse produces, so the rest of the import pipeline is format-agnostic.
 *
 * Returns ALL rows including the header row at index 0. The xlsx library is
 * dynamically imported so it only loads when someone actually imports a file.
 */

import Papa from 'papaparse';

export function isExcelFile(name: string): boolean {
  const n = name.toLowerCase();
  return n.endsWith('.xlsx') || n.endsWith('.xls') || n.endsWith('.xlsm');
}

export function isSupportedFile(name: string): boolean {
  return name.toLowerCase().endsWith('.csv') || isExcelFile(name);
}

async function parseExcel(file: File): Promise<string[][]> {
  const XLSX = await import('xlsx');
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: 'array' });
  const firstSheetName = wb.SheetNames[0];
  if (!firstSheetName) return [];
  const sheet = wb.Sheets[firstSheetName];
  // header:1 → array-of-arrays; raw:false → formatted strings (dates, numbers as shown)
  const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, {
    header: 1, blankrows: false, defval: '', raw: false,
  });
  return rows.map((r) => (Array.isArray(r) ? r.map((c) => (c == null ? '' : String(c))) : []));
}

function parseCSV(file: File): Promise<string[][]> {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: false,
      skipEmptyLines: true,
      complete: (res) => resolve(res.data as string[][]),
      error: reject,
    });
  });
}

export async function parseSpreadsheet(file: File): Promise<string[][]> {
  const rows = isExcelFile(file.name) ? await parseExcel(file) : await parseCSV(file);
  // Drop fully-empty rows so the header row and previews are clean
  return rows.filter((r) => Array.isArray(r) && r.some((c) => c && String(c).trim()));
}
