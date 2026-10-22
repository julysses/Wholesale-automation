import { useRef } from 'react';
import { apiFetch } from '@/lib/api';

type CsvPayload = {
  rows: unknown[];
  engine: 'rules' | 'ai';
  score_with_claude: boolean;
  list_name: string;
  filename: string;
};
export type CsvImportResult = {
  status: 'ok'; request_id: string; replayed: boolean;
  imported: number; updated: number; skipped: number; scored: number | null;
  consolidated_rows: number; owner_review: number;
  scoring_state: 'disabled' | 'completed' | 'pending' | 'submitting' | 'review' | 'unconfirmed';
  warning?: string | null;
};

/** Explicit attempts reuse the original reference while prepared content is unchanged. */
export function useCsvImport(reference?: string | null) {
  const prepared = useRef<{ key: string; body: string; id: string } | null>(null);
  return async (payload: CsvPayload): Promise<CsvImportResult> => {
    const key = JSON.stringify(payload);
    if (!prepared.current || prepared.current.key !== key) {
      const id = reference || crypto.randomUUID();
      prepared.current = { key, id, body: JSON.stringify({ ...payload, request_id: id }) };
    }
    const attempt = prepared.current;
    if (new TextEncoder().encode(attempt.body).byteLength > 4_500_000) {
      throw new Error('This upload exceeds the 4.5 MB request limit. Split it into smaller files; no rows were submitted.');
    }
    const response = await apiFetch('/api/ai/import-master-list', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: attempt.body,
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.detail || 'Import outcome unconfirmed. Retry the original import.');
    const counts = ['imported', 'updated', 'skipped', 'consolidated_rows', 'owner_review'] as const;
    if (saved.status !== 'ok' || saved.request_id !== attempt.id || typeof saved.replayed !== 'boolean'
      || counts.some(k => !Number.isInteger(saved[k]) || saved[k] < 0)
      || saved.imported + saved.updated !== saved.consolidated_rows
      || saved.consolidated_rows > payload.rows.length
      || (saved.scored === null ? saved.scoring_state !== 'unconfirmed'
        : !Number.isInteger(saved.scored) || saved.scored < 0 || saved.scored > saved.consolidated_rows)
      || saved.owner_review > saved.updated
      || !['disabled', 'completed', 'pending', 'submitting', 'review', 'unconfirmed'].includes(saved.scoring_state)
      || (saved.warning != null && typeof saved.warning !== 'string')) {
      throw new Error('The server did not confirm this import reference and outcome. Retry the original import.');
    }
    return saved as CsvImportResult;
  };
}
