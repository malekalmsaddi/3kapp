'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState, PropsWithChildren } from 'react';

export default function AuthGuard({ children }: PropsWithChildren) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [networkError, setNetworkError] = useState(false);

  useEffect(() => {
    // Session cookie is HttpOnly — unreadable by JS.
    // Verify auth by pinging an authenticated endpoint.
    // Only redirect on explicit 401; a network error should not log the user out.
    let cancelled = false;

    async function verify(attempt: number) {
      try {
        const res = await fetch('/api/dashboard/data', {
          credentials: 'include',
        });
        if (cancelled) return;
        if (res.status === 401) {
          router.replace('/login');
        } else {
          setNetworkError(false);
          setChecking(false);
        }
      } catch {
        if (cancelled) return;
        // Retry once before showing an error — a single dropped packet shouldn't bounce the user.
        if (attempt === 0) {
          setTimeout(() => verify(1), 2000);
        } else {
          // Second failure: surface an error rather than silently redirecting.
          setNetworkError(true);
          setChecking(false);
        }
      }
    }

    verify(0);
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (checking) return null;

  if (networkError) {
    return (
      <div
        className="flex items-center justify-center min-h-screen text-sm"
        style={{ color: '#b00909' }}
        role="alert"
      >
        Unable to verify your session. Please check your connection and{' '}
        <button
          onClick={() => window.location.reload()}
          className="ml-1 underline"
        >
          refresh
        </button>
        .
      </div>
    );
  }

  return <>{children}</>;
}
