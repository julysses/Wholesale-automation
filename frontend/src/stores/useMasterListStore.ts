/**
 * useMasterListStore — keeps the Master List Builder's dropped files and merged
 * result alive across route changes. Component state is lost the moment you
 * navigate away; this module-level store survives SPA navigation so switching
 * to Leads and back doesn't wipe your work. (It does not survive a full page
 * reload — the merged list should be imported or downloaded to persist for good.)
 */

import { create } from 'zustand';
import type { CanonicalField, MergedRow } from '@/lib/masterList';

export interface SourceFile {
  id: string;
  label: string;
  fileName: string;
  headers: string[];
  rows: string[][];
  mapping: Partial<Record<CanonicalField, number>>;
  addressCombined: boolean;
  defaultCity: string;
  defaultState: string;
  status: 'mapping' | 'mapped' | 'error';
  mappedBy: 'claude' | 'heuristic' | null;
}

interface MasterListStore {
  files: SourceFile[];
  merged: MergedRow[] | null;
  imported: boolean;
  setFiles: (updater: SourceFile[] | ((prev: SourceFile[]) => SourceFile[])) => void;
  setMerged: (rows: MergedRow[] | null) => void;
  setImported: (v: boolean) => void;
  clearAll: () => void;
}

export const useMasterListStore = create<MasterListStore>((set) => ({
  files: [],
  merged: null,
  imported: false,
  setFiles: (updater) =>
    set((s) => ({ files: typeof updater === 'function' ? updater(s.files) : updater })),
  setMerged: (rows) => set({ merged: rows }),
  setImported: (v) => set({ imported: v }),
  clearAll: () => set({ files: [], merged: null, imported: false }),
}));
