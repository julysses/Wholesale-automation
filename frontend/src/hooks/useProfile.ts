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
  error: string | null;
  isAdmin: boolean;
  isApproved: boolean;
  isPending: boolean;
  refetch: () => void;
}

export function useProfile(): UseProfileResult {
  // undefined means authentication is still initializing; null means signed out.
  const [userId, setUserId] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let active = true;
    let receivedAuthEvent = false;
    void supabase.auth.getSession().then(({ data }) => {
      if (active && !receivedAuthEvent) setUserId(data.session?.user.id ?? null);
    }).catch(() => {
      if (active && !receivedAuthEvent) setUserId(null);
    });
    // Keep this callback synchronous: querying Supabase here can deadlock auth.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      receivedAuthEvent = true;
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
    loading: userId === undefined || (!!userId && query.isPending),
    error: query.error?.message ?? null,
    isAdmin: profile?.role === 'admin' && profile.status === 'approved',
    isApproved: profile?.status === 'approved',
    isPending: profile?.status === 'pending',
    refetch: () => { void query.refetch(); },
  };
}
