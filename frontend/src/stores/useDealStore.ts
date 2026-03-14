import { create } from 'zustand';
import type { Deal } from '@/types';

interface DealStore {
  deals: Deal[];
  setDeals: (deals: Deal[]) => void;
  moveDealStage: (id: string, stage: string) => void;
}

export const useDealStore = create<DealStore>((set) => ({
  deals: [],
  setDeals: (deals) => set({ deals }),
  moveDealStage: (id, stage) =>
    set((s) => ({
      deals: s.deals.map((d) => (d.id === id ? { ...d, stage } : d)),
    })),
}));
