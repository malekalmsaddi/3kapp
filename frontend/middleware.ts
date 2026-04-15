import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PROTECTED_PATHS = ['/dashboard', '/settings', '/send_template', '/admin'];
const PLATFORM_PATHS = ['/platform'];
const ONBOARDING_PATHS = ['/onboarding'];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  const isPlatform = PLATFORM_PATHS.some((p) => pathname.startsWith(p));
  const isOnboarding = ONBOARDING_PATHS.some((p) => pathname.startsWith(p));

  if (!isProtected && !isPlatform && !isOnboarding) {
    return NextResponse.next();
  }

  // Accept either JWT access_token cookie (new) or legacy session cookie
  const hasJWT = req.cookies.has('access_token');
  const hasSession = req.cookies.has('session');

  if (!hasJWT && !hasSession) {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  // For platform routes, we'd ideally check the JWT role claim here.
  // Since HttpOnly cookies aren't decodable in Edge middleware without
  // a crypto library, we rely on the backend to enforce role checks.
  // The frontend middleware just checks for auth presence.

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/settings/:path*',
    '/send_template/:path*',
    '/admin/:path*',
    '/platform/:path*',
    '/onboarding/:path*',
  ],
};
