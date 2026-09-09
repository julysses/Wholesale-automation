// Keep existing findings visible while making new lint regressions block CI.
import { ESLint } from 'eslint';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const eslint = new ESLint();
const results = await eslint.lintFiles(['.']);
const baseline = JSON.parse(readFileSync(new URL('../lint-baseline.json', import.meta.url)));
const counts = {};
for (const result of results) {
  for (const message of result.messages) {
    const key = JSON.stringify([path.relative(process.cwd(), result.filePath), message.ruleId, message.message.split('\n')[0]]);
    counts[key] = (counts[key] ?? 0) + 1;
  }
}
const regressions = Object.entries(counts).filter(([key, count]) => count > (baseline[key] ?? 0));
if (regressions.length) {
  for (const [key, count] of regressions) console.error(`${key}: ${count} findings (baseline ${baseline[key] ?? 0})`);
  process.exitCode = 1;
} else {
  console.log(`No new lint findings. ${Object.values(counts).reduce((a, b) => a + b, 0)} existing findings remain; npm run lint lists them.`);
}
