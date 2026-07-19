import { type NextRequest, NextResponse } from 'next/server';

import { isProtectedPath, routes } from '@/config/routes';
import { AUTH_SESSION_COOKIE } from '@/services/auth/config';

export function proxy(request: NextRequest) {
  if (
    isProtectedPath(request.nextUrl.pathname) &&
    !request.cookies.has(AUTH_SESSION_COOKIE)
  ) {
    const loginUrl = new URL(routes.login.path, request.url);
    loginUrl.searchParams.set(
      'redirect',
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );
    return NextResponse.redirect(loginUrl);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(
    'x-orion-request-path',
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
