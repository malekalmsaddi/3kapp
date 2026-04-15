'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';

const STEPS = [
  { key: 'assistant', label: 'AI Assistant', href: '/onboarding/assistant' },
  { key: 'whatsapp', label: 'WhatsApp', href: '/onboarding/whatsapp' },
  { key: 'calendar', label: 'Calendar', href: '/onboarding/calendar' },
  { key: 'branding', label: 'Branding', href: '/onboarding/branding' },
  { key: 'done', label: 'Launch', href: '/onboarding/done' },
];

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const currentIdx = STEPS.findIndex((s) => pathname.startsWith(s.href));

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="w-full px-6 py-4 flex items-center gap-3 border-b" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
              <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
            </svg>
          </div>
          <span className="font-bold text-sm grad-text">Setup Wizard</span>
        </Link>
      </header>

      {/* Progress steps */}
      <div className="w-full max-w-3xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-8">
          {STEPS.map((step, idx) => {
            const isComplete = idx < currentIdx;
            const isCurrent = idx === currentIdx;
            return (
              <div key={step.key} className="flex items-center gap-2 flex-1">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                  style={{
                    background: isComplete
                      ? 'linear-gradient(135deg, #16a34a, #15803d)'
                      : isCurrent
                        ? 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)'
                        : 'rgba(0,0,0,0.06)',
                    color: isComplete || isCurrent ? 'white' : 'var(--text-dim)',
                  }}
                >
                  {isComplete ? '✓' : idx + 1}
                </div>
                <span
                  className="text-xs font-medium hidden sm:block"
                  style={{ color: isCurrent ? 'var(--text)' : 'var(--text-dim)' }}
                >
                  {step.label}
                </span>
                {idx < STEPS.length - 1 && (
                  <div
                    className="flex-1 h-px mx-2"
                    style={{
                      background: isComplete ? '#16a34a' : 'rgba(0,0,0,0.08)',
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {children}
      </div>
    </div>
  );
}
