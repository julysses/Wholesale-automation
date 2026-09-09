/** Input is newest first. Keep the latest decision, including COLD/disqualified results. */
export function latestByLead<T extends { lead_id: string | null }>(rows: T[]): T[] {
  const seen = new Set<string>();
  return rows.filter(row => {
    if (!row.lead_id || seen.has(row.lead_id)) return false;
    seen.add(row.lead_id);
    return true;
  });
}
