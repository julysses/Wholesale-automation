import { apiFetch } from '@/lib/api';

export interface OutreachSummary {
  sent: number;
  failed: number;
  skipped: number;
  dryRun: number;
  logFailed: number;
  unresolved: number;
  unattempted: number;
  interrupted: boolean;
  error?: string;
}

/** Never retry a batch whose request may already have reached the provider. */
export async function sendOutreachBatches(
  endpoint: string,
  recipientField: 'buyer_ids' | 'lead_ids',
  recipientIds: string[],
  payload: Record<string, unknown> = {},
): Promise<OutreachSummary> {
  const ids = [...new Set(recipientIds)];
  const summary: OutreachSummary = { sent: 0, failed: 0, skipped: 0, dryRun: 0, logFailed: 0, unresolved: 0, unattempted: 0, interrupted: false };
  for (let offset = 0; offset < ids.length; offset += 5) {
    const batch = ids.slice(offset, offset + 5);
    try {
      const response = await apiFetch(endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, [recipientField]: batch }),
      });
      const result = await response.json();
      const count = (key: string): number => {
        const value = result[key];
        if (!Number.isSafeInteger(value) || value < 0) throw new Error('The server did not confirm complete delivery results.');
        return value;
      };
      const sent = count('sent_count'), failed = count('failed_count'), skipped = count('skipped_count'), dryRun = count('dry_run_count');
      const logFailed = count('log_failed_count');
      if (sent + failed + skipped + dryRun !== batch.length) throw new Error('The server did not confirm every recipient in this batch.');
      summary.sent += sent;
      summary.failed += failed;
      summary.skipped += skipped;
      summary.dryRun += dryRun;
      summary.logFailed += logFailed;
    } catch (error) {
      summary.interrupted = true;
      summary.unresolved = batch.length;
      summary.unattempted = ids.length - offset - batch.length;
      summary.error = error instanceof Error ? error.message : 'Request interrupted';
      break;
    }
  }
  return summary;
}

export function outreachResultText(summary: OutreachSummary): string {
  const counts = `${summary.sent} accepted by provider, ${summary.failed} failed, ${summary.skipped} skipped, ${summary.dryRun} dry run, ${summary.logFailed} activity-log updates failed.`;
  if (!summary.interrupted) return counts;
  return `${counts} ${summary.unresolved} recipients have unknown results; ${summary.unattempted} were not attempted. ${summary.error || 'Request interrupted'}. Review provider and outreach activity before starting another send; unknown recipients may already have received it.`;
}
