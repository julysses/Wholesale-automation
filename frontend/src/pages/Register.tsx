/**
 * Register — new user self-signup with pending-approval flow.
 *
 * After signup the user sees a "Pending Approval" screen until an admin
 * approves them. The admin receives an in-app notification automatically
 * (see migration 003, handle_new_user trigger).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Building2, CheckCircle, Clock, LogIn } from 'lucide-react';
import { toast } from 'sonner';
import { Toaster } from 'sonner';

type Stage = 'form' | 'pending';

export function Register() {
  const [stage, setStage] = useState<Stage>('form');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!fullName.trim()) return toast.error('Full name is required');
    if (!email.trim())    return toast.error('Email is required');
    if (password.length < 8) return toast.error('Password must be at least 8 characters');
    if (password !== confirm)  return toast.error('Passwords do not match');

    setLoading(true);
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        // Do NOT automatically sign in — user waits for approval
        emailRedirectTo: window.location.origin + '/login',
      },
    });

    if (error) {
      toast.error(error.message);
    } else {
      setStage('pending');
    }
    setLoading(false);
  };

  /* ── Pending-approval holding screen ──────────────────────────────────────── */
  if (stage === 'pending') {
    return (
      <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center p-4">
        <Toaster position="top-right" richColors />
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8 text-center">
          <div className="flex justify-center mb-4">
            <div className="p-4 bg-yellow-50 rounded-full">
              <Clock className="h-10 w-10 text-yellow-500" />
            </div>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Request Submitted</h2>
          <p className="text-gray-500 mb-6">
            Your account request has been sent to an admin for review.
            You'll receive a notification once your access is approved.
          </p>

          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-left mb-6 space-y-2">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-blue-900">What happens next</p>
                <p className="text-xs text-blue-700 mt-1">
                  An admin will review your request and approve or deny access.
                  You'll see a notification when you sign in after approval.
                </p>
              </div>
            </div>
          </div>

          <Link
            to="/login"
            className="flex items-center justify-center gap-2 w-full py-3 px-4 bg-[#1B3A5C] text-white rounded-xl font-medium hover:bg-[#142d48] transition-colors"
          >
            <LogIn className="h-4 w-4" />
            Back to Sign In
          </Link>
        </div>
      </div>
    );
  }

  /* ── Registration form ────────────────────────────────────────────────────── */
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

        <h2 className="text-2xl font-bold text-gray-900 mb-1">Request Access</h2>
        <p className="text-sm text-gray-500 mb-6">
          Submit your details and an admin will approve your account.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Full Name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jane Smith"
            autoComplete="name"
            required
          />
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="jane@company.com"
            autoComplete="email"
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            autoComplete="new-password"
            required
          />
          <Input
            label="Confirm Password"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Re-enter password"
            autoComplete="new-password"
            required
          />

          <Button type="submit" loading={loading} className="w-full" size="lg">
            Submit Access Request
          </Button>
        </form>

        <p className="text-center text-sm text-gray-500 mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-[#E8720C] font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
