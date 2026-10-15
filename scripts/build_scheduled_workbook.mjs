// Run on demand inside GPT with the bundled artifact-tool runtime. No daemon.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw Error('Usage: build_scheduled_workbook.mjs workbook-input.json output.xlsx');
const packet = JSON.parse(await fs.readFile(input, 'utf8'));
const workbook = Workbook.create();
for (const spec of packet.sheets) {
  const sheet = workbook.worksheets.add(spec.name);
  sheet.showGridLines = false;
  const values = [spec.headers, ...spec.rows].map(row => row.map(value =>
    typeof value === 'string' && /^\s*[=+@-]/.test(value) ? "'" + value : value));
  const range = sheet.getRangeByIndexes(0, 0, values.length, spec.headers.length);
  if (spec.name !== 'Batch status') range.setNumberFormat('@');
  range.values = values;
  range.format.font = {name:'Arial', size:10};
  range.format.rowHeight = 24;
  range.format.columnWidth = 24;
  range.format.verticalAlignment = 'center';
  sheet.getRangeByIndexes(0, 0, 1, spec.headers.length).format = {
    fill:'#24364B', font:{name:'Arial', size:10, bold:true, color:'#FFFFFF'}, rowHeight:28,
  };
  if (spec.name === 'Batch status') {
    sheet.getRange('A1:A12').format.columnWidth = 38;
    sheet.getRange('B1:B12').format.columnWidth = 100;
  } else {
    sheet.freezePanes.freezeRows(1);
    sheet.freezePanes.freezeColumns(1);
    if (spec.rows.length) sheet.tables.add(range, true, spec.name.replaceAll(' ', '') + 'Table');
    if (spec.name === 'Completed properties') {
      sheet.getRange('B1:B500').format.columnWidth = 32;
      sheet.getRange('E1:E500').format.columnWidth = 60;
      sheet.getRange('F1:H500').format.columnWidth = 42;
      sheet.getRange('E2:H500').format.wrapText = true;
      range.format.rowHeight = 55;
    }
    if (spec.name === 'Excluded phones') sheet.getRange('D1:D500').format.columnWidth = 40;
  }
}
workbook.recalculate();
await fs.mkdir(path.dirname(output), {recursive:true, mode:0o700});
for (const spec of packet.sheets) {
  const preview = await workbook.render({sheetName:spec.name,
    range: spec.name === 'Completed properties' ? 'A1:H5' : spec.name === 'Batch status' ? 'A1:B11' : 'A1:D8',
    scale:1, format:'png'});
  await fs.writeFile(path.join(path.dirname(output), spec.name.replaceAll(' ', '-') + '.png'),
    new Uint8Array(await preview.arrayBuffer()), {mode:0o600});
}
console.log((await workbook.inspect({kind:'table',range:"'Batch status'!A1:B11",maxChars:2500,tableMaxRows:11,tableMaxCols:2})).ndjson);
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(output);
await fs.chmod(output, 0o600);
console.log(JSON.stringify({output,sheets:packet.sheets.length}));
