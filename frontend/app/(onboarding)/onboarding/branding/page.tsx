'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function OnboardingBrandingPage() {
  const router = useRouter();
  const [brandName, setBrandName] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#b00909');
  const [secondaryColor, setSecondaryColor] = useState('#891565');
  const [logoUrl, setLogoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/v1/onboarding/branding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          brand_name: brandName,
          brand_color_primary: primaryColor,
          brand_color_secondary: secondaryColor,
          brand_logo_url: logoUrl,
        }),
      });
      if (res.ok) {
        router.push('/onboarding/done');
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to save');
      }
    } catch {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
        Customize Your Brand
      </h2>
      <p className="text-sm mb-8" style={{ color: 'var(--text-dim)' }}>
        Set your brand name and colors. Your team will see these in the dashboard.
      </p>

      <div className="flex gap-8 flex-col lg:flex-row">
        <form onSubmit={handleSubmit} className="space-y-5 max-w-lg flex-1">
          {error && (
            <div className="px-4 py-3 rounded-xl text-sm" style={{
              background: 'rgba(176,9,9,0.06)', border: '1px solid rgba(176,9,9,0.25)', color: '#b00909',
            }}>{error}</div>
          )}

          <div className="space-y-2">
            <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
              Brand Name
            </label>
            <input value={brandName} onChange={(e) => setBrandName(e.target.value)}
              placeholder="Your Company Name" required
              className="w-full px-4 py-3 text-sm rounded-xl outline-none"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
                Primary Color
              </label>
              <div className="flex items-center gap-2">
                <input type="color" value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="w-10 h-10 rounded-lg cursor-pointer border-0" />
                <input value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)}
                  className="flex-1 px-3 py-2 text-sm rounded-lg outline-none font-mono"
                  style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
              </div>
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
                Secondary Color
              </label>
              <div className="flex items-center gap-2">
                <input type="color" value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="w-10 h-10 rounded-lg cursor-pointer border-0" />
                <input value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)}
                  className="flex-1 px-3 py-2 text-sm rounded-lg outline-none font-mono"
                  style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-dim)' }}>
              Logo URL (optional)
            </label>
            <input value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)}
              placeholder="https://..."
              className="w-full px-4 py-3 text-sm rounded-xl outline-none"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.12)' }} />
          </div>

          <button type="submit" disabled={loading}
            className="px-8 py-3 text-sm font-bold rounded-xl text-white disabled:opacity-50"
            style={{
              background: `linear-gradient(135deg, ${primaryColor} 0%, ${secondaryColor} 55%, #6d1f9e 100%)`,
              boxShadow: `0 4px 18px ${primaryColor}60`,
            }}>
            {loading ? 'Saving...' : 'Continue →'}
          </button>
        </form>

        {/* Live preview */}
        <div className="flex-1 max-w-sm">
          <p className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: 'var(--text-dim)' }}>
            Preview
          </p>
          <div className="rounded-2xl p-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)' }}>
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center"
                style={{ background: `linear-gradient(135deg, ${primaryColor}, ${secondaryColor})` }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
                  <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
                </svg>
              </div>
              <span className="font-bold text-sm" style={{ color: primaryColor }}>
                {brandName || 'Your Brand'}
              </span>
            </div>
            <div className="h-2 rounded-full mb-2" style={{ background: `linear-gradient(to right, ${primaryColor}, ${secondaryColor})`, width: '60%' }} />
            <div className="h-2 rounded-full mb-2" style={{ background: 'rgba(0,0,0,0.06)', width: '80%' }} />
            <div className="h-2 rounded-full" style={{ background: 'rgba(0,0,0,0.04)', width: '40%' }} />
          </div>
        </div>
      </div>
    </div>
  );
}
