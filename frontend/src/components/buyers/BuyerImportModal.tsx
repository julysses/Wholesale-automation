import { apiFetch } from '@/lib/api';
/**
 * BuyerImportModal — CSV upload for county records / PropStream lists.
 *
 * Accepts any CSV with flexible column names (see buyer_csv_parser.py).
 * Shows a preview of parsed rows before confirming the import.
 *
 * Sends to POST /api/buyers/import (multipart/form-data).
 */

import { useRef, useState } from 'react';
import Papa from 'papaparse';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Upload, FileText, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface BuyerImportModalProps {
  open: boolean;
  onClose: () => void;
  onImported?: () => void;
}

interface PreviewRow {
  grantee: string;
  property_address: string;
  purchase_price: string;
  purchase_date: string;
  cash_transaction: string;
  zip_code: string;
}

type ImportStep = 'upload' | 'preview' | 'importing' | 'done';

export function BuyerImportModal({ open, onClose, onImported }: BuyerImportModalProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<ImportStep>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [market, setMarket] = useState('');
  const [cashOnly, setCashOnly] = useState(false);
  const [entitiesOnly, setEntitiesOnly] = useState(false);
  const [logId, setLogId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const MARKET_OPTIONS = ['DFW', 'Houston', 'Austin', 'San Antonio', 'El Paso', 'Other'];

  const handleFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith('.csv')) {
      toast.error('Please upload a CSV file');
      return;
    }
    setFile(f);
    // Quick preview parse
    Papa.parse(f, {
      header: true,
      preview: 5,
      skipEmptyLines: true,
      complete: (results) => {
        const cols = results.meta.fields || [];
        const rows = results.data as Record<string, string>[];

        // Map to preview format — detect key columns by name similarity
        const find = (keys: string[]) =>
          cols.find((c) => keys.some((k) => c.toLowerCase().includes(k))) || '';

        const granteeCol   = find(['grantee', 'buyer', 'purchaser', 'owner']);
        const addrCol      = find(['address', 'property', 'situs', 'location']);
        const priceCol     = find(['price', 'amount', 'consideration', 'value']);
        const dateCol      = find(['date', 'recording', 'closing', 'transfer']);
        const cashCol      = find(['cash', 'financing', 'loan type']);
        const zipCol       = find(['zip', 'postal']);

        const mapped: PreviewRow[] = rows.map((r) => ({
          grantee:         r[granteeCol]   || '—',
          property_address: r[addrCol]     || '—',
          purchase_price:  r[priceCol]     || '—',
          purchase_date:   r[dateCol]      || '—',
          cash_transaction: r[cashCol]     || '—',
          zip_code:        r[zipCol]       || '—',
        }));

        setPreview(mapped);
        setTotalRows(0);  // Full count done server-side
        setStep('preview');
      },
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmit = async () => {
    if (!file) return;
    setStep('importing');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('market', market);
      form.append('cash_only', String(cashOnly));
      form.append('entities_only', String(entitiesOnly));

      const resp = await apiFetch('/api/buyers/import', {
        method: 'POST',
        body: form,
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setLogId(data.import_log_id);
      setStep('done');
      onImported?.();
    } catch (err) {
      toast.error(`Import failed: ${err}`);
      setStep('preview');
    }
  };

  const reset = () => {
    setStep('upload');
    setFile(null);
    setPreview([]);
    setTotalRows(0);
    setLogId(null);
  };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Import Buyer List" size="xl">
      <div className="p-6 space-y-5">

        {/* ── Step: Upload ─────────────────────────────────────────────── */}
        {step === 'upload' && (
          <div className="space-y-5">
            {/* Drop zone */}
            <div
              className={cn(
                'border-2 border-dashed rounded-xl p-10 flex flex-col items-center gap-3 cursor-pointer transition-colors',
                dragging ? 'border-[#E8720C] bg-orange-50' : 'border-gray-300 hover:border-[#1B3A5C]'
              )}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="h-10 w-10 text-gray-400" />
              <p className="font-medium text-gray-700">Drop CSV here or click to browse</p>
              <p className="text-xs text-gray-400">County deed records, PropStream Cash Buyer export, title company lists</p>
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }}
              />
            </div>

            {/* Options */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Market</label>
                <select
                  value={market}
                  onChange={(e) => setMarket(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1B3A5C]"
                >
                  <option value="">All Markets</option>
                  {MARKET_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div className="space-y-2 pt-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={cashOnly} onChange={(e) => setCashOnly(e.target.checked)} className="w-4 h-4 rounded border-gray-300" />
                  <span className="text-sm text-gray-700">Cash transactions only</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={entitiesOnly} onChange={(e) => setEntitiesOnly(e.target.checked)} className="w-4 h-4 rounded border-gray-300" />
                  <span className="text-sm text-gray-700">Entities (LLC/INC) only</span>
                </label>
              </div>
            </div>

            {/* Accepted formats note */}
            <div className="bg-blue-50 rounded-lg p-3 text-xs text-blue-700 space-y-1">
              <p className="font-semibold">Accepted column names (flexible):</p>
              <p>Grantee / Buyer / Owner • Sale Price / Deed Amount • Sale Date / Recording Date</p>
              <p>Cash Sale • Financing Type • APN / Parcel Number • Property Address • Zip Code</p>
            </div>
          </div>
        )}

        {/* ── Step: Preview ────────────────────────────────────────────── */}
        {step === 'preview' && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <FileText className="h-4 w-4" />
              <span className="font-medium">{file?.name}</span>
              <span className="text-gray-400">— showing first 5 rows</span>
            </div>

            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    {['Grantee/Buyer', 'Property Address', 'Purchase Price', 'Date', 'Cash?', 'Zip'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {preview.map((row, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-medium text-gray-900 max-w-40 truncate">{row.grantee}</td>
                      <td className="px-3 py-2 text-gray-600 max-w-40 truncate">{row.property_address}</td>
                      <td className="px-3 py-2 text-gray-600">{row.purchase_price}</td>
                      <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{row.purchase_date}</td>
                      <td className="px-3 py-2">{row.cash_transaction}</td>
                      <td className="px-3 py-2 text-gray-600">{row.zip_code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                The parser will group rows by buyer entity, compute IBIE scores,
                and deduplicate by APN. Existing buyers with matching phone/entity
                will be enriched rather than duplicated.
              </p>
            </div>

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => { setStep('upload'); setFile(null); }}>Back</Button>
              <Button onClick={handleSubmit}>
                <Upload className="h-4 w-4 mr-2" />
                Import {file?.name}
              </Button>
            </div>
          </div>
        )}

        {/* ── Step: Importing ──────────────────────────────────────────── */}
        {step === 'importing' && (
          <div className="flex flex-col items-center py-10 gap-4">
            <Loader2 className="h-12 w-12 text-[#E8720C] animate-spin" />
            <p className="font-semibold text-gray-700">Parsing and scoring buyers…</p>
            <p className="text-sm text-gray-400">
              Large files may take up to 30 seconds. You'll be notified when complete.
            </p>
          </div>
        )}

        {/* ── Step: Done ──────────────────────────────────────────────── */}
        {step === 'done' && (
          <div className="flex flex-col items-center py-10 gap-4">
            <CheckCircle2 className="h-12 w-12 text-green-500" />
            <p className="font-semibold text-gray-700">Import queued successfully!</p>
            <p className="text-sm text-gray-500">
              Buyers are being scored and saved in the background.
              {logId && <> Import log ID: <code className="text-xs bg-gray-100 px-1 rounded">{logId}</code></>}
            </p>
            <Button onClick={() => { reset(); onClose(); }}>Done</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
