'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

type Sentiment = 'positive' | 'neutral' | 'negative';

interface Message {
  timestamp: string;
  direction: 'inbound' | 'outbound';
  phone: string;
  message: string;
  sentiment?: Sentiment;
}

interface UserEntry {
  phone: string;
  last_seen: string;
  last_message: string;
  escalation_status: 'bot' | 'escalated' | 'resolved';
}

interface DashboardData {
  conversations: Record<string, Message[]>;
  users: UserEntry[];
}

interface ChartData {
  labels: string[];
  inbound: number[];
  outbound: number[];
  escalated_count: number;
}

/* ── Stat Card ──────────────────────────────────────────────────── */
type CardColor = 'red' | 'crimson' | 'redviolet' | 'violet' | 'amber';

const COLOR_MAP: Record<
  CardColor,
  {
    bg: string;
    border: string;
    shadow: string;
    iconBg: string;
    iconBorder: string;
    numColor: string;
  }
> = {
  red: {
    bg: '#fff5f5',
    border: 'rgba(176,9,9,0.14)',
    shadow: '0 2px 16px rgba(176,9,9,0.08)',
    iconBg: 'linear-gradient(135deg, rgba(176,9,9,0.14), rgba(176,9,9,0.07))',
    iconBorder: 'rgba(176,9,9,0.18)',
    numColor: '#b00909',
  },
  crimson: {
    bg: '#fdf2f7',
    border: 'rgba(156,16,66,0.14)',
    shadow: '0 2px 16px rgba(156,16,66,0.08)',
    iconBg:
      'linear-gradient(135deg, rgba(156,16,66,0.14), rgba(156,16,66,0.07))',
    iconBorder: 'rgba(156,16,66,0.18)',
    numColor: '#9c1042',
  },
  redviolet: {
    bg: '#fdf0f9',
    border: 'rgba(137,21,101,0.14)',
    shadow: '0 2px 16px rgba(137,21,101,0.08)',
    iconBg:
      'linear-gradient(135deg, rgba(137,21,101,0.14), rgba(137,21,101,0.07))',
    iconBorder: 'rgba(137,21,101,0.18)',
    numColor: '#891565',
  },
  violet: {
    bg: '#f6f0ff',
    border: 'rgba(109,31,158,0.14)',
    shadow: '0 2px 16px rgba(109,31,158,0.08)',
    iconBg:
      'linear-gradient(135deg, rgba(109,31,158,0.14), rgba(109,31,158,0.07))',
    iconBorder: 'rgba(109,31,158,0.18)',
    numColor: '#6d1f9e',
  },
  amber: {
    bg: '#fffbeb',
    border: 'rgba(217,119,6,0.16)',
    shadow: '0 2px 16px rgba(217,119,6,0.08)',
    iconBg:
      'linear-gradient(135deg, rgba(217,119,6,0.16), rgba(217,119,6,0.07))',
    iconBorder: 'rgba(217,119,6,0.22)',
    numColor: '#d97706',
  },
};

function StatCard({
  value,
  label,
  icon,
  color = 'red',
}: {
  value: number | string;
  label: string;
  icon: React.ReactNode;
  color?: CardColor;
}) {
  const c = COLOR_MAP[color];
  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-4"
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        boxShadow: c.shadow,
        minHeight: '130px',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div
          className="text-4xl font-bold leading-none tracking-tight"
          style={{ color: c.numColor }}
        >
          {value}
        </div>
        <div
          className="p-2.5 rounded-xl shrink-0"
          style={{ background: c.iconBg, border: `1px solid ${c.iconBorder}` }}
        >
          {icon}
        </div>
      </div>
      <div
        className="text-sm font-medium"
        style={{ color: 'var(--text-muted)' }}
      >
        {label}
      </div>
    </div>
  );
}

/* ── Bar Chart ──────────────────────────────────────────────────── */
function BarChart({
  data,
  error,
  loading,
}: {
  data: ChartData | null;
  error?: boolean;
  loading?: boolean;
}) {
  if (error)
    return (
      <div
        className="flex items-center justify-center h-32 text-sm"
        role="alert"
        style={{ color: '#b00909' }}
      >
        Failed to load chart data
      </div>
    );

  if (loading || !data)
    return (
      <div
        className="flex items-center justify-center h-32 text-sm"
        style={{ color: 'var(--text-dim)' }}
      >
        Loading…
      </div>
    );

  const { labels, inbound, outbound } = data;
  if (labels.length === 0)
    return (
      <div
        className="flex items-center justify-center h-32 text-sm"
        style={{ color: 'var(--text-dim)' }}
      >
        No data yet
      </div>
    );

  const maxVal = Math.max(...inbound, ...outbound, 1);
  const barW = 10;
  const groupW = barW * 2 + 6 + 12;
  const W = labels.length * groupW + 40;
  const H = 140;
  const padB = 24;
  const padT = 10;
  const chartH = H - padB - padT;

  return (
    <div className="w-full">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: `${Math.min(W, 240)}px` }}
        >
          <defs>
            <linearGradient id="gradIn" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#b00909" />
              <stop offset="100%" stopColor="#dc2626" stopOpacity="0.6" />
            </linearGradient>
            <linearGradient id="gradOut" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#891565" />
              <stop offset="100%" stopColor="#6d1f9e" stopOpacity="0.6" />
            </linearGradient>
          </defs>

          {[0, 0.5, 1].map((ratio) => (
            <line
              key={ratio}
              x1="20"
              x2={W - 10}
              y1={padT + chartH * (1 - ratio)}
              y2={padT + chartH * (1 - ratio)}
              stroke="rgba(0,0,0,0.06)"
              strokeWidth="1"
            />
          ))}

          {labels.map((label, i) => {
            const x = 20 + i * groupW;
            const inH = Math.max(
              (inbound[i] / maxVal) * chartH,
              inbound[i] > 0 ? 3 : 0,
            );
            const outH = Math.max(
              (outbound[i] / maxVal) * chartH,
              outbound[i] > 0 ? 3 : 0,
            );
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={padT + chartH - inH}
                  width={barW}
                  height={inH}
                  fill="url(#gradIn)"
                  rx="3"
                />
                <rect
                  x={x + barW + 2}
                  y={padT + chartH - outH}
                  width={barW}
                  height={outH}
                  fill="url(#gradOut)"
                  rx="3"
                />
                <text
                  x={x + barW + 1}
                  y={H - 6}
                  textAnchor="middle"
                  fontSize="7"
                  fill="#9ca3af"
                >
                  {label.length > 4 ? label.slice(0, 3) : label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex gap-4 justify-end mt-2">
        {[
          { label: 'Inbound', color: '#b00909' },
          { label: 'Outbound', color: '#891565' },
        ].map(({ label, color }) => (
          <span
            key={label}
            className="flex items-center gap-1.5 text-xs"
            style={{ color: 'var(--text-muted)' }}
          >
            <span
              className="inline-block w-3 h-2 rounded-sm"
              style={{ background: color }}
            />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── Sentiment dot ──────────────────────────────────────────────── */
const SENTIMENT_COLOR: Record<Sentiment, string> = {
  positive: '#16a34a',
  neutral: '#9ca3af',
  negative: '#dc2626',
};
const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: 'Positive',
  neutral: 'Neutral',
  negative: 'Negative',
};

function SentimentDot({ sentiment }: { sentiment?: Sentiment }) {
  if (!sentiment) return null;
  const color = SENTIMENT_COLOR[sentiment];
  return (
    <span
      title={SENTIMENT_LABEL[sentiment]}
      className="inline-block w-2 h-2 rounded-full shrink-0"
      style={{ background: color, boxShadow: `0 0 4px ${color}60` }}
    />
  );
}

/* ── Icons ──────────────────────────────────────────────────────── */
function IconUsers({ color }: { color: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
    >
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
function IconInbound({ color }: { color: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
    >
      <polyline points="8 17 12 21 16 17" />
      <line x1="12" y1="12" x2="12" y2="21" />
      <path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29" />
    </svg>
  );
}
function IconOutbound({ color }: { color: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
    >
      <polyline points="16 7 12 3 8 7" />
      <line x1="12" y1="3" x2="12" y2="15" />
      <path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29" />
    </svg>
  );
}
function IconMsg({ color }: { color: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}
function IconEscalate({ color }: { color: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
    >
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

/* ── Panel base style ───────────────────────────────────────────── */
const panel: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(0,0,0,0.07)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04)',
};

/* ── Last inbound sentiment for a conversation ──────────────────── */
function lastInboundSentiment(msgs: Message[]): Sentiment | undefined {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].direction === 'inbound' && msgs[i].sentiment) {
      return msgs[i].sentiment as Sentiment;
    }
  }
  return undefined;
}

/* ── Dashboard Page ─────────────────────────────────────────────── */
export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [chartData, setChartData] = useState<ChartData | null>(null);
  const [chartError, setChartError] = useState(false);
  const [chartLoading, setChartLoading] = useState(true);
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);
  const [botMsg, setBotMsg] = useState('');
  const [userMsg, setUserMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [resolvingPhone, setResolvingPhone] = useState<string | null>(null);
  const [resolveError, setResolveError] = useState('');
  const msgListRef = useRef<HTMLDivElement>(null);

  const dashboardEtag = useRef<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const headers: HeadersInit = {};
      if (dashboardEtag.current)
        headers['If-None-Match'] = dashboardEtag.current;
      const res = await fetch('/api/dashboard', {
        credentials: 'include',
        headers,
      });
      if (res.status === 304) return;
      if (!res.ok) return;
      const etag = res.headers.get('ETag');
      if (etag) dashboardEtag.current = etag;
      setData(await res.json());
    } catch {
      /* silent */
    }
  }, []);

  const fetchChart = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard/data', {
        credentials: 'include',
      });
      if (!res.ok) {
        setChartError(true);
        return;
      }
      setChartData(await res.json());
      setChartError(false);
    } catch {
      setChartError(true);
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    fetchChart();

    const tick = () => {
      // Skip polling when the tab is in the background — saves network/battery.
      if (document.visibilityState === 'hidden') return;
      fetchDashboard();
      fetchChart();
    };

    const id = setInterval(tick, 5000);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [fetchDashboard, fetchChart]);

  useEffect(() => {
    if (msgListRef.current)
      msgListRef.current.scrollTop = msgListRef.current.scrollHeight;
  }, [selectedPhone, data]);

  async function respond(mode: 'user_to_bot' | 'bot_to_user') {
    if (!selectedPhone) return;
    const message = mode === 'bot_to_user' ? botMsg : userMsg;
    if (!message.trim()) return;
    setSending(true);
    setSendError('');
    try {
      const res = await fetch('/api/admin/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ user_number: selectedPhone, message, mode }),
      });
      if (!res.ok) throw new Error(await res.text());
      if (mode === 'bot_to_user') setBotMsg('');
      else setUserMsg('');
      await fetchDashboard();
    } catch (e: unknown) {
      setSendError(e instanceof Error ? e.message : 'Error sending');
    } finally {
      setSending(false);
    }
  }

  async function resolveEscalation(phone: string) {
    setResolvingPhone(phone);
    setResolveError('');
    try {
      const encoded = encodeURIComponent(phone);
      const res = await fetch(`/api/admin/escalations/${encoded}/resolve`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`Failed to resolve: ${res.status}`);
      await Promise.all([fetchDashboard(), fetchChart()]);
    } catch (e: unknown) {
      setResolveError(
        e instanceof Error ? e.message : 'Could not resolve escalation',
      );
    } finally {
      setResolvingPhone(null);
    }
  }

  const conversations = data?.conversations ?? {};
  const users = data?.users ?? [];
  const selected = selectedPhone ? (conversations[selectedPhone] ?? []) : [];
  const allMsgs = Object.values(conversations).flat();
  const totalInbound = allMsgs.filter((m) => m.direction === 'inbound').length;
  const totalOutbound = allMsgs.filter(
    (m) => m.direction === 'outbound',
  ).length;
  const escalatedUsers = users.filter(
    (u) => u.escalation_status === 'escalated',
  );
  const escalatedCount = chartData?.escalated_count ?? escalatedUsers.length;
  const displayPhone = (p: string) => p.replace('whatsapp:', '').trim();
  const today = new Date().toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>
            Dashboard
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-dim)' }}>
            {today}
          </p>
        </div>
        <div
          className="flex items-center gap-2 text-xs"
          style={{ color: 'var(--text-dim)' }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full inline-block"
            style={{ background: '#16a34a', boxShadow: '0 0 4px #16a34a' }}
          />
          Live · every 5s
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          value={users.length}
          label="Total Users"
          icon={<IconUsers color="#b00909" />}
          color="red"
        />
        <StatCard
          value={totalInbound}
          label="Inbound Messages"
          icon={<IconInbound color="#9c1042" />}
          color="crimson"
        />
        <StatCard
          value={totalOutbound}
          label="Outbound Messages"
          icon={<IconOutbound color="#891565" />}
          color="redviolet"
        />
        <StatCard
          value={allMsgs.length}
          label="Total Messages"
          icon={<IconMsg color="#6d1f9e" />}
          color="violet"
        />
        <StatCard
          value={escalatedCount}
          label="Needs Human"
          icon={<IconEscalate color="#d97706" />}
          color="amber"
        />
      </div>

      {/* Table + Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Conversations table */}
        <div
          className="lg:col-span-3 rounded-2xl overflow-hidden"
          style={panel}
        >
          <div className="px-5 pt-5 pb-3 flex items-center justify-between">
            <h2 className="font-semibold" style={{ color: 'var(--text)' }}>
              Recent Conversations
            </h2>
            <span
              className="text-xs px-2.5 py-1 rounded-full font-semibold"
              style={{
                background: 'rgba(176,9,9,0.08)',
                border: '1px solid rgba(176,9,9,0.18)',
                color: '#b00909',
              }}
            >
              {users.length} users
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}>
                  {['Phone', 'Last Message', 'Last Seen', 'Msgs', 'Mood'].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-5 py-2.5 text-xs font-bold uppercase tracking-wider"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {users.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="text-center px-5 py-12 text-sm"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      No conversations yet
                    </td>
                  </tr>
                )}
                {users.map((u) => {
                  const msgs = conversations[u.phone] ?? [];
                  const isActive = selectedPhone === u.phone;
                  const isEscalated = u.escalation_status === 'escalated';
                  const sentiment = lastInboundSentiment(msgs);
                  return (
                    <tr
                      key={u.phone}
                      onClick={() =>
                        setSelectedPhone(isActive ? null : u.phone)
                      }
                      className="cursor-pointer transition-all duration-150"
                      style={{
                        borderBottom: '1px solid rgba(0,0,0,0.05)',
                        background: isActive
                          ? isEscalated
                            ? '#fffbeb'
                            : '#fff5f5'
                          : 'transparent',
                        boxShadow: isActive
                          ? `inset 3px 0 0 ${isEscalated ? '#d97706' : '#b00909'}`
                          : 'none',
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive)
                          e.currentTarget.style.background = '#fafafa';
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive)
                          e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      <td
                        className="px-5 py-3 whitespace-nowrap"
                        style={{ color: 'var(--text)' }}
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">
                            {displayPhone(u.phone)}
                          </span>
                          {isEscalated && (
                            <span
                              className="text-xs px-1.5 py-0.5 rounded-md font-semibold"
                              style={{
                                background: 'rgba(217,119,6,0.12)',
                                border: '1px solid rgba(217,119,6,0.25)',
                                color: '#d97706',
                              }}
                            >
                              Escalated
                            </span>
                          )}
                        </div>
                      </td>
                      <td
                        className="px-5 py-3 max-w-40 truncate"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {u.last_message}
                      </td>
                      <td
                        className="px-5 py-3 text-xs whitespace-nowrap"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {u.last_seen}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className="px-2 py-0.5 rounded-full text-xs font-bold"
                          style={{
                            background: 'rgba(176,9,9,0.08)',
                            border: '1px solid rgba(176,9,9,0.18)',
                            color: '#b00909',
                          }}
                        >
                          {msgs.length}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <SentimentDot sentiment={sentiment} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Chart */}
        <div className="lg:col-span-2 rounded-2xl p-5" style={panel}>
          <h2 className="font-semibold mb-5" style={{ color: 'var(--text)' }}>
            Message Activity
          </h2>
          <BarChart
            data={chartData}
            error={chartError}
            loading={chartLoading}
          />
        </div>
      </div>

      {/* Escalated conversations panel */}
      {escalatedUsers.length > 0 && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            ...panel,
            border: '1px solid rgba(217,119,6,0.22)',
            boxShadow:
              '0 1px 3px rgba(217,119,6,0.06), 0 4px 16px rgba(217,119,6,0.08)',
          }}
        >
          <div
            className="px-5 py-4 flex items-center gap-3"
            style={{
              borderBottom: '1px solid rgba(217,119,6,0.15)',
              background: 'rgba(255,251,235,0.6)',
            }}
          >
            <IconEscalate color="#d97706" />
            <h2 className="font-semibold" style={{ color: '#92400e' }}>
              Escalated Conversations
            </h2>
            <span
              className="ml-auto text-xs px-2.5 py-1 rounded-full font-bold"
              style={{
                background: 'rgba(217,119,6,0.14)',
                border: '1px solid rgba(217,119,6,0.28)',
                color: '#d97706',
              }}
            >
              {escalatedUsers.length} waiting
            </span>
          </div>

          {resolveError && (
            <div
              className="px-5 py-2.5 text-sm"
              role="alert"
              style={{
                background: 'rgba(220,38,38,0.06)',
                borderBottom: '1px solid rgba(220,38,38,0.14)',
                color: '#dc2626',
              }}
            >
              {resolveError}
            </div>
          )}

          <div
            className="divide-y"
            style={{ borderColor: 'rgba(217,119,6,0.10)' }}
          >
            {escalatedUsers.map((u) => {
              const msgs = conversations[u.phone] ?? [];
              const sentiment = lastInboundSentiment(msgs);
              const isResolving = resolvingPhone === u.phone;
              return (
                <div
                  key={u.phone}
                  className="px-5 py-4 flex items-center gap-4"
                  style={{ background: '#fffdf5' }}
                >
                  {/* Avatar */}
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
                    style={{
                      background: 'linear-gradient(135deg, #d97706, #b45309)',
                    }}
                  >
                    {displayPhone(u.phone).slice(-2)}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="font-semibold text-sm"
                        style={{ color: 'var(--text)' }}
                      >
                        {displayPhone(u.phone)}
                      </span>
                      <SentimentDot sentiment={sentiment} />
                    </div>
                    <p
                      className="text-xs mt-0.5 truncate"
                      style={{ color: 'var(--text-muted)', maxWidth: '320px' }}
                    >
                      {u.last_message}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() =>
                        setSelectedPhone(
                          selectedPhone === u.phone ? null : u.phone,
                        )
                      }
                      className="px-3 py-1.5 text-xs rounded-lg font-medium transition-all duration-150"
                      style={{
                        background: 'rgba(217,119,6,0.08)',
                        border: '1px solid rgba(217,119,6,0.22)',
                        color: '#d97706',
                      }}
                    >
                      View
                    </button>
                    <button
                      onClick={() => resolveEscalation(u.phone)}
                      disabled={isResolving}
                      className="px-3 py-1.5 text-xs rounded-lg font-semibold transition-all duration-150 disabled:opacity-50"
                      style={{
                        background: 'rgba(22,163,74,0.10)',
                        border: '1px solid rgba(22,163,74,0.25)',
                        color: '#16a34a',
                      }}
                    >
                      {isResolving ? 'Resolving…' : 'Resolve → Bot'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Chat panel */}
      {selectedPhone && (
        <div
          className="rounded-2xl overflow-hidden"
          style={panel}
          role="dialog"
          aria-label={`Conversation with ${displayPhone(selectedPhone)}`}
          aria-modal="false"
        >
          {/* Chat header */}
          <div
            className="px-5 py-4 flex items-center justify-between"
            style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white shrink-0"
                style={{
                  background:
                    'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                  boxShadow: '0 2px 10px rgba(176,9,9,0.35)',
                }}
              >
                {displayPhone(selectedPhone).slice(-2)}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className="font-semibold text-sm"
                    style={{ color: 'var(--text)' }}
                  >
                    {displayPhone(selectedPhone)}
                  </span>
                  {users.find((u) => u.phone === selectedPhone)
                    ?.escalation_status === 'escalated' && (
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-md font-semibold"
                      style={{
                        background: 'rgba(217,119,6,0.12)',
                        border: '1px solid rgba(217,119,6,0.25)',
                        color: '#d97706',
                      }}
                    >
                      Escalated
                    </span>
                  )}
                </div>
                <div className="text-xs" style={{ color: 'var(--text-dim)' }}>
                  {selected.length} messages
                </div>
              </div>
            </div>
            <button
              onClick={() => setSelectedPhone(null)}
              aria-label="Close conversation panel"
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: 'var(--text-dim)' }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLButtonElement).style.color =
                  'var(--text)')
              }
              onMouseLeave={(e) =>
                ((e.currentTarget as HTMLButtonElement).style.color =
                  'var(--text-dim)')
              }
            >
              <svg
                width="16"
                height="16"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Messages */}
          <div
            ref={msgListRef}
            className="h-64 overflow-y-auto px-5 py-4 space-y-2.5"
            style={{ background: '#fafafa' }}
          >
            {selected.map((msg, i) => (
              <div
                key={`${msg.timestamp}-${msg.direction}-${i}`}
                className={`flex ${msg.direction === 'inbound' ? 'justify-start' : 'justify-end'}`}
              >
                <div
                  className="max-w-sm px-4 py-2.5 text-sm whitespace-pre-wrap"
                  style={
                    msg.direction === 'inbound'
                      ? {
                          background: '#ffffff',
                          border: '1px solid rgba(0,0,0,0.08)',
                          borderRadius: '16px 16px 16px 4px',
                          color: 'var(--text)',
                        }
                      : {
                          background: '#fff5f5',
                          border: '1px solid rgba(176,9,9,0.18)',
                          borderRadius: '16px 16px 4px 16px',
                          color: 'var(--text)',
                        }
                  }
                >
                  {msg.message}
                  <div className="flex items-center justify-between gap-3 mt-1.5">
                    <span
                      className="text-xs"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {msg.timestamp}
                    </span>
                    {msg.direction === 'inbound' && msg.sentiment && (
                      <SentimentDot sentiment={msg.sentiment as Sentiment} />
                    )}
                  </div>
                </div>
              </div>
            ))}
            {selected.length === 0 && (
              <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
                No messages yet.
              </p>
            )}
          </div>

          {/* Compose */}
          <div
            className="px-5 py-4 space-y-3"
            style={{ borderTop: '1px solid rgba(0,0,0,0.07)' }}
          >
            {sendError && (
              <p className="text-sm" role="alert" style={{ color: '#b00909' }}>
                {sendError}
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  label: 'Simulate user → bot',
                  value: userMsg,
                  set: setUserMsg,
                  mode: 'user_to_bot' as const,
                  accent: '#b00909',
                  accentBg: 'rgba(176,9,9,0.08)',
                  accentBorder: 'rgba(176,9,9,0.22)',
                },
                {
                  label: 'Bot → user (direct)',
                  value: botMsg,
                  set: setBotMsg,
                  mode: 'bot_to_user' as const,
                  accent: '#16a34a',
                  accentBg: 'rgba(22,163,74,0.08)',
                  accentBorder: 'rgba(22,163,74,0.22)',
                },
              ].map(
                ({
                  label,
                  value,
                  set,
                  mode,
                  accent,
                  accentBg,
                  accentBorder,
                }) => (
                  <div key={mode}>
                    <p
                      className="text-xs mb-1.5 font-semibold"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {label}
                    </p>
                    <div className="flex gap-2">
                      <input
                        value={value}
                        onChange={(e) => set(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && respond(mode)}
                        placeholder="Type a message…"
                        className="flex-1 px-3 py-2 text-sm rounded-xl outline-none transition-all duration-200"
                        style={{
                          background: '#ffffff',
                          border: '1px solid rgba(0,0,0,0.10)',
                          color: 'var(--text)',
                        }}
                        onFocus={(e) => {
                          e.currentTarget.style.borderColor = accent;
                          e.currentTarget.style.boxShadow = `0 0 0 3px ${accentBg}`;
                        }}
                        onBlur={(e) => {
                          e.currentTarget.style.borderColor =
                            'rgba(0,0,0,0.10)';
                          e.currentTarget.style.boxShadow = 'none';
                        }}
                      />
                      <button
                        onClick={() => respond(mode)}
                        disabled={sending}
                        className="px-4 py-2 text-sm rounded-xl font-semibold transition-all duration-200 disabled:opacity-40"
                        style={{
                          background: accentBg,
                          border: `1px solid ${accentBorder}`,
                          color: accent,
                        }}
                        onMouseEnter={(e) => {
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.background = accentBorder;
                        }}
                        onMouseLeave={(e) => {
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.background = accentBg;
                        }}
                      >
                        Send
                      </button>
                    </div>
                  </div>
                ),
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
