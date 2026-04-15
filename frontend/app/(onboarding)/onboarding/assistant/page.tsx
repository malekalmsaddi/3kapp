'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function OnboardingAssistantPage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState('');
  const [assistantId, setAssistantId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/v1/onboarding/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          openai_api_key: apiKey,
          assistant_id: assistantId,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        router.push('/onboarding/whatsapp');
      } else {
        setError(data.error || 'Validation failed');
      }
    } catch {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
        Configure Your AI Assistant
      </h2>
      <p className="text-sm mb-8" style={{ color: 'var(--text-dim)' }}>
        Connect your OpenAI assistant. We&apos;ll validate the credentials before saving.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 max-w-lg">
        {error && (
          <div className="px-4 py-3 rounded-xl text-sm" style={{
            background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
          }}>
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
            OpenAI API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-proj-..."
            required
            className="w-full px-4 py-3 text-sm rounded-xl outline-none"
            style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
            Assistant ID
          </label>
          <input
            value={assistantId}
            onChange={(e) => setAssistantId(e.target.value)}
            placeholder="asst_..."
            required
            className="w-full px-4 py-3 text-sm rounded-xl outline-none"
            style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="px-8 py-3 text-sm font-bold rounded-xl text-white disabled:opacity-50"
          style={{
            background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
            boxShadow: '0 4px 18px rgba(176,9,9,0.38)',
          }}
        >
          {loading ? 'Validating...' : 'Continue →'}
        </button>
      </form>
    </div>
  );
}
