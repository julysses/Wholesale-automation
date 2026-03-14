import { useState } from 'react';
import { useTasks, useCreateTask, useUpdateTask, useCompleteTask } from '@/hooks/useTasks';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { Task } from '@/types';
import { formatDateTime, daysUntil, getPriorityClass } from '@/lib/utils';
import { cn } from '@/lib/utils';
import {
  Plus, CheckCircle, Circle, Clock, AlertCircle,
  Phone, Mail, Calendar, FileText, X
} from 'lucide-react';
import { toast } from 'sonner';

const TASK_TYPES = [
  { value: 'follow_up', label: 'Follow Up', icon: Phone },
  { value: 'appointment', label: 'Appointment', icon: Calendar },
  { value: 'contract', label: 'Contract', icon: FileText },
  { value: 'closing', label: 'Closing', icon: CheckCircle },
  { value: 'call', label: 'Call', icon: Phone },
  { value: 'email', label: 'Email', icon: Mail },
  { value: 'other', label: 'Other', icon: Circle },
];

const PRIORITY_OPTIONS = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

export function Tasks() {
  const [filters, setFilters] = useState({ status: 'pending', priority: '', type: '' });
  const [addOpen, setAddOpen] = useState(false);
  const [editTask, setEditTask] = useState<Task | null>(null);
  const [quickTitle, setQuickTitle] = useState('');
  const [quickDue, setQuickDue] = useState('');

  const { data: tasks = [], isLoading } = useTasks({
    status: filters.status || undefined,
    priority: filters.priority || undefined,
    type: filters.type || undefined,
  });
  const completeTask = useCompleteTask();
  const updateTask = useUpdateTask();
  const createTask = useCreateTask();

  const handleQuickAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickTitle.trim()) return;
    await createTask.mutateAsync({
      title: quickTitle,
      due_date: quickDue ? new Date(quickDue).toISOString() : undefined,
      priority: 'medium',
      status: 'pending',
    });
    setQuickTitle('');
    setQuickDue('');
  };

  // Separate tasks by time
  const today = new Date().toISOString().split('T')[0];
  const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];

  const overdueT = tasks.filter((t) => t.due_date && t.due_date < today && t.status !== 'completed');
  const todayT = tasks.filter((t) => t.due_date && t.due_date.startsWith(today));
  const upcomingT = tasks.filter((t) => !t.due_date || t.due_date > today);

  const TaskCard = ({ task }: { task: Task }) => {
    const TypeIcon = TASK_TYPES.find((t) => t.value === task.type)?.icon || Circle;
    const days = daysUntil(task.due_date);
    const isOverdue = days !== null && days < 0 && task.status !== 'completed';

    return (
      <div className={cn(
        'bg-white border border-gray-200 rounded-xl p-4 flex items-start gap-3 hover:shadow-sm transition-shadow',
        task.status === 'completed' && 'opacity-60',
        isOverdue && 'border-red-200 bg-red-50/30'
      )}>
        {/* Complete button */}
        <button
          onClick={() => task.status !== 'completed' && completeTask.mutate(task.id)}
          className={cn(
            'mt-0.5 shrink-0 transition-colors',
            task.status === 'completed' ? 'text-green-500' : 'text-gray-300 hover:text-green-500'
          )}
        >
          {task.status === 'completed'
            ? <CheckCircle className="h-5 w-5" />
            : <Circle className="h-5 w-5" />}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className={cn(
              'text-sm font-medium text-gray-900',
              task.status === 'completed' && 'line-through text-gray-400'
            )}>
              {task.title}
            </p>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className={cn('px-1.5 py-0.5 rounded text-xs font-medium', getPriorityClass(task.priority))}>
                {task.priority}
              </span>
            </div>
          </div>

          {task.description && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{task.description}</p>
          )}

          <div className="flex items-center gap-3 mt-2 flex-wrap">
            {/* Type */}
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <TypeIcon className="h-3 w-3" />
              <span className="capitalize">{task.type?.replace(/_/g, ' ') || 'task'}</span>
            </div>

            {/* Due date */}
            {task.due_date && (
              <div className={cn(
                'flex items-center gap-1 text-xs font-medium',
                isOverdue ? 'text-red-600' :
                days === 0 ? 'text-orange-500' :
                'text-gray-400'
              )}>
                <Clock className="h-3 w-3" />
                {isOverdue
                  ? `${Math.abs(days!)}d overdue`
                  : days === 0
                  ? 'Due today'
                  : formatDateTime(task.due_date)}
              </div>
            )}

            {/* Linked entity */}
            {task.lead && (
              <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                {task.lead.property_address}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => setEditTask(task)}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        </div>
      </div>
    );
  };

  const Section = ({ title, tasks: sectionTasks, emptyMsg, danger }: {
    title: string; tasks: Task[]; emptyMsg: string; danger?: boolean;
  }) => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 className={cn('text-sm font-semibold', danger ? 'text-red-600' : 'text-gray-700')}>
          {title}
        </h2>
        <span className={cn(
          'text-xs px-1.5 py-0.5 rounded-full font-medium',
          danger ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'
        )}>
          {sectionTasks.length}
        </span>
      </div>
      {sectionTasks.length === 0 ? (
        <p className="text-sm text-gray-400 pl-2">{emptyMsg}</p>
      ) : (
        sectionTasks.map((t) => <TaskCard key={t.id} task={t} />)
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tasks</h1>
          <p className="text-sm text-gray-500 mt-0.5">{tasks.length} tasks</p>
        </div>
        <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
          Add Task
        </Button>
      </div>

      {/* Quick add */}
      <form onSubmit={handleQuickAdd} className="bg-white border border-gray-200 rounded-xl p-4 flex gap-3">
        <input
          type="text"
          value={quickTitle}
          onChange={(e) => setQuickTitle(e.target.value)}
          placeholder="Quick add task..."
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1B3A5C]"
        />
        <input
          type="date"
          value={quickDue}
          onChange={(e) => setQuickDue(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1B3A5C]"
        />
        <Button type="submit" size="sm" loading={createTask.isPending}>Add</Button>
      </form>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          options={[{ value: '', label: 'All Status' }, ...STATUS_OPTIONS]}
          className="w-36"
        />
        <Select
          value={filters.priority}
          onChange={(e) => setFilters({ ...filters, priority: e.target.value })}
          options={[{ value: '', label: 'All Priority' }, ...PRIORITY_OPTIONS]}
          className="w-36"
        />
        <Select
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
          options={[{ value: '', label: 'All Types' }, ...TASK_TYPES.map((t) => ({ value: t.value, label: t.label }))]}
          className="w-36"
        />
      </div>

      {/* Task lists */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="space-y-6">
          {overdueT.length > 0 && (
            <Section title="Overdue" tasks={overdueT} emptyMsg="" danger />
          )}
          <Section title="Today" tasks={todayT} emptyMsg="Nothing due today" />
        </div>
        <div>
          <Section title="Upcoming" tasks={upcomingT} emptyMsg="No upcoming tasks" />
        </div>
      </div>

      {/* Full Add/Edit Modal */}
      <TaskFormModal open={addOpen || !!editTask} task={editTask} onClose={() => { setAddOpen(false); setEditTask(null); }} />
    </div>
  );
}

function TaskFormModal({ open, task, onClose }: { open: boolean; task: Task | null; onClose: () => void }) {
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const isEdit = !!task;

  const [form, setForm] = useState({
    title: task?.title || '',
    description: task?.description || '',
    priority: task?.priority || 'medium',
    type: task?.type || 'follow_up',
    status: task?.status || 'pending',
    due_date: task?.due_date ? task.due_date.slice(0, 16) : '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return toast.error('Title required');
    const payload = {
      ...form,
      due_date: form.due_date ? new Date(form.due_date).toISOString() : undefined,
    };
    if (isEdit && task) {
      await updateTask.mutateAsync({ id: task.id, updates: payload });
    } else {
      await createTask.mutateAsync(payload);
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? 'Edit Task' : 'New Task'} size="md">
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        <Input label="Title *" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <Textarea label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} />
        <div className="grid grid-cols-2 gap-4">
          <Select label="Priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
            options={[{ value: 'high', label: 'High' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }]} />
          <Select label="Type" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
            options={TASK_TYPES.map((t) => ({ value: t.value, label: t.label }))} />
          <Input label="Due Date & Time" type="datetime-local" value={form.due_date}
            onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          <Select label="Status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
            options={[{ value: 'pending', label: 'Pending' }, { value: 'in_progress', label: 'In Progress' }, { value: 'completed', label: 'Completed' }]} />
        </div>
        <div className="flex justify-end gap-3">
          <Button variant="outline" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={createTask.isPending || updateTask.isPending}>
            {isEdit ? 'Save' : 'Create Task'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
