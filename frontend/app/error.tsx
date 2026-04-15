'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import GlassPanel from '../components/GlassPanel';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <GlassPanel>
        <h1 className="mb-2 text-xl font-semibold text-red-500">
          Something went wrong
        </h1>
        <button
          onClick={() => reset()}
          className="mb-4 rounded bg-red-500 px-3 py-1 text-white"
        >
          Try again
        </button>
        <div>
          <Link href="/" className="text-red-500 underline">
            Go home
          </Link>
        </div>
      </GlassPanel>
    </div>
  );
}
