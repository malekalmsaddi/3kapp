import Link from 'next/link';

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    desc: 'Get started with a basic AI assistant',
    features: [
      '1 admin user',
      '200 messages/day',
      '100 bulk recipients/day',
      'Basic AI (GPT-4o-mini)',
      'Escalation to human',
    ],
    cta: 'Start Free',
    highlight: false,
  },
  {
    name: 'Starter',
    price: '$49',
    period: '/month',
    desc: 'For growing businesses',
    features: [
      '3 admin users',
      '1,000 messages/day',
      '500 bulk recipients/day',
      'Google Calendar integration',
      'GPT-4o-mini',
    ],
    cta: 'Start Starter',
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$149',
    period: '/month',
    desc: 'Full power for serious operations',
    features: [
      '10 admin users',
      '5,000 messages/day',
      '2,000 bulk recipients/day',
      'Custom branding',
      'Audit logs',
      'GPT-4o',
      'Own Twilio credentials',
    ],
    cta: 'Start Pro',
    highlight: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    desc: 'Unlimited scale with dedicated support',
    features: [
      'Unlimited admins',
      'Unlimited messages',
      'Unlimited bulk sends',
      'Any AI model',
      'API access',
      'Dedicated support',
      'SLA guarantee',
    ],
    cta: 'Contact Us',
    highlight: false,
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen">
      {/* Nav */}
      <header className="w-full px-6 py-4 flex items-center justify-between max-w-6xl mx-auto">
        <Link href="/" className="flex items-center gap-2.5">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
              boxShadow: '0 2px 12px rgba(176,9,9,0.35)',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
            </svg>
          </div>
          <span className="font-bold text-lg grad-text">Moeen AI</span>
        </Link>
        <nav className="flex items-center gap-6">
          <Link href="/login" className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
            Sign In
          </Link>
          <Link
            href="/signup"
            className="px-5 py-2 text-sm font-bold rounded-xl text-white"
            style={{
              background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
            }}
          >
            Get Started
          </Link>
        </nav>
      </header>

      {/* Pricing */}
      <main className="px-6 py-16 max-w-6xl mx-auto">
        <div className="text-center mb-16 animate-fade-up">
          <h1 className="text-4xl font-extrabold mb-4" style={{ color: 'var(--text)' }}>
            Simple, Transparent <span className="grad-text">Pricing</span>
          </h1>
          <p className="text-lg" style={{ color: 'var(--text-muted)' }}>
            Start free. Scale as you grow. No hidden fees.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className="rounded-2xl p-6 flex flex-col"
              style={{
                background: '#ffffff',
                border: plan.highlight
                  ? '2px solid #b00909'
                  : '1px solid rgba(0,0,0,0.08)',
                boxShadow: plan.highlight
                  ? '0 8px 32px rgba(176,9,9,0.15)'
                  : '0 2px 12px rgba(0,0,0,0.04)',
              }}
            >
              {plan.highlight && (
                <div
                  className="text-[10px] font-bold uppercase tracking-widest mb-4 px-3 py-1 rounded-full self-start"
                  style={{
                    background: 'rgba(176,9,9,0.08)',
                    color: '#b00909',
                  }}
                >
                  Most Popular
                </div>
              )}
              <h3 className="font-bold text-lg" style={{ color: 'var(--text)' }}>
                {plan.name}
              </h3>
              <div className="mt-2 mb-1">
                <span className="text-3xl font-extrabold" style={{ color: 'var(--text)' }}>
                  {plan.price}
                </span>
                <span className="text-sm" style={{ color: 'var(--text-dim)' }}>
                  {plan.period}
                </span>
              </div>
              <p className="text-xs mb-6" style={{ color: 'var(--text-dim)' }}>
                {plan.desc}
              </p>
              <ul className="space-y-2 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li
                    key={f}
                    className="text-sm flex items-start gap-2"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <span style={{ color: '#16a34a' }}>&#10003;</span>
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                href={plan.name === 'Enterprise' ? '/contact' : '/signup'}
                className="block text-center py-2.5 text-sm font-bold rounded-xl transition-all"
                style={
                  plan.highlight
                    ? {
                        background: 'linear-gradient(135deg, #b00909 0%, #891565 55%, #6d1f9e 100%)',
                        color: 'white',
                        boxShadow: '0 4px 18px rgba(176,9,9,0.38)',
                      }
                    : {
                        border: '1px solid rgba(0,0,0,0.12)',
                        color: 'var(--text-muted)',
                      }
                }
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
