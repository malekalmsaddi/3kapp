'use client';

import { useEffect, useState, useCallback } from 'react';
import GlassPanel from '@/components/GlassPanel';

interface ThreadEntry {
  user_id: string;
  thread_id: string;
  last_accessed: string;
}

export default function ThreadsPage() {
  const [threads, setThreads] = useState<ThreadEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [flash, setFlash] = useState('');

  const fetchThreads = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/dashboard', {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Failed to load');
      const data = await res.json();
      setThreads(data.thread_map ?? []);
      setError('');
    } catch {
      setError('Could not load thread data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchThreads();
    const interval = setInterval(fetchThreads, 10000);
    return () => clearInterval(interval);
  }, [fetchThreads]);

  async function deleteThread(threadId: string) {
    setDeletingId(threadId);
    try {
      const res = await fetch(`/api/admin/delete_thread/${threadId}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(await res.text());
      setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
      setFlash(`Thread ${threadId.slice(0, 12)}… deleted.`);
      setTimeout(() => setFlash(''), 3000);
    } catch {
      setError('Failed to delete thread.');
    } finally {
      setDeletingId(null);
    }
  }

  const displayPhone = (p: string) => p.replace('whatsapp:', '').trim();

  return (
    <div className="space-y-4">
      <GlassPanel>
        <div className="flex items-center justify-between mb-4">
          <h1
            className="text-xl font-semibold"
            style={{ color: 'var(--text)' }}
          >
            Thread Management
          </h1>
          <span className="text-sm" style={{ color: 'var(--text-dim)' }}>
            {threads.length} active thread{threads.length !== 1 ? 's' : ''}
          </span>
        </div>

        {flash && (
          <p className="text-sm mb-3" style={{ color: '#15803d' }}>
            {flash}
          </p>
        )}
        {error && (
          <p className="text-sm mb-3" style={{ color: '#b00909' }}>
            {error}
          </p>
        )}

        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Loading…
          </p>
        ) : threads.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            No OpenAI threads found.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr
                  className="text-left"
                  style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
                >
                  {['Phone', 'Thread ID', 'Last Accessed', 'Action'].map(
                    (h) => (
                      <th
                        key={h}
                        className="pb-2 pr-4 text-xs font-bold uppercase tracking-wider"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {threads.map((t) => (
                  <tr key={t.thread_id} className="hover:bg-gray-50">
                    <td
                      className="py-2 pr-4 font-mono text-xs"
                      style={{ color: 'var(--text)' }}
                    >
                      {displayPhone(t.user_id)}
                    </td>
                    <td
                      className="py-2 pr-4 font-mono text-xs"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {t.thread_id}
                    </td>
                    <td
                      className="py-2 pr-4 text-xs whitespace-nowrap"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {t.last_accessed}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => deleteThread(t.thread_id)}
                        disabled={deletingId === t.thread_id}
                        className="px-3 py-1 text-xs rounded-lg text-white transition-all duration-150 disabled:opacity-40"
                        style={{
                          background:
                            deletingId === t.thread_id
                              ? 'rgba(176,9,9,0.50)'
                              : '#b00909',
                          boxShadow:
                            deletingId === t.thread_id
                              ? 'none'
                              : '0 1px 6px rgba(176,9,9,0.25)',
                        }}
                        onMouseEnter={(e) => {
                          if (deletingId !== t.thread_id) {
                            (
                              e.currentTarget as HTMLButtonElement
                            ).style.background = '#8b0707';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (deletingId !== t.thread_id) {
                            (
                              e.currentTarget as HTMLButtonElement
                            ).style.background = '#b00909';
                          }
                        }}
                      >
                        {deletingId === t.thread_id ? 'Deleting…' : 'Delete'}
                      </button>
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
          Deleting a thread removes the OpenAI conversation history for that
          user. The next message from that user will start a fresh thread. This
          page auto-refreshes every 10 seconds.
        </p>
      </GlassPanel>
    </div>
  );
}
