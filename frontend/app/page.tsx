import Link from 'next/link';

export default function HomePage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <header className="w-full px-6 py-4 flex items-center justify-between max-w-6xl mx-auto">
        <div className="flex items-center gap-2.5">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: '0 2px 12px rgba(176,9,9,0.35)',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
            </svg>
          </div>
          <span className="font-bold text-lg grad-text">Moeen AI</span>
        </div>
        <nav className="flex items-center gap-6">
          <Link
            href="/pricing"
            className="text-sm font-medium"
            style={{ color: 'var(--text-muted)' }}
          >
            Pricing
          </Link>
          <Link
            href="/login"
            className="text-sm font-medium"
            style={{ color: 'var(--text-muted)' }}
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            className="px-5 py-2 text-sm font-bold rounded-xl text-white"
            style={{
              background:
                'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: '0 4px 18px rgba(176,9,9,0.38)',
            }}
          >
            Get Started
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center max-w-4xl mx-auto">
        <div className="animate-fade-up">
          <div
            className="inline-block px-4 py-1.5 rounded-full text-xs font-bold mb-8 uppercase tracking-widest"
            style={{
              background: 'rgba(176,9,9,0.08)',
              color: '#b00909',
              border: '1px solid rgba(176,9,9,0.20)',
            }}
          >
            Multi-Tenant AI Platform
          </div>

          <h1
            className="text-5xl sm:text-6xl font-extrabold leading-[1.1] mb-6"
            style={{ color: 'var(--text)' }}
          >
            Your AI WhatsApp Assistant,{' '}
            <span className="grad-text">Built for Scale</span>
          </h1>

          <p
            className="text-lg sm:text-xl max-w-2xl mx-auto mb-10 leading-relaxed"
            style={{ color: 'var(--text-muted)' }}
          >
            Deploy intelligent WhatsApp assistants for your clients in minutes.
            Each tenant gets their own AI, branding, dashboard, and complete
            data isolation — all from one platform.
          </p>

          <div className="flex items-center justify-center gap-4">
            <Link
              href="/signup"
              className="px-8 py-3.5 text-sm font-bold rounded-xl text-white transition-transform hover:-translate-y-0.5"
              style={{
                background:
                  'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                boxShadow: '0 4px 24px rgba(176,9,9,0.4)',
              }}
            >
              Create Workspace — Free
            </Link>
            <Link
              href="/pricing"
              className="px-8 py-3.5 text-sm font-bold rounded-xl transition-all"
              style={{
                color: 'var(--text-muted)',
                border: '1px solid rgba(0,0,0,0.12)',
              }}
            >
              View Pricing
            </Link>
          </div>
        </div>

        {/* Feature grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-24 w-full max-w-3xl">
          {[
            {
              title: 'Per-Tenant AI',
              desc: 'Each client gets their own OpenAI assistant with custom instructions, tools, and behavior.',
              icon: '🤖',
            },
            {
              title: 'Complete Isolation',
              desc: 'Conversations, data, credentials, and Redis state are fully isolated between tenants.',
              icon: '🔒',
            },
            {
              title: 'White-Label Ready',
              desc: 'Custom branding, colors, and logo per tenant. Your clients see their own brand.',
              icon: '🎨',
            },
          ].map((f) => (
            <div
              key={f.title}
              className="rounded-2xl p-6 text-left"
              style={{
                background: '#ffffff',
                border: '1px solid rgba(0,0,0,0.06)',
                boxShadow: '0 2px 12px rgba(0,0,0,0.04)',
              }}
            >
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3
                className="font-bold text-sm mb-2"
                style={{ color: 'var(--text)' }}
              >
                {f.title}
              </h3>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-dim)' }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 text-center">
        <p className="text-xs" style={{ color: 'var(--text-dim)' }}>
          Moeen AI Platform
        </p>
      </footer>
    </div>
  );
}
