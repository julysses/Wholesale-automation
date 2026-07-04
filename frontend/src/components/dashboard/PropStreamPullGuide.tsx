/**
 * PropStreamPullGuide
 *
 * Strategy-specific PropStream list-pull instructions, shown under Workflow
 * step 3 ("Import Your First Leads"). Reads the strategy chosen in the
 * StrategyComparisonPanel (localStorage 'acquisition_strategy') and lays out
 * exactly which Quick Lists to pull, which filters to set, and which columns
 * to include in the export so the CSV drops straight into the Leads importer
 * with columns auto-mapped.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Database, Filter, ListChecks, Download, Lightbulb, ArrowRight } from 'lucide-react';
import { STRATEGIES, type StrategyKey } from './FunnelPanel';

const STORAGE_KEY = 'acquisition_strategy';

interface PullSpec {
  volume: string;
  headline: string;
  quickLists: { name: string; note: string }[];
  filters: string[];
  countyNote?: string;
  tip: string;
}

const PULL_SPECS: Record<StrategyKey, PullSpec> = {
  mass: {
    volume: '~30,000 leads',
    headline: 'Broad single-signal pulls — volume over precision. Pull each Quick List as a separate export and label the source column so stack analytics can compare list performance later.',
    quickLists: [
      { name: 'Absentee Owners (out-of-state)', note: 'your largest list — target ~15k' },
      { name: 'Absentee Owners (in-state)',     note: 'second pull — target ~8k' },
      { name: 'High Equity',                    note: 'owner-occupied 40%+ equity — ~4k' },
      { name: 'Pre-Foreclosures',               note: 'every active NOD/lis pendens in your counties' },
      { name: 'Vacant Properties',              note: 'USPS-flagged vacancies' },
    ],
    filters: [
      'Property Type: Single Family Residence (add Duplex–Fourplex if you buy small multis)',
      'Estimated Equity: 40% or higher',
      'Ownership Length: 7+ years',
      'Last Sale Date: 7+ years ago (skip recent flips)',
      'Location: your target counties — pull one county at a time to stay under export caps',
      'Exclude: active listings (On Market = No)',
    ],
    tip: 'PropStream caps single exports (typically 10k rows). Split large pulls by county or zip range, then import each CSV — the importer dedupes by address automatically.',
  },

  precision: {
    volume: '~2,000 leads (Top 2,000 list)',
    headline: 'Stacked distress only — every lead must show 2+ distress signals. Start with the tightest PropStream stack, then enrich with the county data PropStream can\'t see.',
    quickLists: [
      { name: 'Absentee Owner + Vacant',           note: 'stack these two filters in one search — your core list' },
      { name: 'Absentee + Pre-Foreclosure',        note: 'second stack — highest urgency' },
      { name: 'Vacant + Liens',                    note: 'municipal/HOA/tax liens on empty houses' },
      { name: 'Absentee + Tax Delinquent (county)', note: 'match your county tax-delinquent roll against absentee pulls' },
    ],
    filters: [
      'Property Type: Single Family Residence',
      'Estimated Equity: 50% or higher (Free & Clear is the strongest signal)',
      'Ownership Length: 10+ years',
      'Owner Type: Individual (exclude LLCs/corporate for this strategy)',
      'Year Built: 2005 or older (deferred-maintenance profile)',
      'Location: your target counties only',
    ],
    countyNote: 'PropStream covers absentee, vacancy, pre-foreclosure, and liens. The remaining government signals this app scores — tax delinquency, code violations, utility shutoffs, and probate — come from county/municipal records. Request those lists from your county, import them with the matching source label, and the stacking engine combines all signals per address.',
    tip: 'Quality bar: if a stacked search returns more than ~2,500 rows, tighten equity to 60%+ or ownership to 15+ years. You want the 2,000 most distressed, not the first 2,000.',
  },

  hybrid: {
    volume: '~5,000 leads (Tier 1 + Tier 2 stacks)',
    headline: 'Tier 1 (3+ signals) and Tier 2 (2 signals) only — skip every single-signal list. This is the Precision stack widened one ring outward.',
    quickLists: [
      { name: 'Absentee + Vacant + Pre-Foreclosure', note: 'Tier 1 core — export everything that matches' },
      { name: 'Absentee + Vacant',                   note: 'Tier 2 — largest stacked pull, ~2.5k' },
      { name: 'Absentee + Liens',                    note: 'Tier 2 — municipal/HOA/tax liens' },
      { name: 'Vacant + Pre-Foreclosure',            note: 'Tier 2 — includes "zombie" properties' },
      { name: 'High Equity + Tax Delinquent (county)', note: 'match county tax roll against 50%+ equity pulls' },
    ],
    filters: [
      'Property Type: Single Family Residence',
      'Estimated Equity: 45% or higher',
      'Ownership Length: 8+ years',
      'Owner Type: Individual preferred; keep LLCs only when they stack 3+ signals',
      'Location: your target counties',
      'Exclude: active listings and sold within last 12 months',
    ],
    countyNote: 'Add county tax-delinquent, code-violation, and probate lists as separate imports — the stacking engine promotes any address that appears on multiple lists into Tier 1 automatically.',
    tip: 'Import Tier 1 stacks first and start dialing them while the Tier 2 lists load. Deal flow starts with the deepest-stacked 500, not the full 5,000.',
  },
};

/** Columns to include in the PropStream export — matches the CSV importer's auto-map */
const EXPORT_COLUMNS = [
  'Address', 'City', 'State', 'Zip', 'Owner 1 First Name', 'Owner 1 Last Name',
  'Phone', 'Email', 'Bedrooms', 'Bathrooms', 'SqFt',
];

export function PropStreamPullGuide() {
  const [strategy, setStrategy] = useState<StrategyKey | null>(() => {
    try { return (localStorage.getItem(STORAGE_KEY) as StrategyKey) || null; }
    catch { return null; }
  });

  useEffect(() => {
    const handler = (e: Event) => setStrategy((e as CustomEvent<StrategyKey>).detail);
    window.addEventListener('strategyChange', handler);
    return () => window.removeEventListener('strategyChange', handler);
  }, []);

  // No strategy picked yet — point at step 2 instead of guessing
  if (!strategy || !PULL_SPECS[strategy]) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 flex items-center gap-2">
        <Lightbulb className="h-4 w-4 shrink-0" />
        <span>
          Pick your acquisition strategy first — the PropStream pull list depends on it.
        </span>
        <Link to="/#strategy" className="ml-auto shrink-0 font-bold text-amber-900 hover:underline flex items-center gap-1">
          Open Strategy Selector <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    );
  }

  const spec = PULL_SPECS[strategy];
  const label = STRATEGIES[strategy].label;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-[#1B3A5C] px-4 py-3 flex items-center gap-2">
        <Database className="h-4 w-4 text-[#E8720C]" />
        <span className="text-sm font-bold text-white">PropStream Pull — {label}</span>
        <span className="ml-auto text-xs font-bold text-white bg-white/15 px-2 py-0.5 rounded-full">
          {spec.volume}
        </span>
      </div>

      <div className="p-4 space-y-4">
        <p className="text-xs text-gray-600 leading-relaxed">{spec.headline}</p>

        {/* Quick Lists */}
        <div>
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <ListChecks className="h-3.5 w-3.5" /> Lists to pull
          </p>
          <div className="space-y-1">
            {spec.quickLists.map((l) => (
              <div key={l.name} className="flex items-baseline gap-2 text-xs">
                <span className="font-semibold text-gray-800 shrink-0">{l.name}</span>
                <span className="text-gray-400">— {l.note}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Filters */}
        <div>
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <Filter className="h-3.5 w-3.5" /> Filters to set on every search
          </p>
          <ul className="space-y-1">
            {spec.filters.map((f) => (
              <li key={f} className="text-xs text-gray-600 flex gap-1.5">
                <span className="text-[#E8720C] shrink-0">•</span> {f}
              </li>
            ))}
          </ul>
        </div>

        {/* Export columns */}
        <div>
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <Download className="h-3.5 w-3.5" /> Include these columns in the export
          </p>
          <div className="flex flex-wrap gap-1">
            {EXPORT_COLUMNS.map((c) => (
              <code key={c} className="text-[11px] bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded">
                {c}
              </code>
            ))}
          </div>
          <p className="text-[11px] text-gray-400 mt-1.5">
            The Leads importer auto-maps these headers; any extra columns are ignored.
          </p>
        </div>

        {/* County data note */}
        {spec.countyNote && (
          <div className="bg-blue-50 border border-blue-100 rounded-lg p-2.5 text-xs text-blue-800 leading-relaxed">
            <span className="font-semibold">County data: </span>{spec.countyNote}
          </div>
        )}

        {/* Tip */}
        <div className="bg-amber-50 border border-amber-100 rounded-lg p-2.5 flex gap-2 text-xs text-amber-800 leading-relaxed">
          <Lightbulb className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <span>{spec.tip}</span>
        </div>

        {/* CTA */}
        <Link
          to="/leads?import=1"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold bg-[#E8720C] text-white hover:bg-[#d4660b] transition-colors"
        >
          Import the CSV <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}
