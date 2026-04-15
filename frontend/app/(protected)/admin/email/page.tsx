'use client';

import { useState } from 'react';
import GlassPanel from '@/components/GlassPanel';

interface SendResult {
  status: 'success' | 'partial' | 'error';
  sent?: string[];
  failed?: Record<string, string>;
  message?: string;
}

const inputCls =
  'w-full px-3.5 py-2.5 text-sm rounded-xl outline-none transition-all duration-200';

const inputStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(0,0,0,0.12)',
  color: 'var(--text)',
};

function handleFocus(
  e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>,
) {
  e.currentTarget.style.borderColor = '#b00909';
  e.currentTarget.style.boxShadow = '0 0 0 3px rgba(176,9,9,0.10)';
}
function handleBlur(
  e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>,
) {
  e.currentTarget.style.borderColor = 'rgba(0,0,0,0.12)';
  e.currentTarget.style.boxShadow = 'none';
}

export default function EmailPage() {
  const [toEmail, setToEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SendResult | null>(null);
  const [error, setError] = useState('');

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!toEmail.trim() || !subject.trim() || !body.trim()) return;
    setSending(true);
    setResult(null);
    setError('');
    try {
      const res = await fetch('/api/send_email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          to_email: toEmail.trim(),
          subject: subject.trim(),
          body: body.trim(),
        }),
      });
      const data: SendResult = await res.json();
      if (!res.ok) {
        setError(data.message ?? 'Failed to send email.');
      } else {
        setResult(data);
        if (data.status === 'success') {
          setToEmail('');
          setSubject('');
          setBody('');
        }
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <GlassPanel>
        <h1 className="text-xl font-bold mb-5" style={{ color: 'var(--text)' }}>
          Send Email
        </h1>

        <form onSubmit={send} className="space-y-4">
          <div>
            <label
              className="block text-xs font-bold uppercase tracking-wider mb-1.5"
              style={{ color: 'var(--text-dim)' }}
            >
              To
            </label>
            <input
              type="email"
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              placeholder="recipient@example.com"
              required
              className={inputCls}
              style={inputStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
          </div>

          <div>
            <label
              className="block text-xs font-bold uppercase tracking-wider mb-1.5"
              style={{ color: 'var(--text-dim)' }}
            >
              Subject
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject"
              required
              className={inputCls}
              style={inputStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
          </div>

          <div>
            <label
              className="block text-xs font-bold uppercase tracking-wider mb-1.5"
              style={{ color: 'var(--text-dim)' }}
            >
              Body
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your message here…"
              required
              rows={6}
              className={`${inputCls} resize-none`}
              style={inputStyle}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
          </div>

          {error && (
            <p className="text-sm" style={{ color: '#b00909' }}>
              {error}
            </p>
          )}

          {result && (
            <div
              className="text-sm rounded-xl px-4 py-3"
              style={
                result.status === 'success'
                  ? {
                      background: 'rgba(22,163,74,0.08)',
                      border: '1px solid rgba(22,163,74,0.25)',
                      color: '#15803d',
                    }
                  : result.status === 'partial'
                    ? {
                        background: 'rgba(217,119,6,0.08)',
                        border: '1px solid rgba(217,119,6,0.25)',
                        color: '#92400e',
                      }
                    : {
                        background: 'rgba(176,9,9,0.07)',
                        border: '1px solid rgba(176,9,9,0.22)',
                        color: '#b00909',
                      }
              }
            >
              {result.status === 'success' && (
                <>
                  <p className="font-semibold">Sent successfully</p>
                  {result.sent && result.sent.length > 0 && (
                    <ul className="mt-1 text-xs opacity-80 list-disc list-inside">
                      {result.sent.map((addr) => (
                        <li key={addr}>{addr}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {result.status === 'partial' && (
                <>
                  <p className="font-semibold">Partially sent</p>
                  {result.sent && (
                    <p className="text-xs mt-1">
                      Sent: {result.sent.join(', ')}
                    </p>
                  )}
                  {result.failed && (
                    <p className="text-xs mt-1">
                      Failed:{' '}
                      {Object.entries(result.failed)
                        .map(([k, v]) => `${k} (${v})`)
                        .join(', ')}
                    </p>
                  )}
                </>
              )}
              {result.status === 'error' && (
                <p className="font-semibold">
                  {result.message ?? 'Failed to send.'}
                </p>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={sending}
            className="px-5 py-2.5 text-sm font-bold rounded-xl text-white transition-all duration-200 disabled:opacity-40"
            style={{
              background: sending
                ? 'rgba(176,9,9,0.50)'
                : 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: sending ? 'none' : '0 3px 16px rgba(176,9,9,0.30)',
            }}
            onMouseEnter={(e) => {
              if (!sending) {
                const el = e.currentTarget as HTMLButtonElement;
                el.style.transform = 'translateY(-1px)';
                el.style.boxShadow = '0 6px 24px rgba(176,9,9,0.45)';
              }
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.transform = 'translateY(0)';
              el.style.boxShadow = sending
                ? 'none'
                : '0 3px 16px rgba(176,9,9,0.30)';
            }}
          >
            {sending ? 'Sending…' : 'Send Email →'}
          </button>
        </form>
      </GlassPanel>

      <GlassPanel>
        <p className="text-xs" style={{ color: 'var(--text-dim)' }}>
          Emails are sent via SendGrid using the configured sender address. The
          &quot;To&quot; field accepts a single recipient email address.
        </p>
      </GlassPanel>
    </div>
  );
}
