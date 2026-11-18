import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const advisoryUrl = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf';
// Vite, Vitest and ESLint use repo-controlled patterns. The static app ships no picomatch.
const exceptionExpires = '2026-12-01T06:00:00Z';
const npmAudit = spawnSync('npm', ['audit', '--include=dev', '--audit-level=high', '--json'], {
  encoding: 'utf8',
});
if (npmAudit.error || ![0, 1].includes(npmAudit.status)) {
  throw new Error('Could not run the full npm audit', { cause: npmAudit.error });
}

const report = JSON.parse(npmAudit.stdout);
if (report?.auditReportVersion !== 2 || report.error || !report.vulnerabilities || !report.metadata?.vulnerabilities) {
  throw new Error('npm did not return a complete dependency audit report');
}

const findings = Object.entries(report.vulnerabilities);
const { total, high, critical } = report.metadata.vulnerabilities;
const hasBlockingSeverity = (severity) => severity === 'high' || severity === 'critical';
const blockingFindings = findings.filter(([, item]) => hasBlockingSeverity(item.severity));
if (![total, high, critical].every(Number.isInteger) || total !== findings.length || high + critical !== blockingFindings.length
  || npmAudit.status !== Number(high + critical > 0)) {
  throw new Error('npm returned inconsistent audit findings');
}

let blockingAdvisoryFound = false;
for (const [name, { nodes, via }] of findings) {
  // npm also reports affected dependents. Evaluate the advisories that cause those findings.
  if (!Array.isArray(via) || !via.length) throw new Error(`npm did not explain the finding for ${name}`);
  for (const advisory of via) {
    if (typeof advisory === 'string' && Object.hasOwn(report.vulnerabilities, advisory)) continue;
    if (!advisory?.url || !['info', 'low', 'moderate', 'high', 'critical'].includes(advisory.severity)) {
      throw new Error(`npm returned an invalid advisory for ${name}`);
    }

    const description = `${advisory.severity} ${name} ${advisory.url}`;
    if (!hasBlockingSeverity(advisory.severity)) {
      console.log(description);
      continue;
    }

    blockingAdvisoryFound = true;
    const installed = lock.packages['node_modules/picomatch'];
    if (name === 'picomatch' && advisory.severity === 'high' && advisory.url === advisoryUrl
      && nodes?.length === 1 && nodes[0] === 'node_modules/picomatch'
      && installed?.dev === true && installed.version === '4.0.7' && Date.now() < Date.parse(exceptionExpires)) {
      console.warn(`${description} (build tooling only, exception expires ${exceptionExpires})`);
      continue;
    }

    console.error(description);
    process.exitCode = 1;
  }
}

if (blockingFindings.length > 0 && !blockingAdvisoryFound) {
  throw new Error('npm omitted an advisory behind a blocking finding');
}
