import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLogActivity } from '@/hooks/useLeads';
import { useTasks, useUpdateTask } from '@/hooks/useTasks';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { localDateTimeInput } from '@/lib/taskDates';
import { formatDateTime } from '@/lib/utils';
import type { Lead, Task } from '@/types';

function FollowUpTask({ task, refresh }: { task: Task; refresh: () => void }) {
  const [due, setDue] = useState<string>();
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const updateTask = useUpdateTask();

  const save = async (resolve = false) => {
    const detail = note.trim();
    if (resolve && !detail) {
      setError('Enter the outcome before resolving this task.');
      return;
    }
    setError('');
    try {
      const now = new Date();
      const entry = `${formatDateTime(now.toISOString())} — ${resolve ? 'Outcome' : 'Next step'}\n${detail}`;
      await updateTask.mutateAsync({ id: task.id, expected: task, updates: {
        ...(due !== undefined && { due_date: due ? new Date(due).toISOString() : null }),
        ...(detail && { description: [task.description, entry].filter(Boolean).join('\n\n') }),
        ...(resolve && { status: 'completed', completed_at: now.toISOString() }),
      } });
      setDue(undefined);
      setNote('');
    } catch {
      setError('The task could not be saved. Refresh the task before trying again.');
      refresh();
    }
  };

  return <section aria-label={task.title} className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-4">
    <div>
      <h3 className="break-words font-semibold">{task.title}</h3>
      <p className="text-xs text-gray-600">{task.assigned_to ? 'Assigned follow-up' : 'Unassigned follow-up'} · {task.due_date ? `Due ${formatDateTime(task.due_date)}` : 'No due date'}</p>
    </div>
    {task.description && <details className="text-sm text-gray-700">
      <summary className="cursor-pointer">Task notes</summary>
      <p className="mt-2 whitespace-pre-wrap break-words">{task.description}</p>
    </details>}
    <Input label="Next follow-up date and time" type="datetime-local" value={due ?? localDateTimeInput(task.due_date)} onChange={event => setDue(event.target.value)} />
    <Textarea label="Next step or outcome" rows={2} value={note} onChange={event => setNote(event.target.value)} />
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <Button type="button" size="sm" loading={updateTask.isPending} disabled={due === undefined && !note.trim()} onClick={() => void save()}>Save next step</Button>
      <Button type="button" size="sm" variant="outline" disabled={updateTask.isPending} onClick={() => void save(true)}>Record outcome and close task</Button>
    </div>
  </section>;
}

export function LeadFollowUp({ lead, taskId, onReviewSms, onReviewCall }: {
  lead: Lead;
  taskId: string | null;
  onReviewSms: () => void;
  onReviewCall: () => void;
}) {
  const { data = [], isLoading, error, refetch } = useTasks({ leadId: lead.id, type: 'follow_up', openOnly: true });
  const tasks = taskId === null ? data : data.filter(task => task.id === taskId);
  const logActivity = useLogActivity();
  const [note, setNote] = useState('');
  const [logError, setLogError] = useState('');

  const logEmail = async (received: boolean) => {
    setLogError('');
    try {
      await logActivity.mutateAsync({ lead_id: lead.id, channel: 'email', direction: received ? 'inbound' : 'outbound',
        status: received ? 'answered' : 'sent', message: note.trim() || undefined });
      setNote('');
    } catch {
      setLogError('The email activity could not be confirmed. Check the activity timeline before trying again.');
    }
  };

  return <div className="space-y-4 text-gray-900">
    {taskId !== null && (
      <Link to="/tasks/follow-ups" className="inline-flex min-h-10 items-center text-sm font-medium text-blue-800 hover:underline">
        Back to My Follow-ups
      </Link>
    )}
    <section className="space-y-2 text-sm">
      {lead.dnc && <p className="font-medium text-red-700">Do not contact</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onReviewSms}>Review SMS consent</Button>
        <Button type="button" size="sm" variant="outline" onClick={onReviewCall}>Review AI-call consent</Button>
      </div>
    </section>
    {isLoading ? <p role="status">Loading follow-ups…</p> : error ? (
      <div role="alert"><p>Could not load follow-ups.</p><Button size="sm" variant="outline" onClick={() => void refetch()}>Retry</Button></div>
    ) : tasks.length ? tasks.map(task => <FollowUpTask key={task.id} task={task} refresh={() => void refetch()} />)
      : <p role="status" className="text-sm text-gray-600">
        {taskId === null ? 'No open follow-up tasks for this lead.' : 'This follow-up is no longer available in this lead’s open tasks.'}
      </p>}
    <section className="space-y-3 rounded-lg border border-gray-200 p-4">
      <h3 className="font-semibold">Log email activity</h3>
      <Textarea label="Email notes" rows={2} value={note} onChange={event => setNote(event.target.value)} />
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="outline" disabled={logActivity.isPending} onClick={() => void logEmail(false)}>Log manual email sent</Button>
        <Button type="button" size="sm" variant="outline" disabled={logActivity.isPending || !note.trim()} onClick={() => void logEmail(true)}>Log email reply</Button>
      </div>
      {logError && <p role="alert" className="text-sm text-red-700">{logError}</p>}
    </section>
  </div>;
}
