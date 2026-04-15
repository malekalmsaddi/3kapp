import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// NOTE: Keep PROTECTED_PATHS and the matcher below in sync — both must list all protected routes.
const PROTECTED_PATHS = ['/dashboard', '/settings', '/send_template', '/admin'];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const requiresAuth = PROTECTED_PATHS.some((path) =>
    pathname.startsWith(path),
  );

  if (requiresAuth && !req.cookies.get('session')) {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/settings/:path*', '/send_template/:path*', '/admin/:path*'],
};
