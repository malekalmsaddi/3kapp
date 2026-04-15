'use client';

import { useEffect, useState, useCallback } from 'react';
import GlassPanel from '../../../../components/GlassPanel';

interface Escalation {
  user_id: string;
  thread_id: string;
  escalated_at: string;
  last_message: string | null;
  last_msg_time: string | null;
}

export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [replyMsg, setReplyMsg] = useState('');
  const [error, setError] = useState('');

  const fetchEscalations = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/escalations', {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        setEscalations(data);
      }
    } catch {
      setError('Failed to load escalations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEscalations();
    const interval = setInterval(fetchEscalations, 15000);
    return () => clearInterval(interval);
  }, [fetchEscalations]);

  async function handleResolve(phone: string) {
    setResolving(phone);
    try {
      await fetch(`/api/admin/escalations/${encodeURIComponent(phone)}/resolve`, {
        method: 'POST',
        credentials: 'include',
      });
      setEscalations((prev) => prev.filter((e) => e.user_id !== phone));
    } catch {
      setError('Failed to resolve escalation');
    } finally {
      setResolving(null);
    }
  }

  async function handleReply(phone: string) {
    if (!replyMsg.trim()) return;
    try {
      await fetch('/api/admin/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_number: phone,
          message: replyMsg,
          mode: 'admin_to_user',
        }),
      });
      setReplyMsg('');
      setReplyTo(null);
    } catch {
      setError('Failed to send reply');
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <p style={{ color: 'var(--text-dim)' }}>Loading escalations...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>
        Escalated Conversations
      </h1>

      {error && (
        <div
          className="px-4 py-3 rounded-xl text-sm"
          style={{
            background: 'rgba(176,9,9,0.06)',
            border: '1px solid rgba(176,9,9,0.25)',
            color: '#b00909',
          }}
        >
          {error}
        </div>
      )}

      {escalations.length === 0 ? (
        <GlassPanel>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            No escalated conversations at this time.
          </p>
        </GlassPanel>
      ) : (
        <div className="space-y-4">
          {escalations.map((esc) => (
            <GlassPanel key={esc.user_id}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-sm font-bold" style={{ color: 'var(--text)' }}>
                    {esc.user_id}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-dim)' }}>
                    Escalated: {esc.escalated_at ? new Date(esc.escalated_at).toLocaleString() : 'Unknown'}
                  </p>
                  {esc.last_message && (
                    <p className="text-sm mt-2 truncate" style={{ color: 'var(--text-muted)' }}>
                      {esc.last_message}
                    </p>
                  )}
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setReplyTo(replyTo === esc.user_id ? null : esc.user_id)}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg"
                    style={{
                      border: '1px solid rgba(109,31,158,0.3)',
                      color: '#6d1f9e',
                      background: 'rgba(109,31,158,0.06)',
                    }}
                  >
                    Reply
                  </button>
                  <button
                    onClick={() => handleResolve(esc.user_id)}
                    disabled={resolving === esc.user_id}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg text-white disabled:opacity-50"
                    style={{
                      background: 'linear-gradient(135deg, #16a34a, #15803d)',
                    }}
                  >
                    {resolving === esc.user_id ? 'Resolving...' : 'Resolve'}
                  </button>
                </div>
              </div>

              {replyTo === esc.user_id && (
                <div className="mt-4 flex gap-2">
                  <input
                    value={replyMsg}
                    onChange={(e) => setReplyMsg(e.target.value)}
                    placeholder="Type your reply..."
                    className="flex-1 px-4 py-2 text-sm rounded-xl outline-none"
                    style={{
                      border: '1px solid rgba(0,0,0,0.12)',
                      background: '#fff',
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleReply(esc.user_id);
                      }
                    }}
                  />
                  <button
                    onClick={() => handleReply(esc.user_id)}
                    className="px-4 py-2 text-sm font-medium rounded-xl text-white"
                    style={{
                      background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                    }}
                  >
                    Send
                  </button>
                </div>
              )}
            </GlassPanel>
          ))}
        </div>
      )}
    </div>
  );
}
