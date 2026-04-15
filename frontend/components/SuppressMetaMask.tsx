'use client';

import { useEffect } from 'react';

export default function SuppressMetaMask() {
  useEffect(() => {
    const originalError = console.error.bind(console);
    console.error = (...args: unknown[]) => {
      const msg = args[0]?.toString() ?? '';
      if (
        msg.includes('MetaMask') ||
        msg.includes('ethereum') ||
        msg.includes('chrome-extension') ||
        msg.includes('Unknown url scheme')
      )
        return;
      originalError(...args);
    };

    const handleError = (event: ErrorEvent) => {
      if (
        event.message?.includes('MetaMask') ||
        event.message?.includes('chrome-extension') ||
        event.message?.includes('Unknown url scheme') ||
        event.filename?.includes('inpage.js') ||
        event.filename?.includes('chrome-extension')
      ) {
        event.preventDefault();
      }
    };

    const handleRejection = (event: PromiseRejectionEvent) => {
      const msg = event.reason?.message ?? event.reason?.toString() ?? '';
      if (
        msg.includes('MetaMask') ||
        msg.includes('chrome-extension') ||
        msg.includes('Unknown url scheme')
      ) {
        event.preventDefault();
      }
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleRejection);
    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleRejection);
      console.error = originalError;
    };
  }, []);

  return null;
}
