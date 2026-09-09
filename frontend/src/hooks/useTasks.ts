import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId } from 'react';
import { supabase } from '@/lib/supabase';
import type { Task } from '@/types';
import { toast } from 'sonner';
import { localDayBounds } from '@/lib/taskDates';
import { queryAll } from '@/lib/queryAll';

export type TaskWrite = Omit<Partial<Task>, 'due_date' | 'completed_at'> & {
  due_date?: string | null;
  completed_at?: string | null;
};

interface TasksFilter {
  status?: string;
  priority?: string;
  type?: string;
}

export function useTasks(filters: TasksFilter = {}) {
  const id = useId();
  const { status, priority, type } = filters;
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ['tasks', filters],
    queryFn: async () => {
      return queryAll<Task>((from, to) => {
        let query = supabase
          .from('tasks')
          .select('*, lead:leads(property_address), deal:deals(deal_name)')
          .order('due_date', { ascending: true, nullsFirst: false })
          .order('id', { ascending: true });

        if (status) query = query.eq('status', status);
        if (priority) query = query.eq('priority', priority);
        if (type) query = query.eq('type', type);

        return query.range(from, to);
      });
    },
    staleTime: 30000,
  });

  useEffect(() => {
    const channel = supabase
      .channel(`tasks-realtime-${id}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, () => {
        qc.invalidateQueries({ queryKey: ['tasks'] });
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [qc, id]);

  return query;
}

export function useTodayTasks() {
  const [today, tomorrow] = localDayBounds();

  return useQuery({
    queryKey: ['tasks', 'today', today.toISOString()],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('tasks')
        .select('*, lead:leads(property_address)')
        .gte('due_date', today.toISOString())
        .lt('due_date', tomorrow.toISOString())
        .neq('status', 'completed')
        .neq('status', 'cancelled')
        .order('priority', { ascending: true });
      if (error) throw error;
      const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
      return (data as Task[]).sort((a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3));
    },
    staleTime: 30000,
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (task: TaskWrite) => {
      const { data, error } = await supabase
        .from('tasks')
        .insert(task)
        .select()
        .single();
      if (error) throw error;
      return data as Task;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      toast.success('Task created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: TaskWrite }) => {
      const { data, error } = await supabase
        .from('tasks')
        .update(updates)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data as Task;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      toast.success('Task updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useCompleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase
        .from('tasks')
        .update({ status: 'completed', completed_at: new Date().toISOString() })
        .eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      toast.success('Task completed');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
