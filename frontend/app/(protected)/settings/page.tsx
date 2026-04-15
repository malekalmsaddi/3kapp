'use client';

import { useEffect, useState } from 'react';

const panel: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(0,0,0,0.07)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04)',
};

export default function SettingsPage() {
  const [notify, setNotify] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/settings', { credentials: 'include' })
      .then((r) => r.json())
      .then((d) => setNotify(d.notify ?? true))
      .catch(() => setError('Failed to load settings.'))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ notify }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>
          Settings
        </h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-dim)' }}>
          Manage your account preferences
        </p>
      </div>

      {/* Notifications card */}
      <div className="rounded-2xl p-6" style={panel}>
        <h2
          className="text-xs font-bold uppercase tracking-widest mb-5"
          style={{ color: 'var(--text-dim)' }}
        >
          Notifications
        </h2>

        {loading ? (
          <div
            className="flex items-center gap-2.5 text-sm"
            style={{ color: 'var(--text-dim)' }}
          >
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
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            Loading…
          </div>
        ) : (
          <div className="space-y-5">
            {/* Toggle row */}
            <div
              className="flex items-center justify-between p-4 rounded-xl"
              style={{
                background: '#f9fafb',
                border: '1px solid rgba(0,0,0,0.07)',
              }}
            >
              <div>
                <div
                  id="notify-label"
                  className="text-sm font-semibold"
                  style={{ color: 'var(--text)' }}
                >
                  Email notifications
                </div>
                <div
                  className="text-xs mt-0.5"
                  style={{ color: 'var(--text-dim)' }}
                >
                  Receive alerts when new messages arrive
                </div>
              </div>

              {/* Toggle switch */}
              <button
                role="switch"
                aria-checked={notify}
                aria-labelledby="notify-label"
                onClick={() => setNotify((v) => !v)}
                className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-all duration-300"
                style={{
                  background: notify
                    ? 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)'
                    : 'rgba(0,0,0,0.15)',
                  boxShadow: notify ? '0 2px 10px rgba(176,9,9,0.35)' : 'none',
                }}
              >
                <span
                  className="inline-block h-5 w-5 rounded-full bg-white shadow-md transition-transform mt-0.5"
                  style={{
                    transform: notify ? 'translateX(22px)' : 'translateX(2px)',
                  }}
                />
              </button>
            </div>

            {/* Feedback */}
            {error && (
              <p className="text-sm" role="alert" style={{ color: '#b00909' }}>
                {error}
              </p>
            )}
            {saved && (
              <p
                className="text-sm flex items-center gap-1.5"
                role="status"
                style={{ color: '#16a34a' }}
              >
                <svg
                  width="14"
                  height="14"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Settings saved
              </p>
            )}

            {/* Save */}
            <button
              onClick={save}
              disabled={saving}
              className="px-5 py-2.5 text-sm font-bold rounded-xl text-white transition-all duration-200 disabled:opacity-40"
              style={{
                background: saving
                  ? 'rgba(176,9,9,0.50)'
                  : 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                boxShadow: saving ? 'none' : '0 3px 16px rgba(176,9,9,0.30)',
              }}
              onMouseEnter={(e) => {
                if (!saving) {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.transform = 'translateY(-1px)';
                  el.style.boxShadow = '0 6px 24px rgba(176,9,9,0.45)';
                }
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLButtonElement;
                el.style.transform = 'translateY(0)';
                el.style.boxShadow = saving
                  ? 'none'
                  : '0 3px 16px rgba(176,9,9,0.30)';
              }}
            >
              {saving ? (
                <span className="flex items-center gap-2">
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
                  Saving…
                </span>
              ) : (
                'Save Changes'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
