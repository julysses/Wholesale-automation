import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const query = vi.hoisted(() => ({
  select: vi.fn().mockReturnThis(),
  order: vi.fn().mockReturnThis(),
  range: vi.fn().mockReturnThis(),
  in: vi.fn().mockReturnThis(),
  eq: vi.fn().mockReturnThis(),
}));

vi.mock('@/lib/supabase', () => ({ supabase: { from: vi.fn(() => query) } }));

import { useLeads } from '@/hooks/useLeads';
import { leadSourceLabel } from '@/lib/leadSources';

function renderLeads(source: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useLeads({ source }), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe('lead sources', () => {
  it('uses both Facebook source values in the same server-side filter', async () => {
    const { result } = renderLeads('facebook_ad');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(query.in).toHaveBeenCalledWith('source', ['facebook_ad', 'facebook_lead_ad']);
    expect(leadSourceLabel('facebook_lead_ad')).toBe('Facebook Ad');
    expect(leadSourceLabel('facebook_ad')).toBe('Facebook Ad');
  });

  it('keeps exact matches for other sources', async () => {
    const { result } = renderLeads('referral');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(query.eq).toHaveBeenCalledWith('source', 'referral');
  });
});
