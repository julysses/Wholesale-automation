/**
 * useProfile — fetches the current user's profile (role, status, name).
 * Provides helpers: isAdmin, isApproved, isPending.
 */
import { useEffect, useState } from 'react';
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
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch = async () => {
    setLoading(true);
    const { data } = await supabase.from('my_profile').select('*').single();
    setProfile(data ?? null);
    setLoading(false);
  };

  useEffect(() => {
    fetch();
    // Re-fetch when auth state changes (e.g. after approval toast arrives)
    const { data: { subscription } } = supabase.auth.onAuthStateChange(() => fetch());
    return () => subscription.unsubscribe();
  }, []);

  return {
    profile,
    loading,
    isAdmin:    profile?.role === 'admin',
    isApproved: profile?.status === 'approved',
    isPending:  profile?.status === 'pending',
    refetch:    fetch,
  };
}
