import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    const rawApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL;
    if (!rawApiUrl) {
      if (process.env.NODE_ENV === 'production') {
        throw new Error('NEXT_PUBLIC_API_BASE_URL or NEXT_PUBLIC_API_URL must be set in production');
      }
      // Fall back to local dev server only in development
      return [{ source: '/api/:path*', destination: 'http://localhost:8080/:path*' }];
    }
    const apiUrl =
      rawApiUrl.startsWith('http://') || rawApiUrl.startsWith('https://')
        ? rawApiUrl
        : `https://${rawApiUrl}`;
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
