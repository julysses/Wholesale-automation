import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseTitleHistory, parseTitleHistoryDetail, type TitleHistoryRecord } from '@/lib/acquisition/title-history';
import { titleFindingNames, titleLabels } from '@/lib/acquisition/title-review';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const statuses = { approved: 'Approval recorded', requires_resolution: 'Resolution hold recorded', withdrawn: 'Decision withdrawn' };
type Props = { context: DocumentContext; disabled: boolean };
export function TitleReviewHistory(props: Props) {
  return <History key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function History({ context, disabled }: Props) {
  const [expanded, setExpanded] = useState(false), [cursors, setCursors] = useState<(number | null)[]>([null]), [selected, setSelected] = useState('');
  const before = cursors.at(-1)!, scope = [context.userId, context.workspaceId, context.contractId, context.contractVersion];
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}/title-review/history`;
  const options = { enabled: expanded && !disabled, retry: false, staleTime: 0, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const history = useQuery({ ...options, queryKey: ['title-history', ...scope, 'page', before],
    queryFn: async ({ signal }) => parseTitleHistory(await (await apiFetch(`${base}?limit=20${before === null ? '' : `&before=${before}`}`, { signal, cache: 'no-store' })).json(), context, before) });
  const record = useQuery({ ...options, enabled: options.enabled && !!selected, queryKey: ['title-history', ...scope, 'record', selected],
    queryFn: async ({ signal }) => parseTitleHistoryDetail(await (await apiFetch(`${base}/${selected}`, { signal, cache: 'no-store' })).json(), context, selected) });
  function close() { setExpanded(false); setSelected(''); setCursors([null]); }
  return <section aria-label="Title decision history" className="rounded-xl border bg-white p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Title decision history</h3><p className="text-sm text-gray-600">Read the original findings and next actions for contract version {context.contractVersion}. Recorded approvals are historical; current checks and disposition approval are separate.</p>
    {!expanded ? <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>View title history</button> : <>
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={disabled || history.isFetching || record.isFetching} onClick={() => { void history.refetch(); if (selected) void record.refetch(); }}>Refresh title history</button><button type="button" className={button} onClick={close}>Close title history</button></div>
      {disabled ? <p role="status" className="text-sm">Finish the open contract step before reading history.</p> : <>
        {history.isError ? <p role="alert">Title history could not be confirmed. Refresh to try again.</p> : history.isFetching ? <p role="status">Loading title history…</p> : history.data && <>
          {!history.data.items.length && <p>No title decisions recorded for this version.</p>}
          <ol className="space-y-3">{history.data.items.map(row => <li key={row.id} className="rounded-lg border p-3 space-y-2 min-w-0"><h4 className="font-medium">Decision {row.sequence} · {statuses[row.status]}</h4>
            <p className="text-xs text-gray-600">Recorded {new Date(row.created_at).toLocaleString()} · Report from version {row.source_version}</p><p className="text-sm whitespace-pre-wrap break-words">{row.note}</p>
            <button type="button" className={button} disabled={record.isFetching} onClick={() => setSelected(row.id)}>Read decision {row.sequence}</button></li>)}</ol>
          <nav aria-label="Title history pages" className="flex flex-wrap gap-2"><button type="button" className={button} disabled={cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setSelected(''); }}>Newer title decisions</button><button type="button" className={button} disabled={history.data.next_before === null} onClick={() => { if (history.data.next_before !== null) { setCursors(c => [...c, history.data.next_before]); setSelected(''); } }}>Older title decisions</button></nav>
        </>}
        {selected && <div className="rounded-lg border border-orange-200 bg-orange-50/40 p-3 min-w-0 space-y-3">
          {record.isError ? <p role="alert">The original decision could not be confirmed. Refresh to try again.</p> : record.isFetching ? <p role="status">Loading original title findings…</p> : record.data && <>
            <RecordedFindings row={record.data.record} />
            {record.data.record.title_original_review_id && <button type="button" className={button} onClick={() => setSelected(record.data.record.title_original_review_id!)}>Read the withdrawn original decision</button>}
          </>}
          <button type="button" className={button} onClick={() => setSelected('')}>Close decision details</button>
        </div>}
      </>}
    </>}
  </section>;
}
function RecordedFindings({ row }: { row: TitleHistoryRecord }) {
  const findings = row.title_findings;
  return <><h4 className="font-semibold">Original decision {row.sequence} · {statuses[row.status]}</h4>
    <p className="text-sm whitespace-pre-wrap break-words">{row.note}</p>
    {row.expires_at && <p className="text-xs">Original approval expiry: {row.expires_at}. This does not establish current approval.</p>}
    {findings && <><p className="text-sm">Original report cutoff: {findings.report_as_of.precision === 'unknown' ? 'Unknown' : findings.report_as_of.precision === 'date' ? `${findings.report_as_of.calendar_date} (calendar date only)` : findings.report_as_of.instant}.</p>
      {findings.report_as_of_source && <p className="text-sm break-words">Cutoff source: {findings.report_as_of_source.locator} · Original version {findings.report_as_of_source.artifact_version}</p>}
      <p className="text-sm whitespace-pre-wrap break-words">{findings.report_note}</p>
      {titleFindingNames.map(name => { const finding = findings[name]; return <div key={name} className="rounded-lg border bg-white p-3 space-y-2 min-w-0"><h5 className="font-medium">{titleLabels[name]} · {finding.finding.replaceAll('_', ' ')}</h5><p className="text-sm whitespace-pre-wrap break-words">{finding.note}</p>
        {finding.required_action && <p className="text-sm whitespace-pre-wrap break-words"><strong>Next action:</strong> {finding.required_action}</p>}
        {finding.sources.map((s, i) => <p key={i} className="text-xs break-all">Source {i + 1}: {s.locator} · Original version {s.artifact_version}</p>)}
      </div>; })}
      <details className="text-xs"><summary className="cursor-pointer font-medium">Original source identifiers</summary><div className="space-y-2 mt-2"><p className="break-all">Recorded reviewer: {row.actor_id}</p>{row.title_sources?.map(s => <p key={s.artifact_id} className="break-all">{s.purpose.replaceAll('_', ' ')} · version {s.source_version} · {s.artifact_id}<br />SHA-256: {s.sha256}</p>)}</div></details>
    </>}
  </>;
}
