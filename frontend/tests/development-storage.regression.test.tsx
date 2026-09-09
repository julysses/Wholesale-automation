import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ save: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: {
  from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: null, error: null }) }) }), upsert: mocks.save }),
  auth: { getUser: async () => ({ data: { user: { id: 'operator-test' } } }) },
} }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { DevelopmentCommandCenter } from '@/pages/DevelopmentCommandCenter';

it('keeps edits and permits cloud saves when browser storage is full', async () => {
  localStorage.clear();
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Storage quota exceeded'); });
  mocks.save.mockResolvedValue({ error: null });
  render(<DevelopmentCommandCenter userId="operator-test" />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Add', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Browser storage is unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1));
  expect(mocks.save.mock.calls[0][0].workspace.projects).toHaveLength(2);
  expect(await screen.findByRole('button', { name: 'Saved' })).toBeEnabled();
});
