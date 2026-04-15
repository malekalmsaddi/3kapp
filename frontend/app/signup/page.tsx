'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import Link from 'next/link';

export default function SignupPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [plan, setPlan] = useState('free');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/v1/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          company_name: companyName,
          email,
          password,
          plan,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        // Signup successful — redirect to onboarding or dashboard
        router.replace('/dashboard');
      } else {
        setError(data.message || 'Signup failed');
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = (field: string): React.CSSProperties => ({
    background: '#ffffff',
    border:
      focused === field ? '1px solid #b00909' : '1px solid rgba(0,0,0,0.12)',
    color: 'var(--text)',
    boxShadow: focused === field ? '0 0 0 3px rgba(176,9,9,0.10)' : 'none',
    transition: 'all 0.2s ease',
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm animate-fade-up">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <div
            className="w-16 h-16 rounded-3xl flex items-center justify-center mb-5"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow:
                '0 4px 32px rgba(176,9,9,0.35), 0 0 0 6px rgba(176,9,9,0.08)',
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="white">
              <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
            </svg>
          </div>
          <h1
            className="text-3xl font-bold"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Moeen AI
          </h1>
          <p className="text-sm mt-2" style={{ color: 'var(--text-dim)' }}>
            Create your AI assistant workspace
          </p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: '#ffffff',
            border: '1px solid rgba(0,0,0,0.08)',
            boxShadow:
              '0 4px 6px rgba(0,0,0,0.05), 0 16px 48px rgba(176,9,9,0.08)',
          }}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div
                className="px-4 py-3 rounded-xl text-sm"
                style={{
                  background: 'rgba(176,9,9,0.06)',
                  border: '1px solid rgba(176,9,9,0.25)',
                  color: '#b00909',
                }}
              >
                {error}
              </div>
            )}

            {/* Company Name */}
            <div className="space-y-2">
              <label
                className="block text-xs font-bold tracking-widest uppercase"
                style={{ color: 'var(--text-dim)' }}
              >
                Company Name
              </label>
              <input
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                onFocus={() => setFocused('company')}
                onBlur={() => setFocused(null)}
                placeholder="Your company name"
                required
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={inputStyle('company')}
              />
            </div>

            {/* Email */}
            <div className="space-y-2">
              <label
                className="block text-xs font-bold tracking-widest uppercase"
                style={{ color: 'var(--text-dim)' }}
              >
                Email
              </label>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocused('email')}
                onBlur={() => setFocused(null)}
                placeholder="you@company.com"
                required
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={inputStyle('email')}
              />
            </div>

            {/* Password */}
            <div className="space-y-2">
              <label
                className="block text-xs font-bold tracking-widest uppercase"
                style={{ color: 'var(--text-dim)' }}
              >
                Password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocused('password')}
                onBlur={() => setFocused(null)}
                placeholder="Min 8 characters"
                required
                minLength={8}
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={inputStyle('password')}
              />
            </div>

            {/* Plan */}
            <div className="space-y-2">
              <label
                className="block text-xs font-bold tracking-widest uppercase"
                style={{ color: 'var(--text-dim)' }}
              >
                Plan
              </label>
              <select
                value={plan}
                onChange={(e) => setPlan(e.target.value)}
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={{
                  background: '#ffffff',
                  border: '1px solid rgba(0,0,0,0.12)',
                  color: 'var(--text)',
                }}
              >
                <option value="free">Free</option>
                <option value="starter">Starter — $49/mo</option>
                <option value="pro">Pro — $149/mo</option>
              </select>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 text-sm font-bold rounded-xl text-white mt-1 disabled:opacity-50 transition-all duration-200"
              style={{
                background: loading
                  ? 'rgba(176,9,9,0.50)'
                  : 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                boxShadow: loading
                  ? 'none'
                  : '0 4px 18px rgba(176,9,9,0.38)',
              }}
            >
              {loading ? 'Creating workspace...' : 'Create Workspace →'}
            </button>
          </form>
        </div>

        <p
          className="text-center text-sm mt-6"
          style={{ color: 'var(--text-dim)' }}
        >
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-medium"
            style={{ color: '#b00909' }}
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
