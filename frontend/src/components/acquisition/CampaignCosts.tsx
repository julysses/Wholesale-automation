import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { costWindow, readCostCoverage, usdMinor } from '@/lib/costCoverage';
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const statusLabels = { complete: 'Complete cost coverage', incomplete: 'Incomplete cost coverage', requires_review: 'Attribution review required', unavailable: 'Cost reporting unavailable' };
export function CampaignCosts({ userId, workspace, campaign }: { userId: string; workspace: string; campaign: string }) {
  const [open, setOpen] = useState(false); const [start, setStart] = useState(''); const [end, setEnd] = useState('');
  const [window, setWindow] = useState<{ start: string; end: string } | null>(null);
  const valid = costWindow(start, end) !== null;
  const matching = !!window && window.start === start && window.end === end;
  const query = useQuery({ queryKey: ['campaign-costs', userId, workspace, campaign, window?.start, window?.end], enabled: open && matching,
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false,
    queryFn: ({ signal }) => readCostCoverage(workspace, campaign, window!.start, window!.end, signal) });
  return <section aria-label="Campaign cost coverage" className="mt-3 space-y-3">
    <button className={button} aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide campaign costs' : 'View campaign costs'}</button>
    {open && <><p className="text-sm">Reviewed cost evidence, separate from the planned budget. Dates use the ad account’s reporting timezone. Missing evidence stays unavailable.</p>
      <div className="flex flex-wrap gap-3"><label>Cost start date<input type="date" className="block rounded border p-2" value={start} onChange={event => setStart(event.target.value)}/></label><label>Cost end date<input type="date" className="block rounded border p-2" value={end} onChange={event => setEnd(event.target.value)}/></label></div>
      <button className={button} disabled={!valid || query.isFetching} onClick={() => { if (matching) void query.refetch(); else setWindow({ start, end }); }}>Load cost coverage</button>
      {!valid && (start || end) && <p>Select a valid range of up to 366 days.</p>}
      {matching && (query.isFetching ? <p role="status">Checking campaign costs…</p> : query.isError ? <p role="alert">Cost coverage could not be verified. Refresh and check workspace access.</p> : query.data && <>
        <h4 className="font-semibold">{statusLabels[query.data.status]}</h4>
        <p className="text-sm">{query.data.reporting_timezone ? `Reporting timezone: ${query.data.reporting_timezone}` : 'Account reporting timezone is not yet established.'}</p>
        <dl className="grid gap-2 sm:grid-cols-2"><div><dt>Reporting-window total (USD)</dt><dd className="font-semibold">{usdMinor(query.data.total_cost_minor)}</dd></div><div><dt>Observed amount (USD; may be partial)</dt><dd>{usdMinor(query.data.observed_cost_minor)}</dd></div></dl>
        {query.data.status === 'requires_review' && <p>Campaign attribution changed. Totals are unavailable; historical daily evidence is retained below.</p>}
        <p className="text-sm">Cost per lead: unavailable until inquiry and conversion counts are reconciled.</p>
        <p className="text-xs break-all">Evidence cutoff: {query.data.as_of}. Campaign attribution is checked at read time.</p>
        {query.data.days.length > 0 && <details><summary className="cursor-pointer">Daily cost evidence ({query.data.complete_days} of {query.data.requested_days} days complete)</summary><ol className="mt-2 space-y-2">{query.data.days.map(day => <li key={day.date} className="border-t pt-2 text-sm break-all"><strong>{day.date} · {day.coverage}</strong><p>{day.attribution_current === false ? 'Historical amount' : 'Recorded amount'}: {usdMinor(day.amount_minor)}</p>{day.revision_id && <><p>Revision {day.revision}: {day.revision_id}</p><p>Campaign review: {day.link_review_id}</p><p>{day.attribution_current ? 'Current reviewed attribution' : 'Attribution is no longer current'}</p></>}</li>)}</ol></details>}
      </>)}
    </>}
  </section>;
}
