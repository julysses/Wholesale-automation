import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { createWorkspace, parseWorkspace, workspaceStorageKey } from '@/lib/developmentEngine';

const mocks = vi.hoisted(() => ({ save: vi.fn(), user: vi.fn(), error: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: {
  from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: null, error: null }) }) }), upsert: mocks.save }),
  auth: { getUser: mocks.user },
} }));
vi.mock('sonner', () => ({ toast: { error: mocks.error, success: mocks.success } }));
import { DevelopmentCommandCenter } from '@/pages/DevelopmentCommandCenter';

const userId = 'validation-operator';
const storageKey = workspaceStorageKey(userId);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  const workspace = createWorkspace();
  workspace.projects[0].name = 'Keep this project';
  localStorage.setItem(storageKey, JSON.stringify(workspace));
  mocks.save.mockResolvedValue({ error: null });
  mocks.user.mockResolvedValue({ data: { user: { id: userId } } });
});

it('keeps invalid square footage and fractional units editable without replacing the last valid copy', async () => {
  const view = render(<DevelopmentCommandCenter userId={userId} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Spec Build' }));
  fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Operator work to retain' } });
  const lastValid = localStorage.getItem(storageKey);
  fireEvent.change(screen.getByLabelText('Finished SF'), { target: { value: '0' } });
  fireEvent.change(screen.getByLabelText('Units'), { target: { value: '1.5' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Finished SF must be greater than zero');
  expect(screen.getByLabelText('Finished SF')).toHaveValue(0);
  expect(screen.getByLabelText('Units')).toHaveValue(1.5);
  expect(localStorage.getItem(storageKey)).toBe(lastValid);
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(mocks.user).not.toHaveBeenCalled();
  expect(mocks.save).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Finished SF'), { target: { value: '3100' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Units must be a whole number of at least one');
  expect(localStorage.getItem(storageKey)).toBe(lastValid);
  fireEvent.change(screen.getByLabelText('Units'), { target: { value: '2' } });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledOnce());
  const saved = parseWorkspace(mocks.save.mock.calls[0][0].workspace);
  expect(saved.projects[0]).toMatchObject({ name: 'Operator work to retain', sf: 3100, units: 2 });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Saved' })).toBeEnabled());
  view.unmount();
  render(<DevelopmentCommandCenter userId={userId} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Spec Build' }));
  expect(screen.getByLabelText('Project name')).toHaveValue('Operator work to retain');
  expect(screen.getByLabelText('Finished SF')).toHaveValue(3100);
  expect(screen.getByLabelText('Units')).toHaveValue(2);
});

it('reloads the last valid project after invalid edits without replacing it with defaults', async () => {
  const view = render(<DevelopmentCommandCenter userId={userId} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Spec Build' }));
  fireEvent.change(screen.getByLabelText('Finished SF'), { target: { value: '0' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  view.unmount();
  render(<DevelopmentCommandCenter userId={userId} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Spec Build' }));
  expect(screen.getByLabelText('Project name')).toHaveValue('Keep this project');
  expect(screen.getByLabelText('Finished SF')).toHaveValue(2800);
});

it('does not save cash timing values that the workspace loader would reject', async () => {
  render(<DevelopmentCommandCenter userId={userId} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Capital', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Cash item' }));
  const lastValid = localStorage.getItem(storageKey);
  fireEvent.change(screen.getByLabelText('Cash item week'), { target: { value: '14' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Week must be a whole number from 1 through 13');
  expect(mocks.save).not.toHaveBeenCalled();
  expect(localStorage.getItem(storageKey)).toBe(lastValid);
  fireEvent.change(screen.getByLabelText('Cash item week'), { target: { value: '13' } });
  fireEvent.change(screen.getByLabelText('Cash item amount'), { target: { value: '-100' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Amount must be a finite, nonnegative number');
  fireEvent.change(screen.getByLabelText('Cash item amount'), { target: { value: '100' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledOnce());
  expect(parseWorkspace(mocks.save.mock.calls[0][0].workspace).cash[0]).toMatchObject({ week: 13, amount: 100 });
});
