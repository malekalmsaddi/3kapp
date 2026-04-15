'use client';

import { useEffect, useState } from 'react';
import GlassPanel from '../../../../components/GlassPanel';

interface Plan {
  id: string;
  name: string;
  display_name: string;
  price_monthly: number;
  price_yearly: number;
  entitlements: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
}

export default function PlatformPlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/platform/plans', { credentials: 'include' })
      .then((res) => res.json())
      .then(setPlans)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6" style={{ color: 'var(--text-dim)' }}>Loading plans...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Plan Configuration</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {plans.map((plan) => (
          <GlassPanel key={plan.id}>
            <h3 className="font-bold text-lg mb-1" style={{ color: 'var(--text)' }}>
              {plan.display_name}
            </h3>
            <p className="text-2xl font-extrabold mb-4" style={{ color: 'var(--text)' }}>
              {plan.price_monthly > 0 ? `$${plan.price_monthly}` : 'Free'}
              <span className="text-xs font-normal" style={{ color: 'var(--text-dim)' }}>/mo</span>
            </p>

            <div className="space-y-2">
              {Object.entries(plan.entitlements).map(([key, value]) => (
                <div key={key} className="flex justify-between text-xs">
                  <span style={{ color: 'var(--text-dim)' }}>
                    {key.replace(/_/g, ' ')}
                  </span>
                  <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                    {typeof value === 'boolean'
                      ? value ? '✓' : '✗'
                      : value === -1
                        ? '∞'
                        : String(value)}
                  </span>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-3" style={{ borderTop: '1px solid rgba(0,0,0,0.06)' }}>
              <span className={`text-xs font-bold px-2 py-1 rounded-md ${plan.is_active ? '' : ''}`}
                style={{
                  background: plan.is_active ? 'rgba(22,163,74,0.08)' : 'rgba(176,9,9,0.08)',
                  color: plan.is_active ? '#16a34a' : '#b00909',
                }}>
                {plan.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          </GlassPanel>
        ))}
      </div>
    </div>
  );
}
