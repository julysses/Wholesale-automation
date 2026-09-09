import type { Task } from '@/types';

export function localDateString(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function localDateTimeInput(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${localDateString(date)}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

export function localDayBounds(now = new Date()): [Date, Date] {
  return [
    new Date(now.getFullYear(), now.getMonth(), now.getDate()),
    new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1),
  ];
}

export function groupTasks(tasks: Task[], now = new Date()) {
  const [today, tomorrow] = localDayBounds(now);
  const groups: { overdue: Task[]; today: Task[]; upcoming: Task[]; finished: Task[] } = {
    overdue: [], today: [], upcoming: [], finished: [],
  };
  for (const task of tasks) {
    if (task.status === 'completed' || task.status === 'cancelled') {
      groups.finished.push(task);
      continue;
    }
    const due = task.due_date ? new Date(task.due_date).getTime() : NaN;
    if (due < today.getTime()) groups.overdue.push(task);
    else if (due < tomorrow.getTime()) groups.today.push(task);
    else groups.upcoming.push(task);
  }
  return groups;
}
