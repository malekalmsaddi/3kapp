'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function OnboardingWhatsAppPage() {
  const router = useRouter();
  const [webhookUrl, setWebhookUrl] = useState('');
  const [accountSid, setAccountSid] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [whatsappNumber, setWhatsappNumber] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const body: Record<string, string> = {};
      if (accountSid) {
        body.twilio_account_sid = accountSid;
        body.twilio_auth_token = authToken;
        body.twilio_whatsapp_number = whatsappNumber;
      }

      const res = await fetch('/api/v1/onboarding/whatsapp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.webhook_url) setWebhookUrl(data.webhook_url);
        router.push('/onboarding/calendar');
      } else {
        setError(data.error || 'Failed to save');
      }
    } catch {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  }

  // Load the webhook URL
  useEffect(() => {
    fetch('/api/v1/auth/me', { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        if (data.tenant_slug) {
          setWebhookUrl(`${window.location.origin}/whatsapp/${data.tenant_slug}`);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="animate-fade-up">
      <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
        Connect WhatsApp
      </h2>
      <p className="text-sm mb-8" style={{ color: 'var(--text-dim)' }}>
        Set up the Twilio webhook so incoming WhatsApp messages reach your assistant.
      </p>

      {webhookUrl && (
        <div className="mb-8 p-4 rounded-xl" style={{
          background: 'rgba(176,9,9,0.04)', border: '1px solid rgba(176,9,9,0.15)',
        }}>
          <p className="text-xs font-bold uppercase tracking-widest mb-2" style={{ color: 'var(--text-dim)' }}>
            Your Webhook URL
          </p>
          <code className="text-sm font-mono" style={{ color: '#b00909' }}>
            {webhookUrl}
          </code>
          <p className="text-xs mt-2" style={{ color: 'var(--text-dim)' }}>
            Paste this URL in your Twilio WhatsApp Sandbox or number configuration.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5 max-w-lg">
        {error && (
          <div className="px-4 py-3 rounded-xl text-sm" style={{
            background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
          }}>
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-xs font-medium"
          style={{ color: '#6d1f9e' }}
        >
          {showAdvanced ? '▼ Hide' : '▶ Advanced'}: Use your own Twilio credentials (Pro plan)
        </button>

        {showAdvanced && (
          <div className="space-y-4 pl-4" style={{ borderLeft: '2px solid rgba(109,31,158,0.2)' }}>
            <div className="space-y-2">
              <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
                Twilio Account SID
              </label>
              <input value={accountSid} onChange={(e) => setAccountSid(e.target.value)}
                placeholder="AC..." className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
                Auth Token
              </label>
              <input type="password" value={authToken} onChange={(e) => setAuthToken(e.target.value)}
                className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
                WhatsApp Number
              </label>
              <input value={whatsappNumber} onChange={(e) => setWhatsappNumber(e.target.value)}
                placeholder="+1234567890" className="w-full px-4 py-3 text-sm rounded-xl outline-none"
                style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
            </div>
          </div>
        )}

        <button type="submit" disabled={loading}
          className="px-8 py-3 text-sm font-bold rounded-xl text-white disabled:opacity-50"
          style={{
            background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
            boxShadow: '0 4px 18px rgba(176,9,9,0.38)',
          }}>
          {loading ? 'Saving...' : 'Continue →'}
        </button>
      </form>
    </div>
  );
}
