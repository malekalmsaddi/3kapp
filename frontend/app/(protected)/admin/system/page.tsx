'use client';

import { useEffect, useState, useCallback } from 'react';
import GlassPanel from '@/components/GlassPanel';

interface DbStats {
  available: number;
  active: number;
  total: number;
}

interface SystemData {
  health: 'ok' | 'error' | null;
  db: DbStats | null;
  limiterKeys: Record<string, string>;
}

function parseMetrics(text: string): DbStats {
  try {
    const lines = text.trim().split('\n');
    const get = (key: string) => {
      const line = lines.find((l) => l.startsWith(key));
      if (!line) return 0;
      const val = parseInt(line.split(' ')[1], 10);
      return isNaN(val) ? 0 : val;
    };
    const available = get('db_connections_available');
    const active = get('db_connections_active');
    const total = get('db_messages_total');
    return { available, active, total };
  } catch {
    return { available: 0, active: 0, total: 0 };
  }
}

export default function SystemPage() {
  const [data, setData] = useState<SystemData>({
    health: null,
    db: null,
    limiterKeys: {},
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState<string>('');

  const fetchAll = useCallback(async () => {
    try {
      const [healthRes, metricsRes, adminRes] = await Promise.all([
        fetch('/api/health', { credentials: 'include' }),
        fetch('/api/metrics', { credentials: 'include' }),
        fetch('/api/admin/dashboard', { credentials: 'include' }),
      ]);

      const healthOk = healthRes.ok ? 'ok' : 'error';
      const metricsText = metricsRes.ok ? await metricsRes.text() : '';
      const db = metricsText ? parseMetrics(metricsText) : null;
      const adminData = adminRes.ok ? await adminRes.json() : {};
      const limiterKeys: Record<string, string> = adminData.limiter_keys ?? {};

      setData({ health: healthOk as 'ok' | 'error', db, limiterKeys });
      setError('');
      setLastRefresh(new Date().toLocaleTimeString());
    } catch {
      setError('Could not load system data.');
      setData((prev) => ({ ...prev, health: 'error' }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 15000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const limiterEntries = Object.entries(data.limiterKeys);

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>
          System Health
        </h1>
        {lastRefresh && (
          <span className="text-xs" style={{ color: 'var(--text-dim)' }}>
            Last updated: {lastRefresh} · auto-refreshes every 15s
          </span>
        )}
      </div>

      {error && (
        <GlassPanel>
          <p className="text-sm" role="alert" style={{ color: '#b00909' }}>
            {error}
          </p>
        </GlassPanel>
      )}

      {/* Service Status */}
      <GlassPanel>
        <h2
          className="text-xs font-bold uppercase tracking-widest mb-3"
          style={{ color: 'var(--text-dim)' }}
        >
          Service Status
        </h2>
        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Checking…
          </p>
        ) : (
          <div className="flex items-center gap-3">
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                data.health === 'ok' ? 'bg-emerald-500' : 'bg-red-500'
              }`}
              style={{
                boxShadow:
                  data.health === 'ok' ? '0 0 6px #10b981' : '0 0 6px #ef4444',
              }}
            />
            <span
              className="text-sm font-medium"
              style={{ color: 'var(--text)' }}
            >
              Flask API:{' '}
              <span
                style={{
                  color: data.health === 'ok' ? '#15803d' : '#b00909',
                }}
              >
                {data.health === 'ok' ? 'Healthy' : 'Unreachable'}
              </span>
            </span>
          </div>
        )}
      </GlassPanel>

      {/* Database Pool */}
      <GlassPanel>
        <h2
          className="text-xs font-bold uppercase tracking-widest mb-3"
          style={{ color: 'var(--text-dim)' }}
        >
          Database Pool
        </h2>
        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Loading…
          </p>
        ) : data.db ? (
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: '#15803d' }}>
                {data.db.available}
              </div>
              <div
                className="text-xs mt-1"
                style={{ color: 'var(--text-dim)' }}
              >
                Available connections
              </div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: '#1d4ed8' }}>
                {data.db.active}
              </div>
              <div
                className="text-xs mt-1"
                style={{ color: 'var(--text-dim)' }}
              >
                Active connections
              </div>
            </div>
            <div className="text-center">
              <div
                className="text-2xl font-bold"
                style={{ color: 'var(--text)' }}
              >
                {data.db.total.toLocaleString()}
              </div>
              <div
                className="text-xs mt-1"
                style={{ color: 'var(--text-dim)' }}
              >
                Total messages logged
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Metrics unavailable.
          </p>
        )}
      </GlassPanel>

      {/* Rate Limiter Keys */}
      <GlassPanel>
        <div className="flex items-center justify-between mb-3">
          <h2
            className="text-xs font-bold uppercase tracking-widest"
            style={{ color: 'var(--text-dim)' }}
          >
            Rate Limiter Keys
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-dim)' }}>
            {limiterEntries.length} active
          </span>
        </div>
        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Loading…
          </p>
        ) : limiterEntries.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            No active rate limiter entries.
          </p>
        ) : (
          <div className="max-h-64 overflow-y-auto space-y-1 font-mono text-xs">
            {limiterEntries.map(([key, val]) => (
              <div
                key={key}
                className="flex justify-between gap-4 py-1"
                style={{ borderBottom: '1px solid rgba(0,0,0,0.06)' }}
              >
                <span
                  style={{ color: 'var(--text-muted)' }}
                  className="truncate"
                >
                  {key}
                </span>
                <span style={{ color: '#1d4ed8' }} className="shrink-0">
                  {val}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
