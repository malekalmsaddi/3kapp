'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function OnboardingCalendarPage() {
  const router = useRouter();
  const [calendarId, setCalendarId] = useState('');
  const [timezone, setTimezone] = useState('UTC');
  const [credentialsJson, setCredentialsJson] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    let credentials;
    try {
      credentials = JSON.parse(credentialsJson);
    } catch {
      setError('Invalid JSON for service account credentials');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch('/api/v1/onboarding/calendar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ calendar_id: calendarId, timezone, credentials }),
      });
      const data = await res.json();
      if (res.ok) {
        router.push('/onboarding/branding');
      } else {
        setError(data.error || 'Failed to save');
      }
    } catch {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  }

  async function handleSkip() {
    await fetch('/api/v1/onboarding/calendar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ skip: true }),
    });
    router.push('/onboarding/branding');
  }

  return (
    <div className="animate-fade-up">
      <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
        Google Calendar (Optional)
      </h2>
      <p className="text-sm mb-8" style={{ color: 'var(--text-dim)' }}>
        Enable calendar integration so your assistant can check availability and create events.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 max-w-lg">
        {error && (
          <div className="px-4 py-3 rounded-xl text-sm" style={{
            background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
          }}>{error}</div>
        )}

        <div className="space-y-2">
          <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
            Calendar ID
          </label>
          <input value={calendarId} onChange={(e) => setCalendarId(e.target.value)}
            placeholder="your-email@company.com" required
            className="w-full px-4 py-3 text-sm rounded-xl outline-none"
            style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
        </div>

        <div className="space-y-2">
          <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
            Timezone
          </label>
          <input value={timezone} onChange={(e) => setTimezone(e.target.value)}
            placeholder="Asia/Qatar"
            className="w-full px-4 py-3 text-sm rounded-xl outline-none"
            style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
        </div>

        <div className="space-y-2">
          <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
            Service Account JSON
          </label>
          <textarea value={credentialsJson} onChange={(e) => setCredentialsJson(e.target.value)}
            placeholder='Paste your Google service account JSON here...'
            rows={6} required
            className="w-full px-4 py-3 text-sm rounded-xl outline-none font-mono"
            style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
        </div>

        <div className="flex gap-3">
          <button type="submit" disabled={loading}
            className="px-8 py-3 text-sm font-bold rounded-xl text-white disabled:opacity-50"
            style={{
              background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: '0 4px 18px rgba(176,9,9,0.38)',
            }}>
            {loading ? 'Saving...' : 'Continue →'}
          </button>
          <button type="button" onClick={handleSkip}
            className="px-8 py-3 text-sm font-medium rounded-xl"
            style={{ border: '1px solid rgba(0,0,0,0.12)', color: 'var(--text-dim)' }}>
            Skip for now
          </button>
        </div>
      </form>
    </div>
  );
}
