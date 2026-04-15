'use client';

import { useEffect, useRef, useState } from 'react';

interface Template {
  label: string;
  value: string;
}

interface BulkRow {
  to: string;
  param1: string;
  param2: string;
  selected: boolean;
}

interface ProgressLog {
  to: string;
  result: string;
  reason?: string;
}

interface BulkLimits {
  max_batch: number;
  daily_cap: number;
  daily_sent: number;
  daily_remaining: number;
  msg_delay_s: number;
}

/* ── Shared styles ───────────────────────────────────────────────── */
const panel: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(0,0,0,0.07)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04)',
};

const inputBaseStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(0,0,0,0.12)',
  color: 'var(--text)',
};

function onFocusRed(e: React.FocusEvent<HTMLElement>) {
  (e.currentTarget as HTMLElement).style.borderColor = '#b00909';
  (e.currentTarget as HTMLElement).style.boxShadow =
    '0 0 0 3px rgba(176,9,9,0.10)';
}
function onBlurRed(e: React.FocusEvent<HTMLElement>) {
  (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,0,0,0.12)';
  (e.currentTarget as HTMLElement).style.boxShadow = 'none';
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="text-xs font-bold uppercase tracking-widest mb-4"
      style={{ color: 'var(--text-dim)' }}
    >
      {children}
    </h2>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label
      className="block text-xs font-semibold mb-1.5"
      style={{ color: 'var(--text-dim)' }}
    >
      {children}
    </label>
  );
}

function StyledInput({
  value,
  onChange,
  placeholder,
  required,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      required={required}
      className="w-full px-4 py-2.5 text-sm rounded-xl outline-none transition-all duration-200"
      style={inputBaseStyle}
      onFocus={onFocusRed}
      onBlur={onBlurRed}
    />
  );
}

function AccentButton({
  onClick,
  disabled,
  children,
  type = 'button',
}: {
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
  type?: 'button' | 'submit';
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="px-5 py-2.5 text-sm font-bold rounded-xl text-white transition-all duration-200 disabled:opacity-40"
      style={{
        background:
          'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
        boxShadow: '0 3px 16px rgba(176,9,9,0.30)',
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          const el = e.currentTarget as HTMLButtonElement;
          el.style.transform = 'translateY(-1px)';
          el.style.boxShadow = '0 6px 24px rgba(176,9,9,0.45)';
        }
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLButtonElement;
        el.style.transform = 'translateY(0)';
        el.style.boxShadow = '0 3px 16px rgba(176,9,9,0.30)';
      }}
    >
      {children}
    </button>
  );
}

/* ── Page ────────────────────────────────────────────────────────── */
export default function SendTemplatePage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateSid, setTemplateSid] = useState('');
  const [userNumber, setUserNumber] = useState('');
  const [param1, setParam1] = useState('');
  const [param2, setParam2] = useState('');
  const [singleSending, setSingleSending] = useState(false);
  const [singleMsg, setSingleMsg] = useState('');
  const [singleError, setSingleError] = useState('');

  const [rows, setRows] = useState<BulkRow[]>([]);
  const [parseError, setParseError] = useState('');
  const [bulkSending, setBulkSending] = useState(false);
  const [bulkTaskId, setBulkTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState('');
  const [logs, setLogs] = useState<ProgressLog[]>([]);
  const [limits, setLimits] = useState<BulkLimits | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/api/get_templates', { credentials: 'include' })
      .then((r) => r.json())
      .then((d: Template[]) => setTemplates(d))
      .catch(() => setTemplates([]));

    fetch('/api/bulk_limits', { credentials: 'include' })
      .then((r) => r.json())
      .then((d: BulkLimits) => setLimits(d))
      .catch(() => {
        /* limits panel stays hidden on error */
      });
  }, []);

  const E164_RE = /^\+?[1-9]\d{6,14}$/;

  async function sendSingle(e: React.FormEvent) {
    e.preventDefault();
    if (!templateSid || !userNumber) return;
    const normalised = userNumber.replace(/[\s\-().]/g, '');
    if (!E164_RE.test(normalised)) {
      setSingleError(
        'Phone number must be in international format, e.g. +97412345678',
      );
      return;
    }
    setSingleSending(true);
    setSingleMsg('');
    setSingleError('');
    try {
      const res = await fetch('/api/send_template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          template_sid: templateSid,
          user_number: userNumber,
          param1,
          param2,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.message || 'Failed');
      }
      setSingleMsg(`Queued for ${userNumber}`);
      setUserNumber('');
      setParam1('');
      setParam2('');
    } catch (err: unknown) {
      setSingleError(
        err instanceof Error ? err.message : 'Error sending template',
      );
    } finally {
      setSingleSending(false);
    }
  }

  /** RFC-4180 compliant CSV line parser — handles quoted fields containing commas. */
  function parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        if (inQuotes && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  }

  function parseCSV() {
    setParseError('');
    setRows([]);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setParseError('Please select a CSV file.');
      return;
    }
    const MAX_SIZE_MB = 5;
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setParseError(
        `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum allowed size is ${MAX_SIZE_MB} MB.`,
      );
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => {
      setParseError('Failed to read file. Please try again.');
    };
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.split('\n').filter((l) => l.trim());
      if (lines.length < 2) {
        setParseError('CSV has no data rows.');
        return;
      }
      // Auto-detect header: skip first row if its first column doesn't look like a phone number
      const looksLikePhone = (s: string) =>
        /^\+?\d[\d\s\-().]{6,}$/.test(s.trim());
      const dataLines = looksLikePhone(parseCSVLine(lines[0])[0])
        ? lines
        : lines.slice(1);

      // Read by position: col 0 = number, col 1 = param1, col 2 = param2
      const parsed: BulkRow[] = dataLines
        .map((line) => {
          const cols = parseCSVLine(line);
          return {
            to: cols[0] ?? '',
            param1: cols[1] ?? '',
            param2: cols[2] ?? '',
            selected: true,
          };
        })
        .filter((r) => r.to);
      if (!parsed.length) {
        setParseError('No valid rows found.');
        return;
      }
      setRows(parsed);
    };
    reader.readAsText(file);
  }

  function toggleRow(i: number) {
    setRows((prev) =>
      prev.map((r, idx) => (idx === i ? { ...r, selected: !r.selected } : r)),
    );
  }
  function toggleAll(checked: boolean) {
    setRows((prev) => prev.map((r) => ({ ...r, selected: checked })));
  }

  async function submitBulk() {
    const payload = rows
      .filter((r) => r.selected)
      .map(({ to, param1, param2 }) => ({ to, param1, param2 }));
    if (!payload.length) {
      setParseError('No rows selected.');
      return;
    }
    if (!templateSid) {
      setParseError('Please select a template first.');
      return;
    }
    // Client-side guard matching backend BULK_MAX_BATCH default.
    // The real enforcement happens on the server; this is just fast feedback.
    if (limits && payload.length > limits.max_batch) {
      setParseError(
        `Too many recipients selected (${payload.length}). ` +
          `Maximum per job is ${limits.max_batch} (Meta/Twilio compliance). ` +
          `Deselect some rows and try again.`,
      );
      return;
    }
    setBulkSending(true);
    setLogs([]);
    setProgress('');
    try {
      const res = await fetch('/api/start_bulk_send', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload, template_sid: templateSid }),
      });
      const d = await res.json();
      if (!res.ok) {
        throw new Error(d.error || 'Failed to start bulk send');
      }
      setBulkTaskId(d.task_id);
      // Refresh limits after starting a job so the banner stays accurate.
      fetch('/api/bulk_limits', { credentials: 'include' })
        .then((r) => r.json())
        .then((d: BulkLimits) => setLimits(d))
        .catch(() => {});
    } catch (err: unknown) {
      setParseError(
        err instanceof Error ? err.message : 'Error starting bulk send',
      );
      setBulkSending(false);
    }
  }

  useEffect(() => {
    if (!bulkTaskId) return;
    let consecutive_errors = 0;
    const MAX_ERRORS = 5;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/progress/${bulkTaskId}`, {
          credentials: 'include',
        });
        if (!res.ok) throw new Error('bad response');
        const d = await res.json();
        consecutive_errors = 0;
        setProgress(d.progress ?? '');
        setLogs(d.logs ?? []);

        // Check explicit status flag first, then fall back to progress string comparison.
        const isDone =
          d.status === 'done' ||
          d.status === 'complete' ||
          (() => {
            const progressStr =
              typeof d.progress === 'string' ? d.progress : '';
            const parts = progressStr.split('/');
            if (parts.length !== 2) return false;
            const done = Number(parts[0]);
            const total = Number(parts[1]);
            return !isNaN(done) && !isNaN(total) && total > 0 && done >= total;
          })();

        if (isDone) {
          clearInterval(interval);
          setBulkSending(false);
        }
      } catch {
        consecutive_errors += 1;
        if (consecutive_errors >= MAX_ERRORS) {
          // Stop polling after repeated failures so the spinner doesn't run forever.
          clearInterval(interval);
          setBulkSending(false);
          setParseError(
            'Lost connection while tracking progress. Check results manually.',
          );
        }
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [bulkTaskId]);

  const selectedCount = rows.filter((r) => r.selected).length;

  return (
    <div className="max-w-3xl space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>
          Send Template
        </h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-dim)' }}>
          Send WhatsApp message templates to users
        </p>
      </div>

      {/* Template selector */}
      <div className="rounded-2xl p-6" style={panel}>
        <SectionHeading>Template</SectionHeading>
        <select
          value={templateSid}
          onChange={(e) => setTemplateSid(e.target.value)}
          className="w-full px-4 py-2.5 text-sm rounded-xl outline-none transition-all duration-200 appearance-none"
          style={{
            ...inputBaseStyle,
            color: templateSid ? 'var(--text)' : 'var(--text-dim)',
          }}
          onFocus={onFocusRed}
          onBlur={onBlurRed}
        >
          <option value="">Select a template…</option>
          {templates.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {/* Single send */}
      <div className="rounded-2xl p-6" style={panel}>
        <SectionHeading>Single Send</SectionHeading>
        <form onSubmit={sendSingle} className="space-y-4">
          <div>
            <FieldLabel>User Number</FieldLabel>
            <StyledInput
              value={userNumber}
              onChange={setUserNumber}
              placeholder="+974…"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel>First Name</FieldLabel>
              <StyledInput
                value={param1}
                onChange={setParam1}
                placeholder="e.g. John"
              />
            </div>
            <div>
              <FieldLabel>Last Name</FieldLabel>
              <StyledInput
                value={param2}
                onChange={setParam2}
                placeholder="e.g. Doe"
              />
            </div>
          </div>

          {singleError && (
            <p className="text-sm" role="alert" style={{ color: '#b00909' }}>
              {singleError}
            </p>
          )}
          {singleMsg && (
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
              {singleMsg}
            </p>
          )}

          <AccentButton type="submit" disabled={singleSending}>
            {singleSending ? 'Sending…' : 'Send →'}
          </AccentButton>
        </form>
      </div>

      {/* Bulk send */}
      <div className="rounded-2xl p-6" style={panel}>
        {/* ── Compliance / Limits banner ──────────────────────────────────── */}
        {limits && (
          <div
            className="mb-5 rounded-xl p-4 text-xs space-y-2"
            style={{
              background: 'rgba(217,119,6,0.05)',
              border: '1px solid rgba(217,119,6,0.22)',
            }}
          >
            <div
              className="flex items-center gap-2 font-bold"
              style={{ color: '#b45309' }}
            >
              <svg
                width="14"
                height="14"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                />
              </svg>
              Meta / Twilio Sending Limits
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                {
                  label: 'Max per job',
                  value: limits.max_batch.toLocaleString(),
                },
                {
                  label: 'Daily cap (Tier 1)',
                  value: limits.daily_cap.toLocaleString(),
                },
                {
                  label: 'Sent today',
                  value: limits.daily_sent.toLocaleString(),
                  warn: limits.daily_sent > limits.daily_cap * 0.8,
                },
                {
                  label: 'Remaining today',
                  value: limits.daily_remaining.toLocaleString(),
                  warn: limits.daily_remaining < 100,
                },
              ].map(({ label, value, warn }) => (
                <div key={label} className="flex flex-col gap-0.5">
                  <span style={{ color: 'var(--text-dim)' }}>{label}</span>
                  <span
                    className="font-bold text-sm"
                    style={{ color: warn ? '#b00909' : '#b45309' }}
                  >
                    {value}
                  </span>
                </div>
              ))}
            </div>
            <p style={{ color: '#78350f' }}>
              Meta Tier 1 allows <strong>1,000 unique recipients/day</strong>{' '}
              per phone number. Messages are spaced {limits.msg_delay_s}s apart
              to stay within Twilio&apos;s rate limit. Upgrade your WhatsApp
              Business number to Tier 2/3 to increase limits.
            </p>
          </div>
        )}

        <div className="flex items-center justify-between mb-4">
          <SectionHeading>Bulk Send via CSV</SectionHeading>
          <button
            type="button"
            onClick={() => {
              const csv =
                'number,first_name,last_name\n+97412345678,John,Doe\n+97487654321,Jane,Smith';
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'sample_bulk.csv';
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-200 shrink-0"
            style={{
              background: 'rgba(176,9,9,0.06)',
              border: '1px solid rgba(176,9,9,0.18)',
              color: '#b00909',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.background = 'rgba(176,9,9,0.12)';
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.background = 'rgba(176,9,9,0.06)';
            }}
          >
            <svg
              width="12"
              height="12"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2.5"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download sample CSV
          </button>
        </div>
        <div
          className="flex flex-wrap gap-3 mb-5 p-3 rounded-xl"
          style={{
            background: 'rgba(0,0,0,0.02)',
            border: '1px solid rgba(0,0,0,0.06)',
          }}
        >
          {[
            { col: '1st column', desc: 'Phone number (e.g. +97412345678)' },
            { col: '2nd column', desc: 'First name' },
            { col: '3rd column', desc: 'Last name' },
          ].map(({ col, desc }) => (
            <div key={col} className="flex items-center gap-2">
              <code
                className="px-1.5 py-0.5 rounded-md text-xs"
                style={{
                  background: 'rgba(176,9,9,0.07)',
                  border: '1px solid rgba(176,9,9,0.16)',
                  color: '#b00909',
                }}
              >
                {col}
              </code>
              <span className="text-xs" style={{ color: 'var(--text-dim)' }}>
                {desc}
              </span>
            </div>
          ))}
        </div>

        {/* File upload */}
        <div
          className="flex gap-3 items-center mb-5 p-4 rounded-xl"
          style={{
            border: '1px dashed rgba(176,9,9,0.28)',
            background: 'rgba(176,9,9,0.03)',
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="text-sm flex-1"
            style={{ color: 'var(--text-muted)' }}
          />
          <button
            type="button"
            onClick={parseCSV}
            className="px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200 shrink-0"
            style={{
              background: 'rgba(0,0,0,0.04)',
              border: '1px solid rgba(0,0,0,0.10)',
              color: 'var(--text-muted)',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.background = 'rgba(176,9,9,0.08)';
              el.style.color = '#b00909';
              el.style.borderColor = 'rgba(176,9,9,0.22)';
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.background = 'rgba(0,0,0,0.04)';
              el.style.color = 'var(--text-muted)';
              el.style.borderColor = 'rgba(0,0,0,0.10)';
            }}
          >
            Preview
          </button>
        </div>

        {parseError && (
          <p className="text-sm mb-4" role="alert" style={{ color: '#b00909' }}>
            {parseError}
          </p>
        )}

        {rows.length > 0 && (
          <>
            <div
              className="rounded-xl overflow-hidden mb-5"
              style={{ border: '1px solid rgba(0,0,0,0.08)' }}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      background: '#f9fafb',
                      borderBottom: '1px solid rgba(0,0,0,0.08)',
                    }}
                  >
                    <th className="px-4 py-2.5 text-left w-10">
                      <input
                        type="checkbox"
                        checked={rows.every((r) => r.selected)}
                        onChange={(e) => toggleAll(e.target.checked)}
                        className="accent-red-700"
                      />
                    </th>
                    {['Number', 'First Name', 'Last Name'].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr
                      key={i}
                      className="transition-colors"
                      style={{ borderTop: '1px solid rgba(0,0,0,0.05)' }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.background = '#fafafa')
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.background = 'transparent')
                      }
                    >
                      <td className="px-4 py-2.5">
                        <input
                          type="checkbox"
                          checked={row.selected}
                          onChange={() => toggleRow(i)}
                          className="accent-red-700"
                        />
                      </td>
                      <td
                        className="px-4 py-2.5 font-medium"
                        style={{ color: 'var(--text)' }}
                      >
                        {row.to}
                      </td>
                      <td
                        className="px-4 py-2.5"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {row.param1}
                      </td>
                      <td
                        className="px-4 py-2.5"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {row.param2}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {(() => {
              const maxBatch = limits?.max_batch ?? 500;
              const overLimit = selectedCount > maxBatch;
              const approachingLimit =
                !overLimit && selectedCount > maxBatch * 0.8;
              const approachingDailyCap =
                limits && selectedCount > limits.daily_remaining * 0.8;
              const msgDelay = limits?.msg_delay_s ?? 1.5;
              const estimatedSecs = Math.ceil(selectedCount * msgDelay);
              const estimatedMins = (estimatedSecs / 60).toFixed(1);
              return (
                <div className="space-y-3">
                  {/* Count warnings */}
                  {overLimit && (
                    <div
                      className="text-xs px-3 py-2 rounded-lg font-medium"
                      role="alert"
                      style={{
                        background: 'rgba(176,9,9,0.07)',
                        border: '1px solid rgba(176,9,9,0.22)',
                        color: '#b00909',
                      }}
                    >
                      ✕ Selection ({selectedCount}) exceeds the max per-job
                      limit of {maxBatch}. Deselect {selectedCount - maxBatch}{' '}
                      recipient{selectedCount - maxBatch !== 1 ? 's' : ''} to
                      continue.
                    </div>
                  )}
                  {approachingLimit && (
                    <div
                      className="text-xs px-3 py-2 rounded-lg"
                      style={{
                        background: 'rgba(217,119,6,0.07)',
                        border: '1px solid rgba(217,119,6,0.22)',
                        color: '#b45309',
                      }}
                    >
                      ⚠ {selectedCount} of {maxBatch} max recipients selected.
                    </div>
                  )}
                  {!overLimit && approachingDailyCap && limits && (
                    <div
                      className="text-xs px-3 py-2 rounded-lg"
                      style={{
                        background: 'rgba(217,119,6,0.07)',
                        border: '1px solid rgba(217,119,6,0.22)',
                        color: '#b45309',
                      }}
                    >
                      ⚠ Only {limits.daily_remaining} recipients remain in
                      today&apos;s daily cap.
                      {selectedCount > limits.daily_remaining
                        ? ` ${selectedCount - limits.daily_remaining} will be skipped by the server.`
                        : ''}
                    </div>
                  )}

                  {/* Stats row */}
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                    <span
                      className="text-sm"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      Selected:{' '}
                      <span
                        style={{
                          color: overLimit ? '#b00909' : '#b00909',
                          fontWeight: 700,
                        }}
                      >
                        {selectedCount}
                      </span>{' '}
                      / {rows.length}
                    </span>
                    {selectedCount > 0 && (
                      <span
                        className="text-xs"
                        style={{ color: 'var(--text-dim)' }}
                      >
                        Est. send time:{' '}
                        <span
                          style={{
                            color: 'var(--text-muted)',
                            fontWeight: 600,
                          }}
                        >
                          {estimatedSecs < 60
                            ? `~${estimatedSecs}s`
                            : `~${estimatedMins} min`}
                        </span>
                      </span>
                    )}
                    <AccentButton
                      onClick={submitBulk}
                      disabled={bulkSending || selectedCount === 0 || overLimit}
                    >
                      {bulkSending ? 'Sending…' : `Send to ${selectedCount} →`}
                    </AccentButton>
                  </div>
                </div>
              );
            })()}
          </>
        )}

        {/* Progress */}
        {(bulkSending || logs.length > 0) && (
          <div
            className="mt-6 rounded-xl p-5"
            style={{
              background: 'rgba(176,9,9,0.03)',
              border: '1px solid rgba(176,9,9,0.14)',
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <h4
                className="text-sm font-semibold"
                style={{ color: 'var(--text)' }}
              >
                Progress
              </h4>
              {progress && (
                <span
                  className="text-xs px-2.5 py-1 rounded-full font-bold"
                  style={{
                    background: 'rgba(176,9,9,0.08)',
                    border: '1px solid rgba(176,9,9,0.20)',
                    color: '#b00909',
                  }}
                >
                  {progress}
                </span>
              )}
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1.5">
              {logs.map((log, i) => {
                const resultColor =
                  log.result === 'sent' || log.result === 'queued'
                    ? '#16a34a'
                    : log.result === 'skipped'
                      ? '#b45309'
                      : log.result === 'failed' || log.result === 'rejected'
                        ? '#b00909'
                        : 'var(--text-muted)';
                return (
                  <div key={i} className="text-xs flex gap-3 items-start">
                    <span
                      className="font-mono shrink-0"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      {log.to}
                    </span>
                    <span
                      className="font-semibold shrink-0"
                      style={{ color: resultColor }}
                    >
                      {log.result}
                    </span>
                    {log.reason && (
                      <span style={{ color: 'var(--text-dim)' }}>
                        — {log.reason}
                      </span>
                    )}
                  </div>
                );
              })}
              {bulkSending && logs.length === 0 && (
                <p
                  className="text-xs flex items-center gap-2"
                  style={{ color: 'var(--text-dim)' }}
                >
                  <svg
                    className="animate-spin w-3 h-3"
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
                  Waiting for progress…
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
