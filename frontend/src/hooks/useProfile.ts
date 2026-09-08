/**
 * useProfile — fetches the current user's profile (role, status, name).
 * Provides helpers: isAdmin, isApproved, isPending.
 */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';

export interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  role: 'admin' | 'user';
  status: 'pending' | 'approved' | 'denied' | 'suspended';
  avatar_url: string | null;
  created_at: string;
  approved_at: string | null;
}

interface UseProfileResult {
  profile: UserProfile | null;
  loading: boolean;
  isAdmin: boolean;
  isApproved: boolean;
  isPending: boolean;
  refetch: () => void;
}

export function useProfile(): UseProfileResult {
  const [userId, setUserId] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (active) setUserId(data.session?.user.id ?? null);
    });
    // Keep this callback synchronous: querying Supabase here can deadlock auth.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUserId(session?.user.id ?? null);
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);
  const query = useQuery({
    queryKey: ['profile', userId],
    enabled: !!userId,
    queryFn: async () => {
      const { data, error } = await supabase.from('my_profile').select('*').single();
      if (error) throw error;
      return data as UserProfile;
    },
  });
  const profile = query.data ?? null;
  return {
    profile,
    loading: query.isLoading,
    isAdmin: profile?.role === 'admin' && profile.status === 'approved',
    isApproved: profile?.status === 'approved',
    isPending: profile?.status === 'pending',
    refetch: () => { void query.refetch(); },
  };
}
