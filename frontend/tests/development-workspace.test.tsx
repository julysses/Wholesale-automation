import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { createWorkspace, workspaceStorageKey } from '../src/lib/developmentEngine';
import { DevelopmentCommandCenter } from '../src/pages/DevelopmentCommandCenter';

const mocks = vi.hoisted(() => ({ load: vi.fn(), user: vi.fn(), save: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: {
  from: () => ({ select: () => ({ eq: () => ({ maybeSingle: mocks.load }) }), upsert: mocks.save }),
  auth: { getUser: mocks.user },
} }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
beforeEach(() => {
  localStorage.clear(); mocks.load.mockReset(); mocks.save.mockReset();
  mocks.load.mockResolvedValue({ data: null, error: null });
  mocks.user.mockResolvedValue({ data: { user: { id: 'operator-b' } } });
  mocks.save.mockResolvedValue({ error: null });
});

it('never loads or saves the previous operator draft into a new account', async () => {
  const old = createWorkspace(); old.projects[0].name = 'Private operator A';
  localStorage.setItem(workspaceStorageKey('operator-a'), JSON.stringify(old));
  localStorage.setItem('hilltop-development-workspace-v1', JSON.stringify(old));
  const view = render(<DevelopmentCommandCenter key="operator-a" userId="operator-a" />);
  await act(async () => {});
  expect(screen.getAllByText('Private operator A').length).toBeGreaterThan(0);
  view.rerender(<DevelopmentCommandCenter key="operator-b" userId="operator-b" />);
  await act(async () => {});
  expect(screen.queryByText('Private operator A')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Saved' }));
  await act(async () => {});
  expect(mocks.save.mock.calls[0][0].user_id).toBe('operator-b');
  expect(mocks.save.mock.calls[0][0].workspace.projects[0].name).not.toBe('Private operator A');
});

it('recovers from malformed local data without rendering a broken workspace', async () => {
  localStorage.setItem(workspaceStorageKey('operator-b'), '{"schema":1,"projects":[{}]}');
  render(<DevelopmentCommandCenter userId="operator-b" />);
  await act(async () => {});
  expect(screen.getByText('Development Command Center')).toBeInTheDocument();
});
