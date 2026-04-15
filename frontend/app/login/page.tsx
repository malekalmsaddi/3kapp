'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    const body = new URLSearchParams({ username, password });
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        body,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'include',
      });
      if (res.ok) {
        router.replace('/dashboard');
      } else {
        try {
          const data = await res.json();
          setError(data.message || 'Invalid credentials');
        } catch {
          setError('Invalid credentials');
        }
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
        {/* Logo mark */}
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
            Sign in to your workspace
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

            {/* Username */}
            <div className="space-y-2">
              <label
                className="block text-xs font-bold tracking-widest uppercase"
                style={{ color: 'var(--text-dim)' }}
              >
                Username
              </label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onFocus={() => setFocused('username')}
                onBlur={() => setFocused(null)}
                placeholder="Enter your username"
                required
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={inputStyle('username')}
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
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocused('password')}
                onBlur={() => setFocused(null)}
                placeholder="Enter your password"
                required
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={inputStyle('password')}
              />
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
                boxShadow: loading ? 'none' : '0 4px 18px rgba(176,9,9,0.38)',
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.transform = 'translateY(-1px)';
                  el.style.boxShadow = '0 8px 28px rgba(176,9,9,0.50)';
                }
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLButtonElement;
                el.style.transform = 'translateY(0)';
                el.style.boxShadow = loading
                  ? 'none'
                  : '0 4px 18px rgba(176,9,9,0.38)';
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg
                    className="animate-spin w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="white"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="white"
                      d="M4 12a8 8 0 018-8v8H4z"
                    />
                  </svg>
                  Signing in…
                </span>
              ) : (
                'Sign In →'
              )}
            </button>
          </form>
        </div>

        <p
          className="text-center text-xs mt-6"
          style={{ color: 'var(--text-dim)' }}
        >
          Moeen AI · Workspace Dashboard
        </p>
      </div>
    </div>
  );
}
