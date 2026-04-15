'use client';

import { useEffect, useState } from 'react';
import GlassPanel from '../../../../components/GlassPanel';

interface TenantUsage {
  name: string;
  events: Record<string, { count: number; total: number }>;
}

export default function PlatformUsagePage() {
  const [usage, setUsage] = useState<Record<string, TenantUsage>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/platform/usage', { credentials: 'include' })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load usage');
        return res.json();
      })
      .then(setUsage)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6" style={{ color: 'var(--text-dim)' }}>Loading usage data...</div>;

  const tenantSlugs = Object.keys(usage);
  const allEventTypes = new Set<string>();
  for (const slug of tenantSlugs) {
    for (const et of Object.keys(usage[slug].events)) {
      allEventTypes.add(et);
    }
  }
  const eventTypes = Array.from(allEventTypes).sort();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>
        Platform Usage (Last 30 Days)
      </h1>

      {error && (
        <div className="px-4 py-3 rounded-xl text-sm" style={{
          background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
        }}>{error}</div>
      )}

      {tenantSlugs.length === 0 ? (
        <GlassPanel>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>No usage data available yet.</p>
        </GlassPanel>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}>
                <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>
                  Tenant
                </th>
                {eventTypes.map((et) => (
                  <th key={et} className="text-right py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>
                    {et.replace('.', ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tenantSlugs.map((slug) => (
                <tr key={slug} style={{ borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                  <td className="py-3 px-4">
                    <div className="font-medium" style={{ color: 'var(--text)' }}>{usage[slug].name}</div>
                    <div className="text-xs font-mono" style={{ color: 'var(--text-dim)' }}>{slug}</div>
                  </td>
                  {eventTypes.map((et) => {
                    const ev = usage[slug].events[et];
                    return (
                      <td key={et} className="py-3 px-4 text-right font-mono" style={{ color: 'var(--text-muted)' }}>
                        {ev ? ev.total.toLocaleString() : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
