'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

interface OnboardingStatus {
  completed_steps: string[];
  completed: boolean;
}

export default function OnboardingDonePage() {
  const router = useRouter();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);

  useEffect(() => {
    // Mark onboarding complete
    fetch('/api/v1/onboarding/complete', {
      method: 'POST',
      credentials: 'include',
    }).then(() => {
      return fetch('/api/v1/onboarding/status', { credentials: 'include' });
    }).then(r => r.json()).then(setStatus).catch(() => {});
  }, []);

  const steps = [
    { key: 'assistant', label: 'AI Assistant configured' },
    { key: 'whatsapp', label: 'WhatsApp webhook connected' },
    { key: 'calendar', label: 'Google Calendar integration' },
    { key: 'branding', label: 'Brand customization applied' },
  ];

  return (
    <div className="animate-fade-up text-center max-w-lg mx-auto">
      <div className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6"
        style={{
          background: 'linear-gradient(135deg, #16a34a, #15803d)',
          boxShadow: '0 8px 32px rgba(22,163,74,0.3)',
        }}>
        <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
          <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
        </svg>
      </div>

      <h2 className="text-3xl font-extrabold mb-3" style={{ color: 'var(--text)' }}>
        You&apos;re All Set!
      </h2>
      <p className="text-sm mb-10" style={{ color: 'var(--text-dim)' }}>
        Your AI workspace is ready. Here&apos;s what was configured:
      </p>

      <div className="space-y-3 text-left mb-10">
        {steps.map(step => {
          const done = status?.completed_steps?.includes(step.key);
          return (
            <div key={step.key} className="flex items-center gap-3 px-4 py-3 rounded-xl"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)' }}>
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
                style={{
                  background: done
                    ? 'linear-gradient(135deg, #16a34a, #15803d)'
                    : 'rgba(0,0,0,0.1)',
                }}>
                {done ? '✓' : '–'}
              </div>
              <span className="text-sm" style={{ color: done ? 'var(--text)' : 'var(--text-dim)' }}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      <Link href="/dashboard"
        className="inline-block px-10 py-3.5 text-sm font-bold rounded-xl text-white transition-transform hover:-translate-y-0.5"
        style={{
          background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
          boxShadow: '0 4px 24px rgba(176,9,9,0.4)',
        }}>
        Go to Dashboard →
      </Link>
    </div>
  );
}
