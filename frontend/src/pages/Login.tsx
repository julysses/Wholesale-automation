import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Building2, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { Toaster } from 'sonner';

function getLoginErrorMessage(message: string): string {
  const normalized = message.toLowerCase();
  const isNetworkFailure =
    normalized.includes('load failed') ||
    normalized.includes('failed to fetch') ||
    normalized.includes('networkerror') ||
    normalized.includes('fetch failed');

  if (!isNetworkFailure) return message;

  return 'Could not reach Supabase Auth. Check that the Supabase project is active and VITE_SUPABASE_URL points to the correct project.';
}

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return toast.error('Enter email and password');
    setLoading(true);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      toast.error(getLoginErrorMessage(error.message));
      setLoading(false);
      return;
    }

    // Check approval status after sign-in
    const { data: profile } = await supabase.from('my_profile').select('status, role').single();

    if (!profile) {
      toast.error('Could not load your profile. Contact an admin.');
      await supabase.auth.signOut();
      setLoading(false);
      return;
    }

    if (profile.status === 'pending') {
      await supabase.auth.signOut();
      toast.error('Your account is awaiting admin approval. Check back soon.');
      setLoading(false);
      return;
    }

    if (profile.status === 'denied') {
      await supabase.auth.signOut();
      toast.error('Your access request was not approved. Contact your admin.');
      setLoading(false);
      return;
    }

    if (profile.status === 'suspended') {
      await supabase.auth.signOut();
      toast.error('Your account has been suspended. Contact your admin.');
      setLoading(false);
      return;
    }

    // Approved — let auth state change redirect via App.tsx
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center p-4">
      <Toaster position="top-right" richColors />
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <div className="p-2 bg-[#1B3A5C] rounded-xl">
            <Building2 className="h-7 w-7 text-[#E8720C]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[#1B3A5C]">WholesaleOS</h1>
            <p className="text-xs text-gray-400">Real Estate Control Center</p>
          </div>
        </div>

        <h2 className="text-2xl font-bold text-gray-900 mb-1">Sign in</h2>
        <p className="text-sm text-gray-500 mb-6">
          Enter your credentials to access the platform.
        </p>

        <form onSubmit={handleLogin} className="space-y-4">
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
          />
          <Button type="submit" loading={loading} className="w-full" size="lg">
            Sign In
          </Button>
        </form>

        {/* Register link */}
        <div className="mt-6 pt-5 border-t border-gray-100">
          <p className="text-sm text-gray-500 text-center">
            Don't have an account?{' '}
            <Link to="/register" className="text-[#E8720C] font-medium hover:underline">
              Request Access
            </Link>
          </p>
        </div>

        {/* Pending notice */}
        <div className="mt-4 flex items-start gap-2 bg-gray-50 border border-gray-200 rounded-xl p-3">
          <Clock className="h-4 w-4 text-gray-400 mt-0.5 shrink-0" />
          <p className="text-xs text-gray-500">
            New accounts require admin approval before you can sign in.
          </p>
        </div>
      </div>
    </div>
  );
}
