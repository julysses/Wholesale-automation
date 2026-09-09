import { apiFetch } from '@/lib/api';
/**
 * MasterListBuilder
 *
 * Drop multiple lead lists (PropStream exports, county rolls, XLeads, buyer
 * lists — any CSV) and get back one deduped, downloadable master list.
 *
 * For each file, Claude reads the header row + a few sample rows and maps
 * them to the app's canonical lead fields — so wildly different column
 * names ("Situs Address" vs "Property Address" vs "Site Addr") all resolve
 * correctly without the user hand-mapping every file. The actual merge
 * (normalizing addresses, deduping, filling gaps, tallying how many lists
 * each address appeared on) runs instantly client-side.
 */

import { useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { parseSpreadsheet, isSupportedFile } from '@/lib/parseFile';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Upload, X, Sparkles, Layers, Download, ArrowRight,
  FileText, Loader2, CheckCircle2, AlertTriangle, Database,
} from 'lucide-react';
import { useMasterListStore, type SourceFile } from '@/stores/useMasterListStore';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';
import {
  CANONICAL_FIELDS, FIELD_LABELS, type CanonicalField, type MergedRow,
  mergeRowInto, toCSV, downloadCSV, heuristicMapColumns, parseCombinedAddress,
} from '@/lib/masterList';

interface ClaudePlan {
  mapping: Partial<Record<CanonicalField, number>>;
  addressCombined: boolean;
  defaultCity: string;
  defaultState: string;
}

async function mapColumnsWithClaude(headers: string[], samples: string[][]): Promise<ClaudePlan | null> {
  try {
    const res = await apiFetch('/api/ai/map-columns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ headers, samples }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.mapping) return null;
    return {
      mapping: data.mapping,
      addressCombined: !!data.address_combined,
      defaultCity: data.default_city || '',
      defaultState: data.default_state || '',
    };
  } catch {
    return null;
  }
}

export function MasterListBuilder() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Persisted across navigation so switching screens doesn't wipe the work
  const { files, merged, setFiles, setMerged, setImported, clearAll } = useMasterListStore();
  const [merging, setMerging] = useState(false);
  const [importing, setImporting] = useState(false);

  const addFiles = useCallback(async (fileList: FileList | File[]) => {
    const supported = Array.from(fileList).filter((f) => isSupportedFile(f.name));
    if (supported.length === 0) {
      toast.error('Drop .csv or Excel (.xlsx/.xls) files');
      return;
    }
    setMerged(null); // adding a new list invalidates any previous merge result

    for (const file of supported) {
      const id = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      let allRows: string[][];
      try {
        allRows = await parseSpreadsheet(file); // handles CSV + Excel uniformly
      } catch {
        toast.error(`Couldn't parse ${file.name}`);
        continue;
      }
      if (allRows.length < 2) {
        toast.error(`${file.name} has no data rows`);
        continue;
      }
      const headers = allRows[0];
      const rows = allRows.slice(1).filter((r) => r.some((c) => c && c.trim()));

      const placeholder: SourceFile = {
        id, label: file.name.replace(/\.(csv|xlsx|xls|xlsm)$/i, ''), fileName: file.name,
        headers, rows, mapping: {}, addressCombined: false, defaultCity: '',
        defaultState: '', status: 'mapping', mappedBy: null,
      };
      setFiles((prev) => [...prev, placeholder]);

      const samples = rows.slice(0, 3);
      const plan = await mapColumnsWithClaude(headers, samples);
      const usedClaude = !!plan && Object.keys(plan.mapping).length > 0;
      const mapping = usedClaude ? plan!.mapping : heuristicMapColumns(headers);

      setFiles((prev) => prev.map((f) => f.id === id
        ? {
            ...f, mapping,
            addressCombined: usedClaude ? plan!.addressCombined : false,
            defaultCity: usedClaude ? plan!.defaultCity : '',
            defaultState: usedClaude ? plan!.defaultState : '',
            mappedBy: usedClaude ? 'claude' : 'heuristic',
            status: mapping.property_address !== undefined ? 'mapped' : 'error',
          }
        : f));
    }
  }, []);

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
    setMerged(null);
  };

  const updateMapping = (id: string, field: CanonicalField, colIdx: string) => {
    setFiles((prev) => prev.map((f) => {
      if (f.id !== id) return f;
      const mapping = { ...f.mapping };
      if (colIdx === '') delete mapping[field];
      else mapping[field] = Number(colIdx);
      return { ...f, mapping, status: mapping.property_address !== undefined ? 'mapped' : 'error' };
    }));
    setMerged(null);
  };

  const updateLabel = (id: string, label: string) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, label } : f)));
  };

  const readyFiles = files.filter((f) => f.status === 'mapped');
  const totalInputRows = readyFiles.reduce((s, f) => s + f.rows.length, 0);

  const handleMerge = () => {
    if (readyFiles.length === 0) {
      toast.error('Map at least one list\'s Property Address column first');
      return;
    }
    setMerging(true);
    const acc = new Map<string, MergedRow>();
    for (const f of readyFiles) {
      for (const row of f.rows) {
        const raw: Record<string, string> = {};
        CANONICAL_FIELDS.forEach((field) => {
          const idx = f.mapping[field];
          if (idx !== undefined) raw[field] = row[idx] ?? '';
        });
        // Claude flagged this list's address as a combined string — split it
        // and fill any parts not already mapped separately.
        if (f.addressCombined && raw.property_address) {
          const p = parseCombinedAddress(raw.property_address);
          if (p.street) raw.property_address = p.street;
          if (!raw.city && p.city) raw.city = p.city;
          if (!raw.state && p.state) raw.state = p.state;
          if (!raw.zip_code && p.zip) raw.zip_code = p.zip;
        }
        // Backfill city/state from Claude's inferred defaults for single-county lists
        if (!raw.city && f.defaultCity) raw.city = f.defaultCity;
        if (!raw.state && f.defaultState) raw.state = f.defaultState;
        mergeRowInto(acc, raw, f.label);
      }
    }
    const rows = Array.from(acc.values()).sort((a, b) => b.stack_count - a.stack_count);
    setMerged(rows);
    setMerging(false);
    toast.success(`Merged into ${rows.length.toLocaleString()} unique properties`);
  };

  const handleDownload = () => {
    if (!merged) return;
    downloadCSV(`master-list-${new Date().toISOString().slice(0, 10)}.csv`, toCSV(merged));
  };

  const handleImportToLeads = async () => {
    if (!merged) return;
    setImporting(true);

    try {
      const rows = merged
        .filter((r) => r.property_address && r.city)
        .map((r) => ({
          ...CANONICAL_FIELDS.reduce<Record<string, string>>((acc, field) => {
            acc[field] = r[field] || '';
            return acc;
          }, {}),
          sources: r.sources,
          source: r.sources.join(' | ').slice(0, 250),
          stack_count: r.stack_count,
        }));

      const res = await apiFetch('/api/ai/import-master-list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows, score_with_claude: false }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Import failed');
      }

      const result = await res.json() as {
        imported: number;
        updated: number;
        skipped: number;
        scored: number;
        consolidated_rows: number;
      };
      const saved = result.imported + result.updated;

      setImported(true);
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['kpi'] });
      queryClient.invalidateQueries({ queryKey: ['workflow_progress'] });
      toast.success(
        `${saved.toLocaleString()} leads saved (${result.imported.toLocaleString()} new, `
        + `${result.updated.toLocaleString()} updated); Claude scoring queued`
      );
      useAutoScoreStore.getState().start();
      setTimeout(() => navigate('/leads'), 800);
      if (result.skipped > 0) toast.warning(`${result.skipped.toLocaleString()} rows skipped`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const stackBreakdown = merged ? {
    tripleplus: merged.filter((r) => r.stack_count >= 3).length,
    double: merged.filter((r) => r.stack_count === 2).length,
    single: merged.filter((r) => r.stack_count === 1).length,
  } : null;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Layers className="h-6 w-6 text-[#1B3A5C]" />
            Master List Builder
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Drop every list you pulled — PropStream, county rolls, skip-trace exports — and get
            back one deduped master list. Claude maps each file's columns (including all
            skip-trace phones and mailing address); addresses on multiple lists are flagged as a stack.
          </p>
        </div>
        {files.length > 0 && (
          <button
            onClick={() => { clearAll(); toast.success('Cleared — start fresh'); }}
            className="shrink-0 text-xs text-gray-400 hover:text-red-600 mt-1"
          >
            Start over
          </button>
        )}
      </div>

      {/* Drop zone */}
      <div
        className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-[#1B3A5C] transition-colors cursor-pointer bg-white"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }}
        onClick={() => document.getElementById('master-list-input')?.click()}
      >
        <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
        <p className="font-medium text-gray-700">Drop CSV or Excel files here or click to browse</p>
        <p className="text-xs text-gray-400 mt-1">Drop multiple files at once — CSV or Excel, any column layout, any source</p>
        <input
          id="master-list-input" type="file" accept=".csv,.xlsx,.xls,.xlsm" multiple className="hidden"
          onChange={(e) => { if (e.target.files?.length) addFiles(e.target.files); e.target.value = ''; }}
        />
      </div>

      {/* Source file cards */}
      {files.length > 0 && (
        <div className="space-y-3">
          {files.map((f) => (
            <div key={f.id} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-gray-400 shrink-0" />
                <Input
                  value={f.label}
                  onChange={(e) => updateLabel(f.id, e.target.value)}
                  className="max-w-xs"
                />
                <span className="text-xs text-gray-400 truncate">{f.fileName} · {f.rows.length.toLocaleString()} rows</span>

                <div className="ml-auto flex items-center gap-2 shrink-0">
                  {f.status === 'mapping' && (
                    <span className="flex items-center gap-1.5 text-xs text-gray-500">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Claude is reading columns…
                    </span>
                  )}
                  {f.status === 'mapped' && (
                    <span className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {f.mappedBy === 'claude' ? 'Mapped by Claude' : 'Mapped (auto-detect)'}
                    </span>
                  )}
                  {f.status === 'error' && (
                    <span className="flex items-center gap-1.5 text-xs text-red-600 font-medium">
                      <AlertTriangle className="h-3.5 w-3.5" /> No address column found
                    </span>
                  )}
                  <button onClick={() => removeFile(f.id)} className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Column mapping (editable) */}
              {f.status !== 'mapping' && (
                <div className="mt-3 pt-3 border-t border-gray-100 grid grid-cols-2 md:grid-cols-3 gap-2">
                  {CANONICAL_FIELDS.map((field) => (
                    <div key={field} className="flex items-center gap-1.5">
                      <span className="text-xs text-gray-500 w-28 shrink-0 truncate">{FIELD_LABELS[field]}</span>
                      <select
                        value={f.mapping[field] ?? ''}
                        onChange={(e) => updateMapping(f.id, field, e.target.value)}
                        className="flex-1 border border-gray-200 rounded px-1.5 py-1 text-xs min-w-0"
                      >
                        <option value="">— skip —</option>
                        {f.headers.map((h, i) => (
                          <option key={i} value={i}>{h || `Column ${i + 1}`}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Merge action */}
      {files.length > 0 && (
        <div className="flex items-center gap-3">
          <Button
            onClick={handleMerge}
            loading={merging}
            disabled={readyFiles.length === 0 || files.some((f) => f.status === 'mapping')}
            icon={<Sparkles className="h-4 w-4" />}
          >
            Merge {readyFiles.length > 0 ? `${readyFiles.length} List${readyFiles.length > 1 ? 's' : ''}` : ''}
          </Button>
          {totalInputRows > 0 && (
            <span className="text-xs text-gray-400">{totalInputRows.toLocaleString()} total rows across ready lists</span>
          )}
        </div>
      )}

      {/* Results */}
      {merged && stackBreakdown && (
        <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-5">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-blue-600" />
            <h2 className="font-semibold text-gray-900">Master List — {merged.length.toLocaleString()} unique properties</h2>
          </div>

          {/* Stack breakdown */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-emerald-700">{stackBreakdown.tripleplus.toLocaleString()}</p>
              <p className="text-xs text-emerald-600 mt-0.5">On 3+ lists (Tier 1 stack)</p>
            </div>
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-blue-700">{stackBreakdown.double.toLocaleString()}</p>
              <p className="text-xs text-blue-600 mt-0.5">On 2 lists (Tier 2 stack)</p>
            </div>
            <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-gray-600">{stackBreakdown.single.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">On 1 list only</p>
            </div>
          </div>

          <p className="text-xs text-gray-400">
            {totalInputRows.toLocaleString()} rows in → {merged.length.toLocaleString()} unique properties
            ({(totalInputRows - merged.length).toLocaleString()} duplicates merged)
          </p>

          {/* Preview table */}
          <div className="overflow-x-auto rounded-lg border border-gray-200 max-h-80 overflow-y-auto">
            <table className="text-xs w-full">
              <thead className="sticky top-0 bg-gray-50">
                <tr>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">Stack</th>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">Address</th>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">City</th>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">Owner</th>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">Phone</th>
                  <th className="px-2 py-1.5 text-left border-b border-gray-200">Sources</th>
                </tr>
              </thead>
              <tbody>
                {merged.slice(0, 100).map((r, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="px-2 py-1.5">
                      <span className={
                        r.stack_count >= 3 ? 'text-emerald-700 font-bold' :
                        r.stack_count === 2 ? 'text-blue-700 font-bold' : 'text-gray-400'
                      }>
                        {r.stack_count}×
                      </span>
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{r.property_address}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{r.city}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{r.owner_first_name} {r.owner_last_name}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{r.owner_phone_1}</td>
                    <td className="px-2 py-1.5 truncate max-w-40">{r.sources.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {merged.length > 100 && (
              <p className="text-center text-xs text-gray-400 py-2">
                Showing first 100 of {merged.length.toLocaleString()} — download for the full list
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleDownload} icon={<Download className="h-4 w-4" />}>
              Download Master List CSV
            </Button>
            <Button variant="outline" onClick={handleImportToLeads} loading={importing} icon={<ArrowRight className="h-4 w-4" />}>
              Import Directly to Leads
            </Button>
            <Link to="/leads" className="text-xs text-[#2E6DA4] hover:underline self-center ml-auto">
              Go to Leads →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
