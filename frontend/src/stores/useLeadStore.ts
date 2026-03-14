import { create } from 'zustand';
import type { Lead } from '@/types';

interface LeadStore {
  selectedLead: Lead | null;
  setSelectedLead: (lead: Lead | null) => void;
  filters: {
    status: string;
    source: string;
    search: string;
    minScore: number;
    maxScore: number;
  };
  setFilters: (filters: Partial<LeadStore['filters']>) => void;
}

export const useLeadStore = create<LeadStore>((set) => ({
  selectedLead: null,
  setSelectedLead: (lead) => set({ selectedLead: lead }),
  filters: {
    status: '',
    source: '',
    search: '',
    minScore: 0,
    maxScore: 15,
  },
  setFilters: (filters) =>
    set((s) => ({ filters: { ...s.filters, ...filters } })),
}));
