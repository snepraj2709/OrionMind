import 'server-only';

import { createHmac, timingSafeEqual } from 'node:crypto';

import type { Route } from 'next';
import { cookies, headers } from 'next/headers';
import { redirect } from 'next/navigation';

import { routes, safeRedirectPath } from '@/config/routes';

import { AUTH_SESSION_COOKIE, AUTH_SESSION_MAX_AGE } from './config';
import type { AuthUser } from './types';

interface SessionPayload extends AuthUser {
  expiresAt: number;
}

function mockAuthSecret() {
  const configuredSecret = process.env.ORION_MOCK_AUTH_SECRET;
  if (configuredSecret) return configuredSecret;

  if (process.env.NODE_ENV === 'production') {
    throw new Error(
      'ORION_MOCK_AUTH_SECRET is required while mock authentication is enabled.',
    );
  }

  return 'orion-local-mock-auth-only';
}

function sign(value: string) {
  return createHmac('sha256', mockAuthSecret())
    .update(value)
    .digest('base64url');
}

function serializeUser(user: AuthUser) {
  const session: SessionPayload = {
    ...user,
    expiresAt: Date.now() + AUTH_SESSION_MAX_AGE * 1000,
  };
  const payload = Buffer.from(JSON.stringify(session)).toString('base64url');
  return `${payload}.${sign(payload)}`;
}

function parseUser(value: string): AuthUser | null {
  const [payload, signature] = value.split('.');
  if (!payload || !signature) return null;

  const expectedSignature = sign(payload);
  const actual = Buffer.from(signature);
  const expected = Buffer.from(expectedSignature);

  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    return null;
  }

  try {
    const parsed = JSON.parse(
      Buffer.from(payload, 'base64url').toString('utf8'),
    ) as Partial<SessionPayload>;

    if (
      !parsed.id ||
      !parsed.email ||
      !parsed.name ||
      !parsed.expiresAt ||
      parsed.expiresAt <= Date.now()
    ) {
      return null;
    }
    return { id: parsed.id, email: parsed.email, name: parsed.name };
  } catch {
    return null;
  }
}

export async function getCurrentUser() {
  const cookieStore = await cookies();
  const value = cookieStore.get(AUTH_SESSION_COOKIE)?.value;
  return value ? parseUser(value) : null;
}

export async function requireUser(requestedPath?: string) {
  const user = await getCurrentUser();
  if (user) return user;

  const requestHeaders = await headers();
  const destination =
    requestedPath ?? requestHeaders.get('x-orion-request-path') ?? undefined;
  const loginUrl = new URL(routes.login.path, 'https://orion.local');
  if (destination) {
    loginUrl.searchParams.set(
      'returnTo',
      safeRedirectPath(destination, routes.entries.path),
    );
  }

  redirect(`${loginUrl.pathname}${loginUrl.search}` as Route);
}

export async function setMockSession(user: AuthUser) {
  const cookieStore = await cookies();
  cookieStore.set(AUTH_SESSION_COOKIE, serializeUser(user), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: AUTH_SESSION_MAX_AGE,
  });
}

export async function clearMockSession() {
  const cookieStore = await cookies();
  cookieStore.delete(AUTH_SESSION_COOKIE);
}
