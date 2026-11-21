import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const query = vi.hoisted(() => ({
  select: vi.fn().mockReturnThis(),
  order: vi.fn().mockReturnThis(),
  range: vi.fn().mockReturnThis(),
  in: vi.fn().mockReturnThis(),
  or: vi.fn().mockReturnThis(),
  eq: vi.fn().mockReturnThis(),
}));

vi.mock('@/lib/supabase', () => ({ supabase: { from: vi.fn(() => query) } }));

import { useLeads } from '@/hooks/useLeads';
import { leadSourceLabel } from '@/lib/leadSources';

function renderLeads(source: string, search?: string, inbound?: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useLeads({ source, search, inbound }), {
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

  it('searches both parts of a full name and includes native inbound sources', async () => {
    const { result } = renderLeads('', 'Ana Seller', true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(query.or).toHaveBeenCalledWith('inbound_channel.not.is.null,source.in.(facebook_ad,facebook_lead_ad,web_form)');
    expect(query.or).toHaveBeenCalledWith(expect.stringContaining('and(owner_first_name.ilike."%Ana%",owner_last_name.ilike."%Seller%")'));
  });

  it('matches a formatted phone against stored numbers with or without formatting', async () => {
    const { result } = renderLeads('', '(214) 555-0101');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(query.or).toHaveBeenCalledWith(expect.stringContaining('owner_phone_1.ilike."%2%1%4%5%5%5%0%1%0%1%"'));
  });
});
