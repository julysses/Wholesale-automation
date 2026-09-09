import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { Task } from '@/types';
import { groupTasks, localDateTimeInput, localDayBounds } from '@/lib/taskDates';

const mocks = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), refetch: vi.fn(), error: null as Error | null, tasks: [] as Task[] }));
vi.mock('@/hooks/useTasks', () => ({
  useTasks: (filters: { status?: string }) => ({ data: mocks.tasks.filter((task) => !filters.status || task.status === filters.status), isLoading: false, error: mocks.error, refetch: mocks.refetch }),
  useCreateTask: () => ({ mutateAsync: mocks.create, isPending: false }),
  useUpdateTask: () => ({ mutateAsync: mocks.update, isPending: false }),
  useCompleteTask: () => ({ mutate: vi.fn(), isPending: false }),
}));
import { Tasks } from '@/pages/Tasks';

const due = new Date(2026, 8, 9, 14, 30).toISOString();
const task = (id: string, due_date?: string, status = 'pending'): Task => ({ id, title: id, due_date, status, priority: 'high', created_at: '2026-01-01', description: `${id} description`, type: 'call' });

beforeEach(() => {
  vi.clearAllMocks();
  mocks.error = null;
  mocks.tasks = [task('Call seller', due), task('Send contract', due)];
  mocks.create.mockResolvedValue({});
  mocks.update.mockResolvedValue({});
});

it('assigns each task to exactly one local calendar bucket and keeps completed history', () => {
  const now = new Date(2026, 8, 9, 23, 30);
  const rows = [
    task('overdue', new Date(2026, 8, 8, 23, 59).toISOString()),
    task('today', new Date(2026, 8, 9, 23, 59).toISOString()),
    task('upcoming', new Date(2026, 8, 10, 0, 0).toISOString()),
    task('undated'), task('finished', new Date(2026, 8, 1).toISOString(), 'completed'),
    task('cancelled', undefined, 'cancelled'),
  ];
  const groups = groupTasks(rows, now);
  expect(groups.overdue.map((row) => row.id)).toEqual(['overdue']);
  expect(groups.today.map((row) => row.id)).toEqual(['today']);
  expect(groups.upcoming.map((row) => row.id)).toEqual(['upcoming', 'undated']);
  expect(groups.finished.map((row) => row.id)).toEqual(['finished', 'cancelled']);
  expect(Object.values(groups).flat()).toHaveLength(rows.length);
  const [start, end] = localDayBounds(now);
  expect(start.getHours()).toBe(0);
  expect(end.getDate()).toBe(10);
});

it('loads selected task fields and preserves its original timestamp on unchanged save', async () => {
  render(<Tasks />);
  fireEvent.click(screen.getByRole('button', { name: 'Edit Call seller' }));
  expect(screen.getByLabelText('Title *')).toHaveValue('Call seller');
  expect(screen.getByLabelText('Due Date & Time')).toHaveValue('2026-09-09T14:30');
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(expect.objectContaining({ id: 'Call seller', updates: expect.objectContaining({ due_date: due, description: 'Call seller description' }) })));
  await waitFor(() => expect(screen.queryByLabelText('Title *')).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'Edit Send contract' }));
  expect(screen.getByLabelText('Title *')).toHaveValue('Send contract');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Add Task' }));
  expect(screen.getByLabelText('Title *')).toHaveValue('');
});

it('sends null when clearing a task date and preserves a failed edit for retry', async () => {
  mocks.update.mockRejectedValueOnce(new Error('Write denied'));
  render(<Tasks />);
  fireEvent.click(screen.getByRole('button', { name: 'Edit Call seller' }));
  fireEvent.change(screen.getByLabelText('Due Date & Time'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalled());
  expect(mocks.update.mock.calls[0][0].updates.due_date).toBeNull();
  expect(screen.getByLabelText('Title *')).toHaveValue('Call seller');
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }));
  await waitFor(() => expect(screen.queryByLabelText('Title *')).not.toBeInTheDocument());
});

it('keeps completed tasks visible with the completed filter', () => {
  mocks.tasks = [task('Old completed task', '2020-01-01T12:00:00Z', 'completed')];
  render(<Tasks />);
  fireEvent.change(screen.getByLabelText('Filter task status'), { target: { value: 'completed' } });
  expect(screen.getByText('Old completed task')).toBeInTheDocument();
  expect(screen.getByText('Completed / Cancelled')).toBeInTheDocument();
});

it('stores quick-add calendar dates in the local timezone', async () => {
  render(<Tasks />);
  fireEvent.change(screen.getByLabelText('Quick task title'), { target: { value: 'Follow up' } });
  fireEvent.change(screen.getByLabelText('Quick task due date'), { target: { value: '2026-09-09' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add', exact: true }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalled());
  expect(mocks.create.mock.calls[0][0].due_date).toBe(new Date(2026, 8, 9).toISOString());
  expect(localDateTimeInput(mocks.create.mock.calls[0][0].due_date)).toBe('2026-09-09T00:00');
});

it('shows task query errors and offers retry', () => {
  mocks.error = new Error('Offline');
  render(<Tasks />);
  expect(screen.getByRole('alert')).toHaveTextContent('Unable to load tasks: Offline');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(mocks.refetch).toHaveBeenCalled();
});
