import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn(), history: {count:0,data:[] as Record<string,unknown>[]} }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('@/components/dashboard/StrategyComparisonPanel', () => ({ StrategyComparisonPanel: () => null }));
const leads = Array.from({ length: 6 }, (_, i) => ({
  id: `lead-${i}`, property_address: `${i} Test St`, city: 'Dallas', state: 'TX', zip_code: '75201',
  qual: { classification: 'WARM', qualification_score: 65 },
}));
vi.mock('@tanstack/react-query', () => ({
  useQuery: (options: { queryKey: string[]; select?: (rows: typeof leads) => unknown }) => ({
    data: options.queryKey[0] === 'acquisition_leads' ? options.select?.(leads) ?? leads : options.queryKey[0] === 'deal_analyses' ? mocks.history : [],
    isLoading: false, refetch: vi.fn(),
  }),
}));
import { Acquisitions } from '@/pages/Acquisitions';

beforeEach(() => {
  mocks.api.mockReset();mocks.history={count:0,data:[]};
  vi.stubGlobal('confirm', vi.fn(() => true));
  vi.stubGlobal('alert', vi.fn());
});

it('retains partial WARM send results and locks the bulk button after an interrupted batch', async () => {
  mocks.api.mockResolvedValueOnce({ json: async () => ({ sent_count: 5, failed_count: 0, skipped_count: 0, dry_run_count: 0, log_failed_count: 1 }) });
  mocks.api.mockRejectedValueOnce(new Error('Network interrupted'));
  render(<Acquisitions />);
  fireEvent.click(screen.getByRole('button', { name: /WARM Leads/ }));
  const send = screen.getByRole('button', { name: 'Bulk SMS All Warm Leads' });
  fireEvent.click(send);
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('5 accepted by provider'));
  expect(screen.getByRole('alert')).toHaveTextContent('1 activity-log updates failed');
  expect(screen.getByRole('alert')).toHaveTextContent('1 recipients have unknown results');
  expect(send).toBeDisabled();
  expect(JSON.parse(mocks.api.mock.calls[0][1].body).lead_ids).toEqual(leads.slice(0, 5).map(lead => lead.id));
  expect(mocks.api).toHaveBeenCalledTimes(2);
});

it('shows rejected analyses, zero MAO and access to older history',()=>{
 mocks.history={count:101,data:[{id:'rejected-analysis',lead_id:null,is_viable:false,mao:0,analyzed_at:'2026-10-08T12:00:00Z',property_address:'Internal rejected estimate'}]};
 render(<Acquisitions />);fireEvent.click(screen.getByRole('button',{name:'Deal Analysis',exact:true}));
 expect(screen.getByText('Not viable under saved assumptions — review required')).toBeInTheDocument();
 expect(screen.getByText('$0')).toBeInTheDocument();expect(screen.getByText(/101 saved analyses · Page 1 of 3/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Next analyses'}));expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();
});
