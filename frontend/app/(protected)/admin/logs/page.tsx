'use client';

import { useEffect, useState, useCallback } from 'react';
import GlassPanel from '@/components/GlassPanel';

interface MessageEntry {
  timestamp: string;
  direction: 'inbound' | 'outbound' | 'queued';
  phone: string;
  message: string;
}

interface BulkLogEntry {
  phone?: string;
  status?: string;
  message?: string;
  [key: string]: unknown;
}

type Tab = 'messages' | 'bulk';

const DIRECTION_BADGE: Record<string, string> = {
  inbound: 'bg-blue-100 text-blue-700',
  outbound: 'bg-emerald-100 text-emerald-700',
  queued: 'bg-amber-100 text-amber-700',
};

const STATUS_BADGE: Record<string, string> = {
  queued: 'bg-amber-100 text-amber-700',
  sent: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  skipped: 'bg-gray-100 text-gray-600',
  delivered: 'bg-emerald-100 text-emerald-700',
  read: 'bg-blue-100 text-blue-700',
};

export default function LogsPage() {
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [bulkLogs, setBulkLogs] = useState<BulkLogEntry[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>('messages');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState('');

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/dashboard', {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Failed to load');
      const data = await res.json();
      setMessages(data.messages ?? []);
      setBulkLogs(data.bulk_logs ?? []);
      setError('');
      setLastRefresh(new Date().toLocaleTimeString());
    } catch {
      setError('Could not load log data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
    const tick = () => {
      if (document.visibilityState === 'hidden') return;
      fetchLogs();
    };
    const interval = setInterval(tick, 10000);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [fetchLogs]);

  const displayPhone = (p: string) => p?.replace('whatsapp:', '').trim() ?? '—';
  const truncate = (s: string, n = 80) =>
    s && s.length > n ? s.slice(0, n) + '…' : (s ?? '');

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>
          Activity Logs
        </h1>
        {lastRefresh && (
          <span className="text-xs" style={{ color: 'var(--text-dim)' }}>
            Last updated: {lastRefresh} · auto-refreshes every 10s
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

      {/* Tabs */}
      <GlassPanel>
        <div
          className="flex gap-2 mb-4 pb-3"
          style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
        >
          {(['messages', 'bulk'] as Tab[]).map((tab) => {
            const isActive = activeTab === tab;
            const label =
              tab === 'messages'
                ? `Recent Messages (${messages.length})`
                : `Bulk Send Logs (${bulkLogs.length})`;
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="px-4 py-1.5 rounded-lg text-sm transition-all duration-200 font-medium"
                style={
                  isActive
                    ? {
                        background: 'rgba(176,9,9,0.08)',
                        color: '#b00909',
                        border: '1px solid rgba(176,9,9,0.20)',
                      }
                    : {
                        color: 'var(--text-dim)',
                        border: '1px solid transparent',
                      }
                }
                onMouseEnter={(e) => {
                  if (!isActive)
                    (e.currentTarget as HTMLButtonElement).style.background =
                      'rgba(0,0,0,0.04)';
                }}
                onMouseLeave={(e) => {
                  if (!isActive)
                    (e.currentTarget as HTMLButtonElement).style.background =
                      'transparent';
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Loading…
          </p>
        ) : activeTab === 'messages' ? (
          messages.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
              No messages found.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr
                    className="text-left"
                    style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
                  >
                    {['Timestamp', 'Direction', 'Phone', 'Message'].map((h) => (
                      <th
                        key={h}
                        className="pb-2 pr-4 text-xs font-bold uppercase tracking-wider"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody
                  style={{ borderTop: '1px solid transparent' }}
                  className="divide-y divide-gray-100"
                >
                  {messages.map((m, i) => (
                    <tr key={`${m.timestamp}-${m.phone}-${i}`} className="hover:bg-gray-50">
                      <td
                        className="py-2 pr-4 text-xs whitespace-nowrap font-mono"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {m.timestamp}
                      </td>
                      <td className="py-2 pr-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold ${DIRECTION_BADGE[m.direction] ?? 'bg-gray-100 text-gray-600'}`}
                        >
                          {m.direction}
                        </span>
                      </td>
                      <td
                        className="py-2 pr-4 font-mono text-xs"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {displayPhone(m.phone)}
                      </td>
                      <td
                        className="py-2 text-xs"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {truncate(m.message)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : bulkLogs.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            No bulk send logs from the latest task.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr
                  className="text-left"
                  style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
                >
                  {['Phone', 'Status', 'Details'].map((h) => (
                    <th
                      key={h}
                      className="pb-2 pr-4 text-xs font-bold uppercase tracking-wider"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {bulkLogs.map((l, i) => (
                  <tr key={`${l.to ?? ''}-${l.result ?? ''}-${i}`} className="hover:bg-gray-50">
                    <td
                      className="py-2 pr-4 font-mono text-xs"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {displayPhone(l.phone ?? '')}
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_BADGE[l.status ?? ''] ?? 'bg-gray-100 text-gray-600'}`}
                      >
                        {l.status ?? '—'}
                      </span>
                    </td>
                    <td
                      className="py-2 text-xs"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {truncate(l.message ?? '')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>

      <GlassPanel>
        <p className="text-xs" style={{ color: 'var(--text-dim)' }}>
          Recent Messages shows the last 50 messages across all users. Bulk Send
          Logs shows delivery results from the most recently initiated bulk send
          task.
        </p>
      </GlassPanel>
    </div>
  );
}
