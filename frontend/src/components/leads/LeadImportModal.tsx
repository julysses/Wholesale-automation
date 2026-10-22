import { useState, useCallback } from 'react';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import Papa from 'papaparse';
import { Upload, CheckCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQueryClient } from '@tanstack/react-query';

interface LeadImportModalProps {
  open: boolean;
  onClose: () => void;
}

const FIELD_MAP: Record<string, string> = {
  'address': 'property_address',
  'property_address': 'property_address',
  'city': 'city',
  'state': 'state',
  'zip': 'zip_code',
  'zip_code': 'zip_code',
  'type': 'property_type',
  'property_type': 'property_type',
  'beds': 'bedrooms',
  'bedrooms': 'bedrooms',
  'baths': 'bathrooms',
  'bathrooms': 'bathrooms',
  'sqft': 'sqft',
  'year_built': 'year_built',
  'first_name': 'owner_first_name',
  'owner_first_name': 'owner_first_name',
  'last_name': 'owner_last_name',
  'owner_last_name': 'owner_last_name',
  'phone': 'owner_phone_1',
  'owner_phone_1': 'owner_phone_1',
  'phone_2': 'owner_phone_2',
  'phone_3': 'owner_phone_3',
  'email': 'owner_email',
  'owner_email': 'owner_email',
  'mailing_address': 'owner_mailing_address',
  'source': 'source',
  'motivation': 'motivation_tag',
  'motivation_tag': 'motivation_tag',
  'status': 'status',
  'asking_price': 'asking_price',
  'notes': 'seller_notes',
};

export function LeadImportModal({ open, onClose }: LeadImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvData, setCsvData] = useState<Record<string, string>[]>([]);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; updated: number; skipped: number; errors: number; message?: string } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const qc = useQueryClient();

  const handleFile = (f: File) => {
    setFile(f);
    setResult(null);
    Papa.parse(f, {
      header: true,
      skipEmptyLines: true,
      preview: 5,
      complete: (results) => {
        const headers = results.meta.fields || [];
        setCsvHeaders(headers);
        setCsvData(results.data as Record<string, string>[]);
        // Auto-map columns
        const autoMap: Record<string, string> = {};
        headers.forEach((h) => {
          const key = h.toLowerCase().replace(/\s+/g, '_');
          if (FIELD_MAP[key]) autoMap[h] = FIELD_MAP[key];
        });
        setColumnMapping(autoMap);
      },
    });
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.endsWith('.csv')) handleFile(f);
    else toast.error('Please drop a CSV file');
  }, []);

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);

    let imported = 0, updated = 0, skipped = 0;
    try {
      const rows = await new Promise<Record<string, string>[]>((resolve, reject) => {
        Papa.parse(file, {
          header: true, skipEmptyLines: true,
          complete: (parsed) => parsed.errors.length
            ? reject(new Error('The CSV could not be parsed. Review its columns and quoting.'))
            : resolve(parsed.data as Record<string, string>[]),
          error: reject,
        });
      });
      const records = rows.map((row) => {
        const record: Record<string, unknown> = { state: 'TX' };
        Object.entries(columnMapping).forEach(([column, field]) => {
          const value = row[column]?.trim();
          if (field && value) record[field] = value;
        });
        return record;
      }).filter(row => row.property_address && row.city);
      skipped = rows.length - records.length;
      if (!records.length) throw new Error('No rows contain both a property address and a verified city.');
      const response = await apiFetch('/api/ai/import-master-list', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows: records, engine: 'rules', score_with_claude: true,
          list_name: file.name.replace(/\.[^.]+$/, '').slice(0, 120), filename: file.name }),
      });
      const saved = await response.json();
      if (saved.status !== 'ok' || !Number.isInteger(saved.imported) || saved.imported < 0
          || !Number.isInteger(saved.updated) || saved.updated < 0) {
        throw new Error('The server did not confirm the import outcome.');
      }
      imported = saved.imported; updated = saved.updated; skipped += saved.skipped || 0;
      setResult({ imported, updated, skipped, errors: 0 });
      toast.success(`Imported ${imported} leads; ${updated} existing leads reconciled`);
    } catch (error) {
      setResult({ imported, updated, skipped, errors: 0,
        message: error instanceof Error ? error.message : 'Import outcome unconfirmed.' });
    } finally {
      setImporting(false);
      await Promise.all([qc.invalidateQueries({ queryKey: ['leads'] }),
        qc.invalidateQueries({ queryKey: ['lead-lists'] })]);
    }
  };

  const dbFields = [...new Set(Object.values(FIELD_MAP))].sort();

  return (
    <Modal open={open} onClose={onClose} title="Import Leads from CSV" size="xl">
      <div className="p-6 space-y-6">
        {/* Drop zone */}
        {!file && (
          <div
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            className={cn(
              'border-2 border-dashed rounded-lg p-10 text-center transition-colors',
              isDragOver ? 'border-[#1B3A5C] bg-blue-50' : 'border-gray-300 hover:border-gray-400'
            )}
          >
            <Upload className="h-10 w-10 mx-auto text-gray-400 mb-3" />
            <p className="text-sm font-medium text-gray-700">Drag & drop a CSV file here</p>
            <p className="text-xs text-gray-400 mt-1">or</p>
            <label className="mt-3 inline-block cursor-pointer">
              <span className="px-4 py-2 text-sm font-medium text-white bg-[#1B3A5C] rounded-lg hover:bg-[#142c47]">
                Browse File
              </span>
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
            </label>
          </div>
        )}

        {/* File loaded */}
        {file && !result && (
          <>
            <div className="flex items-center gap-2 text-sm text-gray-700 bg-blue-50 border border-blue-200 rounded-lg p-3">
              <CheckCircle className="h-4 w-4 text-blue-600 shrink-0" />
              <span><strong>{file.name}</strong> loaded — {csvData.length} preview rows</span>
              <button onClick={() => setFile(null)} className="ml-auto text-xs text-gray-400 hover:text-gray-600">
                Change
              </button>
            </div>

            {/* Column mapping */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Column Mapping</h4>
              <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto pr-1">
                {csvHeaders.map((header) => (
                  <div key={header} className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 w-28 truncate font-mono bg-gray-100 px-2 py-1 rounded" title={header}>
                      {header}
                    </span>
                    <span className="text-gray-400">→</span>
                    <select
                      value={columnMapping[header] || ''}
                      onChange={(e) => setColumnMapping((m) => ({ ...m, [header]: e.target.value }))}
                      className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:border-[#1B3A5C]"
                    >
                      <option value="">Skip</option>
                      {dbFields.map((f) => (
                        <option key={f} value={f}>{f}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* Preview */}
            {csvData.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Preview (first 5 rows)</h4>
                <div className="overflow-x-auto rounded-lg border border-gray-200">
                  <table className="text-xs min-w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        {csvHeaders.slice(0, 6).map((h) => (
                          <th key={h} className="px-3 py-2 text-left text-gray-500 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {csvData.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-t border-gray-200">
                          {csvHeaders.slice(0, 6).map((h) => (
                            <td key={h} className="px-3 py-1.5 text-gray-700 max-w-32 truncate">{row[h]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button onClick={handleImport} loading={importing}>
                {importing ? 'Importing...' : 'Import Leads'}
              </Button>
            </div>
          </>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            {result.updated > 0 && <p>{result.updated} existing leads reconciled; no duplicate created for these properties.</p>}
            {result.message && <p role="alert">{result.message} Import stopped. Review saved leads before retrying.</p>}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-green-600">{result.imported}</p>
                <p className="text-xs text-green-600 mt-1">Imported</p>
              </div>
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-yellow-600">{result.skipped}</p>
                <p className="text-xs text-yellow-600 mt-1">Skipped</p>
              </div>
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-red-600">{result.errors}</p>
                <p className="text-xs text-red-600 mt-1">Errors</p>
              </div>
            </div>
            <Button variant="outline" onClick={onClose} className="w-full">Close</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
