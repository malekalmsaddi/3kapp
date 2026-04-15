'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

const NAV_LINKS = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/send_template', label: 'Send' },
  { href: '/settings', label: 'Settings' },
  { href: '/admin/threads', label: 'Threads' },
  { href: '/admin/system', label: 'System' },
  { href: '/admin/email', label: 'Email' },
  { href: '/admin/logs', label: 'Logs' },
];

export default function NavBar() {
  const router = useRouter();
  const pathname = usePathname();

  async function handleLogout() {
    try {
      await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    } catch {
      // Network error — proceed with client-side redirect anyway so the
      // user isn't stuck. The server session will expire on its own.
    }
    router.replace('/login');
  }

  return (
    <header
      className="sticky top-0 z-50 w-full"
      style={{
        background: 'var(--bg-nav)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: '1px solid rgba(0,0,0,0.07)',
        boxShadow: '0 1px 12px rgba(0,0,0,0.06)',
      }}
    >
      <div className="flex items-center gap-3 px-6 py-3.5">
        {/* Logo */}
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5 mr-5 shrink-0"
        >
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: '0 2px 12px rgba(176,9,9,0.35)',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="white">
              <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
            </svg>
          </div>
          <span
            className="font-bold text-sm tracking-tight"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Moeen AI
          </span>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1 flex-1 overflow-x-auto">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive =
              pathname === href || pathname.startsWith(href + '/');
            return (
              <Link
                key={href}
                href={href}
                className="px-3.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition-all duration-200 font-medium"
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
                  if (!isActive) {
                    const el = e.currentTarget as HTMLAnchorElement;
                    el.style.color = 'var(--text-muted)';
                    el.style.background = 'rgba(0,0,0,0.04)';
                    el.style.borderColor = 'rgba(0,0,0,0.07)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    const el = e.currentTarget as HTMLAnchorElement;
                    el.style.color = 'var(--text-dim)';
                    el.style.background = 'transparent';
                    el.style.borderColor = 'transparent';
                  }
                }}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        {/* User + logout */}
        <div className="flex items-center gap-3 shrink-0 ml-2">
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
              style={{
                background:
                  'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                boxShadow: '0 2px 10px rgba(176,9,9,0.30)',
              }}
            >
              A
            </div>
            <span
              className="text-sm hidden sm:block"
              style={{ color: 'var(--text-muted)' }}
            >
              Admin
            </span>
          </div>

          <button
            onClick={handleLogout}
            className="px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all duration-200"
            style={{
              color: 'var(--text-dim)',
              border: '1px solid rgba(0,0,0,0.10)',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.color = '#b00909';
              el.style.borderColor = 'rgba(176,9,9,0.30)';
              el.style.background = 'rgba(176,9,9,0.06)';
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.color = 'var(--text-dim)';
              el.style.borderColor = 'rgba(0,0,0,0.10)';
              el.style.background = 'transparent';
            }}
          >
            Sign Out
          </button>
        </div>
      </div>
    </header>
  );
}
