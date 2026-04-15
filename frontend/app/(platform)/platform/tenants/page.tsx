'use client';

import { useEffect, useState } from 'react';
import GlassPanel from '../../../../components/GlassPanel';

interface Tenant {
  id: string;
  slug: string;
  name: string;
  status: string;
  plan_name: string;
  plan_display_name: string;
  user_count: number;
  created_at: string;
  timezone: string;
}

export default function PlatformTenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/platform/tenants', { credentials: 'include' })
      .then((res) => {
        if (res.status === 403) throw new Error('Access denied — super admin only');
        if (!res.ok) throw new Error('Failed to load tenants');
        return res.json();
      })
      .then(setTenants)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleAction(tenantId: string, action: 'suspend' | 'activate') {
    try {
      const res = await fetch(`/platform/tenants/${tenantId}/${action}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (res.ok) {
        setTenants((prev) =>
          prev.map((t) =>
            t.id === tenantId
              ? { ...t, status: action === 'suspend' ? 'suspended' : 'active' }
              : t,
          ),
        );
      }
    } catch {
      setError(`Failed to ${action} tenant`);
    }
  }

  if (loading) return <div className="p-6" style={{ color: 'var(--text-dim)' }}>Loading tenants...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>
          All Tenants
        </h1>
        <span className="text-sm" style={{ color: 'var(--text-dim)' }}>
          {tenants.length} total
        </span>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-xl text-sm" style={{
          background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
        }}>{error}</div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Tenant</th>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Slug</th>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Plan</th>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Users</th>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Status</th>
              <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Created</th>
              <th className="text-right py-3 px-4 font-bold text-xs uppercase tracking-widest" style={{ color: 'var(--text-dim)' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.id} style={{ borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                <td className="py-3 px-4 font-medium" style={{ color: 'var(--text)' }}>{t.name}</td>
                <td className="py-3 px-4 font-mono text-xs" style={{ color: 'var(--text-dim)' }}>{t.slug}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-1 rounded-md text-xs font-bold" style={{
                    background: 'rgba(109,31,158,0.08)', color: '#6d1f9e',
                  }}>{t.plan_display_name || t.plan_name}</span>
                </td>
                <td className="py-3 px-4" style={{ color: 'var(--text-muted)' }}>{t.user_count}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-1 rounded-md text-xs font-bold" style={{
                    background: t.status === 'active' ? 'rgba(22,163,74,0.08)' :
                      t.status === 'suspended' ? 'rgba(176,9,9,0.08)' : 'rgba(217,119,6,0.08)',
                    color: t.status === 'active' ? '#16a34a' :
                      t.status === 'suspended' ? '#b00909' : '#d97706',
                  }}>{t.status}</span>
                </td>
                <td className="py-3 px-4 text-xs" style={{ color: 'var(--text-dim)' }}>
                  {new Date(t.created_at).toLocaleDateString()}
                </td>
                <td className="py-3 px-4 text-right">
                  {t.status === 'active' ? (
                    <button onClick={() => handleAction(t.id, 'suspend')}
                      className="px-3 py-1 text-xs font-medium rounded-md"
                      style={{ border: '1px solid rgba(176,9,9,0.3)', color: '#b00909' }}>
                      Suspend
                    </button>
                  ) : t.status === 'suspended' ? (
                    <button onClick={() => handleAction(t.id, 'activate')}
                      className="px-3 py-1 text-xs font-medium rounded-md"
                      style={{ border: '1px solid rgba(22,163,74,0.3)', color: '#16a34a' }}>
                      Activate
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
